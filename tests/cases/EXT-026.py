"""Replay the Rust SELF owner and its pinned clock on an exact Host candidate."""

from contextlib import closing
from hashlib import file_digest, sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import platform
import runpy
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from threading import Thread
import time
from zipfile import ZipFile

from maintenance_release_check import checked_member, unpack_worker
from package import build
from participation_rule import run as replay_rule
from participation_semantic import run as replay_semantic
from participation_semantic import checkpoint_idle
from personal_preview import free_address
from rebuild_intake import Owner, sha
from windows_candidate_replay import load, verify_producer


SELF_METHODS = {"participation.sources", "participation.self_propose", "participation.feedback"}
STABLE_TAG = "plugin/participation/v0.2.0"
STABLE_CONTRACT = "compat/stable-1.4/source.lock.json"


def prepare(root, output):
    upstream = Path(os.environ["YUKI_PARTICIPATION_SOURCE"]).resolve()
    if stable_host := os.environ.get("YUKI_PARTICIPATION_STABLE_HOST"):
        return stable_replay(root, output, Path(stable_host).resolve(strict=True), upstream)
    archive = Path(os.environ["YUKI_CORE050_CANDIDATE"])
    manifest = Path(os.environ["YUKI_CORE050_MANIFEST"])
    pins = root / "compat/participation-library"
    library = json.loads((pins / "source.lock.json").read_bytes())
    host = json.loads((pins / "native-host.lock.json").read_bytes())
    assert sha(upstream) == library["source_sha256"]
    with TemporaryDirectory(prefix="ext026-") as directory, ZipFile(archive) as bundle:
        work = Path(directory)
        candidate = json.loads(bundle.read("candidate.json"))
        verify_producer(manifest, candidate, "CORE-050")
        assert candidate["status"] == host["status"] and candidate["source_commit"] == host["commit"]
        assert candidate["source_tree_sha256"] == host["tree_sha256"]
        assert candidate["host_schema_sha256"] == host["host_schema_sha256"]
        assert candidate["sdk_versions"] == host["sdk_versions"]
        assert SELF_METHODS <= set(candidate["implemented_methods"])
        assert sorted(bundle.namelist()) == sorted(["candidate.json", *candidate["members"]])
        for name, member in candidate["members"].items():
            with bundle.open(name) as file:
                assert file_digest(file, "sha256").hexdigest() == member["sha256"]
        native = "yuki-core.exe" if os.name == "nt" else "yuki-core"
        executable = work / native
        with bundle.open("bin/" + native) as source, executable.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        executable.chmod(0o700)
        packages = output / "packages"
        package = build(root, "participation", packages)
        worker = packages / ("yuki-participation.exe" if os.name == "nt" else "yuki-participation")
        replays = replay_package(root, output, work, executable, worker, upstream, library, host["reader"])
        return "self-tick-diff.json", {
            "status": "PASS", "card_status": "SELF_CANDIDATE_VERIFIED", "published": False,
            "host": {**host, "archive_sha256": sha(archive), "binary_sha256": sha(executable)},
            "library": library["source_commit"], "worker_sha256": sha(worker),
            "package_manifest_sha256": sha(packages / "package-manifest.json"),
            "worker_version": package["version"], **replays,
        }


def replay_package(root, output, work, executable, worker, upstream, library, reader):
    with tarfile.open(upstream) as source:
        source.extractall(work, filter="data")
    library_root = work / ("Yuki-Semantic-Participation-" + library["source_commit"])
    sys.path.insert(0, str(library_root / "src"))
    try:
        clock = replay_clock(work, worker.with_name("semantic_bridge.py"), upstream)
        intrinsic = exercise(root, output, work / "fixture", executable, worker, upstream)
        send_output = output / "confirmed"
        send_output.mkdir()
        delivery = exercise(root, send_output, work / "delivery", executable, worker, upstream, delivery=True)
        source_output = output / "conversation"
        source_output.mkdir()
        conversation = exercise(root, source_output, work / "conversation", executable, worker, upstream, conversation=True)
        assert intrinsic["reader"] == delivery["reader"] == conversation["reader"] == reader
        return {"fixed_clock": clock, "confirmed_delivery": delivery, "conversation": conversation, **intrinsic}
    finally:
        sys.path.remove(str(library_root / "src"))


