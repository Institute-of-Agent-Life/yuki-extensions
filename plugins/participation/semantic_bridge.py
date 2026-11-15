"""Load the pinned participation library and exchange its native review with Rust."""

import asyncio
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import time

import httpx


UPSTREAM = "a6a13d4f04ecc36da26adb5f364abdb4f032fc1e"
UPSTREAM_SHA256 = "0e2cad3ad0f16e710e39f6fd2c9513c0a4c889ca54617ad6fdcb599f313a6ab4"


def receive():
    return json.loads(sys.stdin.buffer.readline())


def send(value):
    print(json.dumps(value, separators=(",", ":"), ensure_ascii=True), flush=True)


def original(source):
    body = b"".join(base64.b64decode(page, validate=True) for page in source["pages"])
    if hashlib.sha256(body).hexdigest() != source["version"]:
        raise ValueError("original source digest changed")
    return json.loads(body)


def projected(source, controller, reply=None):
    from yuki_participation.models import EventMention, ScopedEvent, SourceRef

    scope = controller.state.scope
    event = source["event"]
    key = f"event:{event}"
    digest = source["version"]
    previous = controller.state.host_checkpoint.get("source_versions", {}).get(key)
    revision = 1 if previous is None else previous[0] + int(previous[1] != digest)
    ref = SourceRef(event_id=key, revision=revision)
    frame = original(source)
    if frame["kind"] == "self":
        if (frame["event"], frame["entry"], frame["generation"]) != (event, scope.conversation_id, scope.generation):
            raise ValueError("original delivery is outside the observation scope")
        item = ScopedEvent(scope=scope, ref=ref, thread=key, kind="self", author="SELF", target="group",
                           text=frame["text"], at=frame["observed"] / 1000, source_order=event)
    else:
        origin = source["origin"]
        if (origin["entry"], origin["observed_generation"]) != (scope.conversation_id, scope.generation):
            raise ValueError("original human observation is outside the review scope")
        actor = origin["original_person"]
        item = ScopedEvent(scope=scope, ref=ref, thread=reply.thread if reply else key, author=actor, target=actor,
                           text=frame.get("text") or "".join(part["text"] for part in frame["segments"] if part["type"] == "text"),
                           at=(frame["occurred"] or frame["observed"]) / 1000, source_order=event,
                           reply_to=reply.ref if reply else None,
                           mentions=tuple(EventMention.model_validate(mark) for mark in source["mentions"]))
    current = controller.state.events.get(key)
    if current is not None and current.ref == ref:
        return current
    if not controller.observe_committed_event(item):
        raise ValueError("original observation is stale")
    controller.set_host_mapping_entry("source_versions", key, [revision, digest])
    return item


def expression_producer(controller, proof, focus):
    if proof is None:
        return None
    key = f"event:{proof['event']}"
    origin = proof["origin"]
    candidate = controller.state.events.get(key)
    version = controller.state.host_checkpoint.get("source_versions", {}).get(key)
    if (candidate is None or not origin or candidate.kind != "human" or candidate.author != focus.author
            or origin["entry"] != focus.scope.conversation_id
            or origin["observed_generation"] != focus.scope.generation
            or origin["original_person"] != candidate.author
            or version != [candidate.ref.revision, proof["version"]]):
        return None
    return candidate


