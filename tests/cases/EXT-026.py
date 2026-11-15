"""Replay the Rust intrinsic owner and its pinned clock on an exact Host candidate."""

from contextlib import closing
from hashlib import file_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from threading import Thread
import time
from zipfile import ZipFile

from package import build
from participation_semantic import checkpoint_idle
from personal_preview import free_address
from rebuild_intake import Owner, sha
from windows_candidate_replay import load, verify_producer


def prepare(root, output):
    upstream = Path(os.environ["YUKI_PARTICIPATION_SOURCE"]).resolve()
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
        assert {"participation.sources", "participation.self_propose", "participation.feedback"} <= set(candidate["implemented_methods"])
        assert sorted(bundle.namelist()) == sorted(["candidate.json", *candidate["members"]])
        for name, member in candidate["members"].items():
            with bundle.open(name) as file:
                assert file_digest(file, "sha256").hexdigest() == member["sha256"]
        native = "yuki-core.exe" if os.name == "nt" else "yuki-core"
        executable = work / native
        with bundle.open("bin/" + native) as source, executable.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        executable.chmod(0o700)
        with tarfile.open(upstream) as source:
            source.extractall(work, filter="data")
        library_root = work / ("Yuki-Semantic-Participation-" + library["source_commit"])
        sys.path.insert(0, str(library_root / "src"))
        packages = output / "packages"
        package = build(root, "participation", packages)
        worker = packages / ("yuki-participation.exe" if os.name == "nt" else "yuki-participation")
        clock = replay_clock(work, packages / "semantic_bridge.py", upstream)
        result = exercise(root, output, work / "fixture", executable, worker, upstream)
        send_output = output / "confirmed"
        send_output.mkdir()
        delivery = exercise(root, send_output, work / "delivery", executable, worker, upstream, delivery=True)
        assert result["reader"] == host["reader"]
        return "self-tick-diff.json", {
            "status": "PASS", "card_status": "INTRINSIC_CANDIDATE_VERIFIED", "published": False,
            "host": {**host, "archive_sha256": sha(archive), "binary_sha256": sha(executable)},
            "library": library["source_commit"], "worker_sha256": sha(worker),
            "package_manifest_sha256": sha(packages / "package-manifest.json"),
            "worker_version": package["version"], "fixed_clock": clock, "confirmed_delivery": delivery, **result,
        }


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
    inputs = [tick(warm, 5429, False), {"execution": arm, "newly_accepted": True},
              tick(resumed, 5429, True), tick(warm, 5629, True),
              {"scope": "original_execution", "executions": [{"execution": arm, "state": "completed",
                "quiet": True, "cancelled": False, "sends": []}]}]
    process = subprocess.run([sys.executable, "-I", "-B", str(adapter), str(upstream), "--ticks"],
                             input="".join(json.dumps(row) + "\n" for row in inputs), text=True,
                             capture_output=True, check=True, timeout=30)
    frames = [json.loads(line) for line in process.stdout.splitlines()]
    assert [frame["type"] for frame in frames] == ["propose", "done", "done", "feedback", "done"]
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
            "cold_opportunities": 0, "original_work_preserved": True, "terminal_feedback": "no_reply"}


def exercise(root, output, work, executable, worker, upstream, *, delivery=False):
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
            author=person, target="group", text="original group activity", at=at, source_order=event,
        ))
    policy.set_state_entry("host_checkpoint", "autonomy_cursor", max(event_times))
    rate = policy.intrinsic_opportunity(now)
    assert rate > 0
    # Select one deterministic original stream so the live fixture need not
    # wait hours for its next intrinsic opportunity.
    arrival = -math.expm1(-rate * 0.5)
    seed = next(number for number in range(1, 3000000)
                if policy._sample(number, "arrival") < arrival
                and all(policy._sample(number + shift, "arrival") > .2 for shift in range(1, 8)))
    policy._set(sample_sequence=seed - 1)
    with closing(SnapshotStore(checkpoint)) as store:
        store.save(policy.state, expected_revision=0)

    def query(statement, *args):
        with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute(statement, args).fetchall()

    def wait(probe, timeout=24):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if result := probe():
                return result
            time.sleep(.05)
        raise TimeoutError("intrinsic SELF fixture did not settle")

    def ready(mode):
        return query("SELECT online FROM host_installations WHERE plugin=?", f"participation-{mode}") == [(1,)]

    def snapshot():
        with closing(SnapshotStore(checkpoint)) as store:
            return store.load(scope)[1]

    def original_proposals():
        return query("SELECT proposal,execution FROM participation_proposals ORDER BY proposal")

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

            other_modes = () if delivery else ("off", "legacy")
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
                        peer.send({"echo": frame["echo"], "status": "ok", "retcode": 0,
                                   "data": {"message_id": 75691}})
                wait(original_proposals)
                [(proposal, execution)] = original_proposals()
                assert query("SELECT source,original_actor FROM executions WHERE id=?", execution) == [(None, None)]
                if not delivery:
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
    assert proposals[0]["key"] == proposal and "sources" not in proposals[0]
    lost = [row["frame"]["result"] for row in frames if row.get("forwarded") is False]
    assert lost == ([] if delivery else [{"execution": execution, "newly_accepted": True}])
    recovery = [row["frame"]["params"] for row in frames if row["direction"] == "from_plugin"
                and row["frame"].get("method") == "participation.feedback"]
    assert {"key": proposal, "allow_missing_proposal": True} in recovery
    assert query("SELECT id FROM events WHERE raw_actor=? ORDER BY id", person) == [
        (event,) for event in event_times
    ]
    observed_sends = query("SELECT locator FROM social_outbound WHERE namespace=?", execution)
    assert observed_sends == ([("75691",)] if delivery else [])
    return {"reader": reader, "owner_modes": [*other_modes, "semantic"], "seed_draw": seed,
            "original_human_events": len(event_times), "new_human_events": 0, "main_attempts": len(calls),
            "paid_calls": 0, "proposal": proposal, "original_work": execution, "terminal_feedback": terminal,
            "confirmed_locators": [row[0] for row in observed_sends],
            "lost_admission_reply": lost, "cold_new_attempts": 0,
            "wire_frames": len(frames), "wire_sha256": sha(trace)}