def stable_replay(root, output, archive, upstream, published_plugin=None):
    host = json.loads((root / STABLE_CONTRACT).read_bytes())
    expected_bundle = host["asset_sha256"]["yuki-plugin-base-1.4.0.zip"]
    if not host["published"] or sha(archive) != expected_bundle:
        raise ValueError("Published Plugin Base 1.4.0 archive required")
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    record = json.loads((root / "releases/participation/0.2.0/qualification.json").read_bytes())
    library = json.loads((root / "compat/participation-library/source.lock.json").read_bytes())
    assert sha(upstream) == library["source_sha256"]
    packages = output / "packages"
    if published_plugin is None:
        prepare_release = runpy.run_path(str(root / "ci/publish-plugin.py"))["prepare"]
        package = prepare_release(root, STABLE_TAG, packages, candidate=record)
    else:
        release = json.loads((root / "compat/participation-0.2.0/release.lock.json").read_bytes())
        asset = release["platforms"][system]
        if (release["status"] != "published-and-downloaded" or release["tag"] != STABLE_TAG
                or release["host"]["archive_sha256"] != expected_bundle
                or release["host"]["source_commit"] != host["source_commit"]
                or release["sdk"]["version"] != host["sdk"]["rust"]
                or release["sdk"]["sha256"] != host["rust_crate_sha256"]
                or sha(published_plugin) != asset["sha256"]):
            raise ValueError("Published participation package differs from its release lock")
        package = unpack_worker(published_plugin.read_bytes(), packages, system, "0.2.0", unit_id="participation")
        binary = "yuki-participation.exe" if system == "windows" else "yuki-participation"
        if package["artifacts"][binary] != asset["worker_sha256"]:
            raise ValueError("Published participation worker differs from its release lock")
    inputs_digest = sha256(json.dumps(record["inputs"], sort_keys=True).encode()).hexdigest()
    if (package["version"] != "0.2.0" or package["release_tag"] != STABLE_TAG
            or package["source"]["sdk_contract"] != STABLE_CONTRACT
            or package["source"]["release_inputs_sha256"] != inputs_digest
            or json.loads((packages / "source.lock.json").read_bytes()) != library):
        raise ValueError("Participation package uses different release inputs")
    worker = packages / ("yuki-participation.exe" if system == "windows" else "yuki-participation")
    assert sha(worker) == package["artifacts"][worker.name]
    bundled_host = host["assets"]["host-" + system]
    with TemporaryDirectory(prefix="ext026-stable-", dir="/tmp" if system != "windows" else None) as directory:
        work = Path(directory)
        executable = work / Path(bundled_host["path"]).name
        with ZipFile(archive) as bundle:
            executable.write_bytes(checked_member(bundle, bundled_host))
            for role in ("rust-sdk", "python-sdk"):
                checked_member(bundle, host["assets"][role])
        executable.chmod(0o700)
        surface = json.loads(subprocess.check_output([executable, "plugin-surface"], timeout=20))
        if (surface["version"] != host["sdk"]["rust"] or surface["candidate_source"] != host["source_commit"]
                or surface["surface_sha256"] != host["surface_sha256"] or not surface["selected_by_default"]
                or not SELF_METHODS.issubset(surface["methods"])):
            raise ValueError("Published Host surface differs from its pin")
        result = replay_package(root, output, work, executable, worker, upstream, library, host["database_reader"])
        rule_out = output / "ordinary-rule"
        review_out = output / "ordinary-review"
        rule_out.mkdir()
        review_out.mkdir()
        rule = replay_rule(work / "rule", executable, worker, rule_out)
        review = replay_semantic(work / "review", executable, worker, packages / "semantic_bridge.py", upstream, review_out)
    result.update(
        status="PASS", card_status="PASS" if published_plugin else "RELEASE_CANDIDATE_VERIFIED",
        tag=STABLE_TAG, published=published_plugin is not None, platform=system, worker_version=package["version"],
        host={"published": True, "tag": host["tag"], "source_commit": host["source_commit"],
              "archive_sha256": expected_bundle, "binary_sha256": bundled_host["sha256"],
              "surface_sha256": host["surface_sha256"], "reader": host["database_reader"]},
        sdk={"versions": host["sdk"], "rust_sha256": host["rust_crate_sha256"]},
        library=library["source_commit"], worker_sha256=sha(worker),
        package_manifest_sha256=sha(packages / "package-manifest.json"), release_inputs_sha256=inputs_digest,
        ordinary_rule=rule, ordinary_review=review,
    )
    if published_plugin:
        result.update(release_package_sha256=sha(published_plugin), release_source_commit=release["source_commit"])
    return "self-tick-diff.json", result