def continue_original(controller, focus, earlier, job, now):
    from yuki_participation.models import Effect
    from yuki_participation.participation import ParticipationUnit, UnitBinding
    from yuki_participation.self_report import SelfDelta, SelfReport

    receipt = job["anchor"].get("delivery_origin")
    prior = expression_producer(controller, job["producer"], focus) if receipt else earlier
    if prior is None or prior.kind != "human" or prior.author != focus.author:
        return False
    source = receipt["producer_event"] if receipt else job["anchor"]["event"]
    basis = controller.participation_own_basis(prior.thread, prior.author, now)
    if not basis:
        return False
    send({"type": "feedback", "event": source})
    executions = receive().get("executions", [])
    if receipt:
        feedback = [row for row in executions if row["execution"] == receipt["execution"]
                    and any(send["operation"] == receipt["operation"] and send["confirmed_parts"] > 0
                            for send in row["sends"])]
    else:
        feedback = [row for row in executions if (row.get("self_report") or {}).get("event") == source]
    if len(feedback) != 1:
        return False
    (execution,) = feedback
    unit = ParticipationUnit(thread=prior.thread, target=prior.target)
    binding = UnitBinding(scope=focus.scope, unit=unit, actor=prior.author,
                          basis=tuple(dict.fromkeys((*basis, prior.ref))))
    if receipt:
        effect = Effect(effect_id=f"send:{receipt['execution']}:{receipt['operation']}", kind="message",
                        at=receipt["first_confirmed_at"] / 1000, actual_targets=("group",))
        if not controller.observe_unit_expression(binding, execution["execution"], effect, anchor=earlier.ref):
            return False
    report = execution["self_report"]
    if report is not None and report["event"] == source:
        controller.observe_unit_hint(binding, SelfReport(
            run_ref=execution["execution"], sequence=report["sequence"], response_id=report["attempt"],
            at=prior.at, source=prior.ref, delta=SelfDelta(engage=report["engage"]),
        ))
        if report["engage"] == "quiet":
            return False
    matched = controller.participation_view(focus, now).matched_unit
    if matched is None or matched.unit != unit or matched.binding.actor != focus.author:
        return False
    actual = matched.binding.model_copy(update={"basis": tuple(dict.fromkeys((*binding.basis, focus.ref)))})
    if not controller.continuation_current(focus.ref, actual, now):
        return False
    send({"type": "fast"})
    outcome = receive()
    if not outcome.get("accepted"):
        return None
    if not controller.observe_unit_input(actual, focus.ref, continuation=True):
        raise ValueError("original continuation could not be applied to the participation state")
    return True


async def review(job):
    from yuki_participation.controller import Controller
    from yuki_participation.models import Scope, Snapshot
    from yuki_participation.observer import JevObserver
    from yuki_participation.participation import ParticipationUnit, UnitBinding
    from yuki_participation.store import SnapshotStore

    if original(job["focus"])["bot_stage"] != job["receiver"]:
        send({"type": "done"})
        return
    original_focus = job["focus"]["origin"]
    scope = Scope(conversation_id=original_focus["entry"], generation=original_focus["observed_generation"])
    now = time.time()
    with closing(SnapshotStore(Path(job["checkpoint"]))) as store:
        store.connection.execute("PRAGMA secure_delete=ON")
        existing = store.load(scope)
        revision = existing[0] if existing else 0
        controller = Controller.restore(existing[1], now) if existing else Controller(scope, now)
        earlier = projected(job["anchor"], controller)
        focus = projected(job["focus"], controller, earlier)
        if focus.kind != "human":
            raise ValueError("the focus must be an original human input")
        key = focus.ref.event_id
        previous = controller.state.host_checkpoint.get("ordinary_reviews", {}).get(key)
        if previous is not None:
            snapshot = Snapshot.model_validate(previous["snapshot"])
            if snapshot.focus.ref != focus.ref or tuple(item.ref for item in snapshot.context) != (earlier.ref,):
                raise ValueError("the original review basis changed")
            if previous["settled"]:
                send({"type": "done"})
                return
            continued = previous.get("continued", False)
        else:
            continued = continue_original(controller, focus, earlier, job, now)
            if continued is None:
                send({"type": "done"})
                return
            snapshot = controller.freeze_observation(Snapshot(scope=scope, focus=focus, context=(earlier,),
                                                              sequence=revision + 1, issued_at=max(now, focus.at)))
            controller.set_host_mapping_entry("ordinary_reviews", key,
                                              {"snapshot": snapshot.model_dump(mode="json"), "settled": False,
                                               "continued": continued})
            revision = store.save(controller.state, expected_revision=revision)

        def exchange(request):
            wire = json.loads(request.content)
            wire.pop("model")
            send({"type": "review", "wire": wire})
            response = receive()
            if response.get("status") != "response":
                return httpx.Response(503)
            payload = b"".join(base64.b64decode(piece, validate=True) for piece in response["pages"])
            if hashlib.sha256(payload).hexdigest() != response["sha256"]:
                raise ValueError("original model result digest changed")
            return httpx.Response(200, content=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(exchange), trust_env=False) as client:
            observer = JevObserver("host-route", identity=lambda: {"display_name": job["name"], "aliases": ()},
                                   endpoint="http://127.0.0.1/systemone", request_model="host-route",
                                   response_model=job["response_model"], client=client)
            try:
                result = await observer.evaluate(snapshot)
            except (httpx.HTTPError, ValueError):
                send({"type": "done"})
                return
        if not controller.apply_semantic_observation(result):
            send({"type": "done"})
            return
        invited = controller.invitation_current(focus, result.received_at)
        send({"type": "decision", "invited": invited})
        outcome = receive()
        if outcome.get("status") == "invalidated":
            send({"type": "done"})
            return
        if outcome.get("accepted") and not continued:
            binding = UnitBinding(scope=scope, unit=ParticipationUnit(thread=focus.thread, target=focus.author),
                                  actor=focus.author, basis=(focus.ref, earlier.ref))
            if not controller.observe_unit_input(binding, focus.ref):
                raise ValueError("original admission could not be applied to the participation state")
        controller.set_host_mapping_entry("ordinary_reviews", key,
                                          {"snapshot": snapshot.model_dump(mode="json"), "settled": True,
                                           "continued": continued})
        store.save(controller.state, expected_revision=revision)
        send({"type": "done"})


