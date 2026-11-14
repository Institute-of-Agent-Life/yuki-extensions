"""A disposable SDK peer for the pinned participation library."""

import asyncio
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import httpx
from yuki_participation.controller import Controller
from yuki_participation.models import EventMention, Scope, ScopedEvent, Snapshot, SourceRef
from yuki_participation.observer import JevObserver
from yuki_participation.participation import ParticipationUnit, UnitBinding
from yuki_participation.store import SnapshotStore
from yuki_plugin_sdk.connection import Binding, Peer, encode, read_frame
from yuki_plugin_sdk.host import Calls


class Session:
    def __init__(self):
        binding = Binding.from_json(json.loads(os.environ["YUKI_PLUGIN_BINDING"]))
        peer = Peer(binding)
        self.write(peer.request(1, binding.offer()))
        raw = read_frame(sys.stdin.buffer)
        peer.receive(raw)
        self.calls = Calls(json.loads(raw)["result"])
        self.next_id = 1
        self.events = []
        self.wire = []

    @staticmethod
    def write(frame):
        sys.stdout.buffer.write(encode(frame))
        sys.stdout.buffer.flush()

    def receive(self):
        raw = read_frame(sys.stdin.buffer)
        if raw is None:
            return None
        frame = json.loads(raw)
        kind, method, payload = self.calls.receive(frame)
        if kind == "notification" and method == "observer.event":
            self.events.append(payload)
        return kind, method, payload

    def request(self, method, params):
        self.next_id += 1
        self.write(self.calls.request(self.next_id, method, params))
        while (frame := self.receive()) is not None:
            kind, name, response = frame
            if kind == "response":
                if name != method or response["id"] != self.next_id:
                    raise RuntimeError("unmatched Host receipt")
                self.wire.append({"method": method, "params": params, "response": response})
                if "result" not in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]
        raise RuntimeError("Host closed during the replay")


def content(session, first):
    raw = bytearray(base64.b64decode(first["data"]))
    page = first
    while not page["complete"]:
        page = session.request("participation.source", {
            "event": first["event"], "version": first["version"],
            "cursor": page["next"], "include_self": True,
        })
        raw.extend(base64.b64decode(page["data"]))
    if hashlib.sha256(raw).hexdigest() != first["version"]:
        raise ValueError("original event hash changed")
    return json.loads(raw)


def hydrate(session, event, version=None):
    params = {"event": event, "include_origin": True, "include_reply": True,
              "include_self": True, "mention_cursor": 0}
    if version is not None:
        params["version"] = version
    first = session.request("participation.source", params)
    frame = content(session, first)

    mentions = first["mentions"]["items"]
    page = first["mentions"]
    while not page["complete"]:
        response = session.request("participation.source", {
            "event": event, "version": first["version"], "cursor": first["size"],
            "mention_cursor": page["next"],
        })
        page = response["mentions"]
        mentions.extend(page["items"])
    return (first["origin"], first["reply_to"], frame,
            tuple(EventMention.model_validate(row) for row in mentions), first["version"])


def source_ref(controller, event, digest):
    key = f"event:{event}"
    prior = controller.state.host_checkpoint.get("source_versions", {}).get(key)
    version = 1 if prior is None else prior[0] + int(prior[1] != digest)
    controller.set_host_mapping_entry("source_versions", key, [version, digest])
    return SourceRef(event_id=key, revision=version)


def scoped(origin, frame, mentions, event, ref, reply=None):
    return ScopedEvent(
        scope=Scope(conversation_id=origin["entry"], generation=origin["observed_generation"]),
        ref=ref, thread=reply.event_id if reply else ref.event_id,
        author=origin["original_person"], target=origin["original_person"],
        text=frame.get("text") or "".join(
            segment["text"] for segment in frame["segments"] if segment["type"] == "text"
        ),
        at=(frame["occurred"] or frame["observed"]) / 1000,
        mentions=mentions, reply_to=reply, source_order=event,
    )