def run(root, output):
    return stable_replay(
        root, output, Path(os.environ["YUKI_PARTICIPATION_STABLE_HOST"]).resolve(strict=True),
        Path(os.environ["YUKI_PARTICIPATION_SOURCE"]).resolve(strict=True),
        Path(os.environ["YUKI_PARTICIPATION_RELEASE"]).resolve(strict=True),
    )


def observation(focus, sequence, issued, received, context=(), *, stop=False):
    from yuki_participation.models import Choice, Observation, Snapshot
    from yuki_participation.rubric import CRITERIA, REVISION

    choices = {"interaction_mark": "ask_yuki_stop" if stop else "open_group",
               "floor_state": "other" if stop else "open", "information_state": "new",
               "boundary_scope": "group_thread" if stop else "target_thread"}
    return Observation(
        observation_id=f"original-fixture-{sequence}", snapshot=Snapshot(
            scope=focus.scope, focus=focus, context=context, sequence=sequence, issued_at=issued,
        ), received_at=received, provider="fixture", model_revision="fixture", rubric_revision=REVISION,
        answers={key: Choice(choice=choice, probabilities={option: float(option == choice)
                 for option in CRITERIA[key]}) for key, choice in choices.items()},
    )


def replay_clock(work, adapter, upstream):
    from yuki_participation.controller import Controller
    from yuki_participation.models import CandidateKind, Scope, ScopedEvent, SourceRef
    from yuki_participation.store import SnapshotStore

    scope = Scope(conversation_id="ext026-clock-reference", generation=3)
    original = Controller(scope, 100)
    for ordinal in range(1, 36):
        key = f"event:{ordinal}"
        assert original.observe_committed_event(ScopedEvent(
            scope=scope, ref=SourceRef(event_id=key, revision=1), thread=key,
            author="original-member", target="group", text="fixed local input",
            at=100 + ordinal, source_order=ordinal,
        ))
    original.advance(135, controller_epoch=0, host_available=False)
    for now in range(137, 5429, 2):
        assert original.advance(now, controller_epoch=0, host_available=True, intrinsic_allowed=True,
                                include_addressed=False, allowed_kinds=frozenset()) is None
    warm = work / "warm.sqlite"
    resumed = work / "resumed.sqlite"
    for path in (warm, resumed):
        with closing(SnapshotStore(path)) as store:
            store.save(original.state, expected_revision=0)
    proposal = original.advance(5429, controller_epoch=0, host_available=True, intrinsic_allowed=True,
                                include_addressed=False, allowed_kinds=frozenset())
    assert proposal.kind is CandidateKind.INTRINSIC and not proposal.sources

    def tick(checkpoint, at, cold):
        return {"action": "tick", "checkpoint": str(checkpoint), "entry": scope.conversation_id,
                "generation": scope.generation, "receiver": "fixed-scene", "now": at,
                "resumed": cold, "can_sample": not cold, "sources": [], "next": 0}

    arm = "original-fixed-work"
    quiet = work / "quiet.sqlite"
    stopped = Controller(scope, 7000)
    focus, stop = (
        ScopedEvent(scope=scope, ref=SourceRef(event_id=f"event:{event}", revision=1), thread="original",
                    author="original-member", target="original-member", text=text, at=at, source_order=event)
        for event, text, at in ((36, "prior opportunity", 6980), (37, "stop participating", 6995))
    )
    for event in (focus, stop):
        assert stopped.observe_committed_event(event)
    assert stopped.apply_semantic_observation(observation(stop, 2, 6995, 6995, stop=True))
    assert stopped.apply_semantic_observation(observation(focus, 1, 6981, 7001))
    assert any(boundary.explicit_stop and boundary.group_wide and boundary.released_by is None
               for boundary in stopped.state.boundaries.values())
    assert not stopped.opportunity_scores(7002, include_addressed=False)
    with closing(SnapshotStore(quiet)) as store:
        store.save(stopped.state, expected_revision=0)
    inputs = [tick(warm, 5429, False), {"execution": arm, "newly_accepted": True},
              tick(resumed, 5429, True), tick(warm, 5629, True),
              {"scope": "original_execution", "executions": [{"execution": arm, "state": "completed",
                "quiet": True, "cancelled": False, "sends": []}]}, tick(quiet, 7002, False)]
    process = subprocess.run([sys.executable, "-I", "-B", str(adapter), str(upstream), "--ticks"],
                             input="".join(json.dumps(row) + "\n" for row in inputs), text=True,
                             capture_output=True, check=True, timeout=30)
    frames = [json.loads(line) for line in process.stdout.splitlines()]
    assert [frame["type"] for frame in frames] == ["propose", "done", "done", "feedback", "done", "done"]
    assert frames[0]["kind"] == proposal.kind and frames[3]["key"] == frames[0]["key"]
    with closing(SnapshotStore(warm)) as store:
        _, state = store.load(scope)
    assert state.proposal_runs == {frames[0]["key"]: arm} and state.pending is None
    assert state.sample_sequence == original.state.sample_sequence
    assert state.feedback[arm].outcome == "no_reply"
    with closing(SnapshotStore(resumed)) as store:
        _, cold = store.load(scope)
    assert cold.pending is None and not cold.proposals and cold.last_sample_at == 5429
    return {"first_proposal_at": 5429, "seed_draw": original.state.sample_sequence,
            "cold_opportunities": 0, "original_work_preserved": True, "terminal_feedback": "no_reply",
            "late_opportunities_after_group_stop": 0}