def erase(job):
    from yuki_participation.controller import Controller
    from yuki_participation.models import Scope, Snapshot, SourceRef
    from yuki_participation.store import SnapshotStore

    checkpoint = Path(job["checkpoint"])
    if not checkpoint.is_file():
        send({"type": "done"})
        return
    keys = {f"event:{event}" for event in job["sources"]}
    with closing(SnapshotStore(checkpoint)) as store:
        store.connection.execute("PRAGMA secure_delete=ON")
        scopes = store.connection.execute("SELECT scope,generation FROM snapshot_head").fetchall()
        for entry, generation in scopes:
            revision, state = store.load(Scope(conversation_id=entry, generation=generation))
            controller = Controller.restore(state, time.time())
            versions = dict(state.host_checkpoint.get("source_versions", {}))
            reviews = dict(state.host_checkpoint.get("ordinary_reviews", {}))
            related = keys.intersection(versions)
            if not related:
                continue
            for key in related:
                controller.observe_source_change(SourceRef(event_id=key, revision=versions.pop(key)[0]))
            for key, record in list(reviews.items()):
                snapshot = Snapshot.model_validate(record["snapshot"])
                if any(item.ref.event_id in related for item in (snapshot.focus, *snapshot.context)):
                    del reviews[key]
            controller.set_state_entry("host_checkpoint", "source_versions", versions)
            controller.set_state_entry("host_checkpoint", "ordinary_reviews", reviews)
            store.save(controller.state, expected_revision=revision)
        checkpoint_result = store.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint_result[0] != 0:
            raise RuntimeError("original SQLite WAL is still in use")
    send({"type": "done"})


def pending(job):
    from yuki_participation.models import Scope
    from yuki_participation.store import SnapshotStore

    with closing(SnapshotStore(Path(job["checkpoint"]))) as store:
        generations = store.connection.execute(
            "SELECT generation FROM snapshot_head WHERE scope=?", (job["entry"],)
        ).fetchall()
        events = set()
        for (generation,) in generations:
            _, state = store.load(Scope(conversation_id=job["entry"], generation=generation))
            for key, record in state.host_checkpoint.get("ordinary_reviews", {}).items():
                if not record["settled"]:
                    events.add(int(key.removeprefix("event:")))
    send({"type": "pending", "events": sorted(events)})


def main():
    archive = Path(sys.argv[1])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("participation archive does not match the pinned source")
    with tempfile.TemporaryDirectory(prefix="yuki-participation-library-") as directory:
        with tarfile.open(archive) as bundle:
            bundle.extractall(directory, filter="data")
        source = Path(directory) / f"Yuki-Semantic-Participation-{UPSTREAM}" / "src"
        sys.path.insert(0, str(source))
        job = receive()
        if job["action"] == "erase":
            erase(job)
        elif job["action"] == "pending":
            pending(job)
        else:
            asyncio.run(review(job))


if __name__ == "__main__":
    main()