def scoped_reply(session, controller, anchor, origin):
    event = anchor["event"]
    first = session.request("participation.source", {**anchor, "include_self": True})
    frame = content(session, first)
    ref = source_ref(controller, event, first["version"])
    if frame["kind"] != "self":
        past_origin, _, past_frame, past_mentions, _ = hydrate(session, event, anchor["version"])
        return scoped(past_origin, past_frame, past_mentions, event, ref)
    if (frame["event"], frame["entry"], frame["generation"]) != (
        event, origin["entry"], origin["observed_generation"],
    ):
        raise ValueError("original SELF context left the focus scope")
    return ScopedEvent(scope=Scope(conversation_id=frame["entry"], generation=frame["generation"]),
                       ref=ref, thread=ref.event_id, author="SELF", target="group", kind="self",
                       text=frame["text"], at=frame["observed"] / 1000, source_order=event)


def review_payload(session, receipt):
    payload = bytearray()
    offset = 0
    while offset is not None:
        page = session.request("llm.result", {"request": receipt["request"], "offset": offset, "limit": 97})
        payload.extend(base64.b64decode(page["bytes"]))
        offset = page["next_offset"]
    if hashlib.sha256(payload).hexdigest() != page["sha256"]:
        raise ValueError("Jev result changed during paging")
    return bytes(payload)