def exercise(root, output, work, executable, worker, upstream, *, delivery=False, conversation=False):
    from yuki_participation.controller import Controller
    from yuki_participation.models import Scope, ScopedEvent, SourceRef
    from yuki_participation.store import SnapshotStore

    owner = Owner(work, executable, output)
    config = owner.data / "yuki.toml"
    checkpoint = work / "self.sqlite"
    trace = output / "self-wire.jsonl"
    space = '["qq","self-fixture","756"]'
    person = "00000000-0000-4000-8000-000000000026"
    address = free_address()
    baseline = config.read_text(encoding="utf-8").replace('"127.0.0.1:0"', json.dumps(address), 1)
    token = "deterministic-qq-fixture"

    def query(statement, *args):
        with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute(statement, args).fetchall()

    with owner.running():
        entry = owner.op("entry", "group", space)["entry"]
        owner.op("person", "create", person)
        author = owner.op("account", "open", "qq", "self-fixture", "200", 1,
                          "--person", person, "--start", 1)
        bot = owner.op("account", "open", "qq", "self-fixture", "100", 1, "--start", 1)
        event_times = {}
        now = time.time()
        for number in range(1, 36):
            at = int((now - 600 + number) * 1000)
            if conversation and number >= 34:
                at = int((now - 21 + number - 34) * 1000)
            packet = {"source": f"old-{number}", "native_id": f"756{number:02}", "account": author["account"],
                      "bot_stage": bot["assignment"], "reply_bot": "100", "space": space, "kind": "message",
                      "observed": at, "occurred": at,
                      "segments": [{"type": "text", "text": "original group activity"}]}
            event = owner.op("ingress", "record", json.dumps(packet))["event"]
            event_times[event] = at / 1000

    scope = Scope(conversation_id=entry, generation=1)
    policy = Controller(scope, now)
    for event, at in event_times.items():
        key = f"event:{event}"
        assert policy.observe_committed_event(ScopedEvent(
            scope=scope, ref=SourceRef(event_id=key, revision=1), thread=key,
            author=person, target=person, text="original group activity", at=at, source_order=event,
        ))
    policy.set_state_entry("host_checkpoint", "autonomy_cursor", max(event_times))
    selected = []
    guard = []
    own_rate = policy.intrinsic_opportunity(now + 10)
    rate = own_rate
    if conversation:
        prior_id, focus_id = list(event_times)[-2:]
        prior, focus = (policy.state.events[f"event:{event}"] for event in (prior_id, focus_id))
        assert policy.apply_semantic_observation(observation(focus, 1, now - 18, now - 12, (prior,)))
        selected = [focus_id]
        for event in (focus_id, prior_id):
            [(envelope,)] = query("SELECT envelope FROM events WHERE id=?", event)
            wire = json.dumps(json.loads(envelope), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            version = sha256(wire.encode()).hexdigest()
            policy.set_host_mapping_entry("source_versions", f"event:{event}", [1, version])
            guard.append({"event": event, "version": version})
        rate += policy.opportunity_scores(now + 10, include_addressed=False)[focus.ref.event_id]
        assert rate > own_rate
    assert rate > 0
    # Select one deterministic original stream so the live fixture need not
    # wait hours for its next intrinsic opportunity.
    arrival = -math.expm1(-rate * 0.5)
    seed = next(number for number in range(1, 3000000)
                if policy._sample(number, "arrival") < arrival
                and (not conversation or policy._sample(number, "selection") * rate > own_rate)
                and all(policy._sample(number + shift, "arrival") > .2 for shift in range(1, 8)))
    policy._set(sample_sequence=seed - 1)
    with closing(SnapshotStore(checkpoint)) as store:
        store.save(policy.state, expected_revision=0)

    def wait(probe, timeout=24):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result := probe():
                return result
            time.sleep(.05)
        raise TimeoutError("SELF fixture did not settle")

    def ready(mode):
        return query("SELECT online FROM host_installations WHERE plugin=?", f"participation-{mode}") == [(1,)]

    def snapshot():
        with closing(SnapshotStore(checkpoint)) as store:
            return store.load(scope)[1]

    def original_proposals():
        return query("SELECT proposal,execution FROM participation_proposals ORDER BY proposal")

    def admission():
        [(proposal, execution)] = wait(original_proposals)
        assert query("SELECT source,original_actor FROM executions WHERE id=?", execution) == [(None, None)]
        assert query("SELECT event FROM main_dependencies WHERE execution=? ORDER BY event", execution) == [
            (event,) for event in sorted(item["event"] for item in guard)
        ]
        [(material,)] = query("SELECT material FROM main_turns WHERE execution=?", execution)
        assert [item["event"] for item in json.loads(material)["context"]] == selected
        return proposal, execution

    calls = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.path == "/main"
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            choice = {"message": {"role": "assistant", "content": "quiet"}, "finish_reason": "stop"}
            if delivery and len(calls) == 1:
                choice = {"message": {"role": "assistant", "content": None, "tool_calls": [
                    {"id": "self-send", "type": "function", "function": {
                        "name": "send", "arguments": json.dumps({"text": "original intrinsic delivery"}),
                    }},
                ]}, "finish_reason": "tool_calls"}
            reply = json.dumps({"choices": [choice],
                                "usage": {"prompt_tokens": 11, "completion_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

    with ThreadingHTTPServer(("127.0.0.1", 0), Model) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            owner.env["YUKI_SELF_FIXTURE_QQ"] = token
            common = (
                '\n[main]\nendpoint=' + json.dumps(f"http://127.0.0.1:{server.server_port}/main")
                + '\nmodel="self-fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=2\n'
                'max_input_units=200000\nmax_output=128\n'
                '[qq]\nnamespace="self-fixture"\ndesignated_ingress="100"\n'
                '[qq.groups]\n"756"="observe"\n[[qq.bots]]\nself_id="100"\nstage='
                + json.dumps(bot["assignment"]) + '\ntoken_env="YUKI_SELF_FIXTURE_QQ"\n'
            )
            relay = root / "tests/peers/observe_stdio.py"
            drop_reply = work / "drop-self-admission-reply"
            args = [str(relay), str(worker), str(trace), "--cut-self-reply", str(drop_reply),
                    entry, bot["assignment"], "--review", sys.executable,
                    str(worker.with_name("semantic_bridge.py")), str(upstream), str(checkpoint),
                    "unused-intrinsic-fixture", "unused-intrinsic-fixture", "Yuki", "--owner"]

            def install(mode):
                config.write_text(baseline + common +
                    '\n[[plugins]]\nid=' + json.dumps(f"participation-{mode}")
                    + '\nnamespace=' + json.dumps(f"participation-{mode}") + '\nprogram='
                    + json.dumps(sys.executable) + '\nargs=' + json.dumps([*args, mode])
                    + '\ngrants=["observe.metadata","participation.source","participation.sources",'
                    '"participation.self_propose","participation.feedback","forget.owner"]\n'
                    '[plugins.participation]\nentries=' + json.dumps([entry])
                    + '\n[plugins.participation.self_scenes]\n' + json.dumps(entry) + '='
                    + json.dumps(bot["assignment"]) + '\n', encoding="utf-8")

            other_modes = () if delivery or conversation else ("off", "legacy")
            for mode in other_modes:
                install(mode)
                with owner.running():
                    wait(lambda: ready(mode))
                    time.sleep(2.25)
                    assert not original_proposals() and not calls
                wait(lambda: checkpoint_idle(checkpoint))

            install("semantic")
            if not delivery:
                drop_reply.touch()
            expected_calls = 2 if delivery else 1
            terminal = "completed" if delivery else "no_reply"
            with owner.running():
                wait(lambda: ready("semantic"))
                reader = owner.op("database-info")["schema_version"]
                if delivery:
                    peer_type = load(root / "tests/peers/subscription_onebot.py").Peer
                    with closing(peer_type(address, "100", token)) as peer:
                        peer.socket.settimeout(16)
                        frame = peer.receive()
                        assert frame["action"] == "send_group_msg"
                        assert str(frame["params"]["group_id"]) == "756"
                        assert "original intrinsic delivery" in str(frame["params"]["message"])
                        # A confirmed delivery can add its own dependency after admission.
                        proposal, execution = admission()
                        peer.send({"echo": frame["echo"], "status": "ok", "retcode": 0,
                                   "data": {"message_id": 75691}})
                else:
                    proposal, execution = admission()
                    wait(lambda: not drop_reply.exists())
                    assert snapshot().pending == proposal and execution not in snapshot().feedback
                wait(lambda: query("SELECT id FROM executions WHERE id=? AND state='completed'", execution))
                if delivery:
                    wait(lambda: any(effect.run_ref == execution and effect.effect.kind == "message"
                                     for effect in snapshot().effects.values()))
                assert len(calls) == expected_calls
                assert not query("SELECT event_id FROM accepted_sources")

            wait(lambda: checkpoint_idle(checkpoint))
            with owner.running():
                wait(lambda: ready("semantic"))
                completed = wait(lambda: (row if (row := snapshot().feedback.get(execution))
                                         and row.outcome == terminal else None))
                assert completed.proposal_id == proposal and snapshot().pending is None
                time.sleep(4.25)
                assert original_proposals() == [(proposal, execution)] and len(calls) == expected_calls
                assert snapshot().feedback[execution].outcome == terminal
        finally:
            server.shutdown()
            thread.join()

    frames = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    proposals = [row["frame"]["params"] for row in frames if row["direction"] == "from_plugin"
                 and row["frame"].get("method") == "participation.self_propose"]
    assert len(proposals) == 1 and proposals[0]["expected_generation"] == 1
    assert proposals[0]["key"] == proposal
    assert proposals[0].get("sources", []) == selected and proposals[0].get("source_guard", []) == guard
    lost = [row["frame"]["result"] for row in frames if row.get("forwarded") is False]
    assert lost == ([] if delivery else [{"execution": execution, "newly_accepted": True}])
    recovery = [row["frame"]["params"] for row in frames if row["direction"] == "from_plugin"
                and row["frame"].get("method") == "participation.feedback"]
    assert {"key": proposal, "allow_missing_proposal": True, "include_delivery_time": True} in recovery
    assert query("SELECT id FROM events WHERE raw_actor=? ORDER BY id", person) == [
        (event,) for event in event_times
    ]
    observed_sends = query("SELECT locator,observed_at FROM social_outbound WHERE namespace=?", execution)
    assert [row[0] for row in observed_sends] == (["75691"] if delivery else [])
    original_confirmation = observed_sends[0][1] if delivery else None
    confirmed_effects = [row.effect.at for row in snapshot().effects.values()
                         if row.run_ref == execution and row.effect.kind == "message"]
    assert confirmed_effects == ([original_confirmation / 1000] if delivery else [])
    return {"reader": reader, "owner_modes": [*other_modes, "semantic"], "seed_draw": seed,
            "original_human_events": len(event_times), "new_human_events": 0, "main_attempts": len(calls),
            "paid_calls": 0, "proposal": proposal, "original_work": execution, "terminal_feedback": terminal,
            "confirmed_locators": [row[0] for row in observed_sends],
            "original_confirmation_ms": original_confirmation,
            "selected_sources": selected, "source_guard": guard,
            "lost_admission_reply": lost, "cold_new_attempts": 0,
            "wire_frames": len(frames), "wire_sha256": sha(trace)}