async def exercise(session, event, config, checkpoint):
    origin, anchor, frame, mentions, digest = hydrate(session, event)
    if anchor is None:
        raise ValueError("fixture has no authorized original reply")
    ancestor = anchor["event"]
    scope = Scope(conversation_id=origin["entry"], generation=origin["observed_generation"])
    now = (frame["occurred"] or frame["observed"]) / 1000
    with closing(SnapshotStore(checkpoint)) as store:
        previous = store.load(scope)
    revision = previous[0] if previous else 0
    controller = Controller.restore(previous[1], now) if previous else Controller(scope, now)
    earlier = scoped_reply(session, controller, anchor, origin)
    ref = source_ref(controller, event, digest)
    focus = scoped(origin, frame, mentions, event, ref, earlier.ref)
    if origin["entry"] != config["entry"]:
        raise ValueError("fixture entry mismatch")
    for original in (earlier, focus):
        if not controller.observe_committed_event(original) and controller.state.events.get(original.ref.event_id) != original:
            raise ValueError("the fixture could not recover an original source")
    snapshot = controller.freeze_observation(Snapshot(
        scope=focus.scope, focus=focus, context=(earlier,), sequence=revision + 1, issued_at=focus.at,
    ))
    admission = {"event": event, "expected_generation": scope.generation}
    apply_rule = earlier.kind == "self" and any(
        mark.kind == "yuki" and mark.presence_id == config["receiver"] for mark in focus.mentions
    )
    rule = session.request("participation.promote", admission) if apply_rule else None
    observations = []
    receipts = []

    def through_host(request):
        native = json.loads(request.content)
        if native.pop("model") != "jev-request-fixture":
            raise ValueError("pinned library selected the wrong request model")
        params = {"origin": {"event": event}, "sources": [ancestor], "route": "review",
                  "purpose": "review", "call_id": "original-native-review", "jev": native}
        receipt = session.request("llm.complete", params)
        if receipt["state"] != "response" or receipt["erased"]:
            raise ValueError("original response unavailable")
        receipts.append(receipt)
        return httpx.Response(200, content=review_payload(session, receipt))

    async with httpx.AsyncClient(transport=httpx.MockTransport(through_host), trust_env=False) as client:
        observer = JevObserver(
            "unused-by-local-transport", identity=lambda: {"display_name": "Yuki", "aliases": ()},
            endpoint="http://127.0.0.1/systemone", request_model="jev-request-fixture",
            response_model="jev-response-fixture", client=client,
        )
        for attempt in range(2):
            result = await observer.evaluate(snapshot)
            if attempt == 0:
                if not controller.apply_semantic_observation(result):
                    raise ValueError("the pinned controller rejected the native observation")
                invited = controller.invitation_current(focus, result.received_at)
            observations.append({
                "model": result.model_revision, "rubric": result.rubric_revision,
                "answers": {key: value.choice for key, value in result.answers.items()},
                "invalid": result.invalid_dimensions, "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            })
    if receipts[0] != receipts[1] or observations[0] != observations[1]:
        raise ValueError("same-key review changed")
    semantic = session.request("participation.promote", admission) if invited else None
    binding = feedback = None
    if rule is not None:
        for _ in range(120):
            feedback = session.request("participation.feedback", {"event": event})
            if any(item["state"] == "completed" for item in feedback["executions"]):
                break
            time.sleep(0.025)
        else:
            raise TimeoutError("ordinary Main feedback")
        binding = UnitBinding(scope=scope, unit=ParticipationUnit(thread=focus.thread, target=focus.author),
                              actor=focus.author, basis=(focus.ref,))
        if not controller.observe_unit_input(binding, focus.ref):
            raise ValueError("the pinned controller rejected the ordinary admission")
    with closing(SnapshotStore(checkpoint)) as store:
        saved = store.save(controller.state, expected_revision=revision)
    with closing(SnapshotStore(checkpoint)) as store:
        recovered = store.load(scope)
    if recovered is None or recovered[0] != saved:
        raise ValueError("the original participation snapshot was lost")
    restored = Controller.restore(recovered[1], focus.at)
    if source_ref(restored, event, digest) != focus.ref:
        raise ValueError("the original source version changed after reopening the checkpoint")
    if binding is not None and focus.ref not in restored.participation_binding_refs():
        raise ValueError("the ordinary source binding was lost")
    return {
        "event": event, "origin": origin, "anchor": anchor,
        "focus": focus.model_dump(mode="json"), "context": earlier.model_dump(mode="json"),
        "receipt": receipts[0],
        "observations": observations, "wire": session.wire, "snapshot_revision": saved,
        "invited": invited, "rule": rule, "semantic": semantic, "feedback": feedback,
        "binding": binding.model_dump(mode="json") if binding is not None else None,
    }


def recover(session, checkpoint, original):
    scope = Scope.model_validate(original["scope"])
    with closing(SnapshotStore(checkpoint)) as store:
        revision, state = store.load(scope)
    item = state.events[original["ref"]["event_id"]]
    controller = Controller.restore(state, item.at)
    if item.ref != SourceRef.model_validate(original["ref"]) or item.ref not in controller.participation_binding_refs():
        raise ValueError("the same human admission must survive cold startup")
    receipt = session.request("llm.complete", original["review"])
    payload = review_payload(session, receipt)
    return {"snapshot_revision": revision, "receipt": receipt,
            "result_sha256": hashlib.sha256(payload).hexdigest(), "ref": item.ref.model_dump(mode="json")}


def main():
    folder = Path(sys.argv[1])
    config = json.loads((folder / "config.json").read_bytes())
    session = Session()
    checkpoint = folder / "checkpoint.sqlite"
    if "recover" in config:
        restored = recover(session, checkpoint, config["recover"])
        pending = folder / "cold-result.tmp"
        pending.write_text(json.dumps(restored, indent=2), encoding="utf-8")
        pending.replace(folder / "cold-result.json")
        for _ in iter(lambda: read_frame(sys.stdin.buffer), None):
            pass
        return
    reviewed = set()
    while session.events or session.receive() is not None:
        if not session.events:
            continue
        notice = session.events.pop(0)
        if notice["entry"] != config["entry"] or notice["kind"] != "message":
            continue
        event = notice["event"]
        if event in reviewed:
            continue
        page = session.request("participation.source", {"event": event, "include_reply": True, "include_self": True})
        if page["reply_to"] is None:
            continue
        outcome = asyncio.run(exercise(session, event, config, checkpoint))
        reviewed.add(event)
        pending = folder / f"result-{event}.tmp"
        pending.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")
        pending.replace(folder / f"result-{event}.json")
        session.wire.clear()


if __name__ == "__main__":
    main()
