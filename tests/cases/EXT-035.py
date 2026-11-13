"""Run the Rust event reflection worker against pinned CORE-035 and CORE-050."""

from contextlib import closing, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import tomllib

from package import build
from rebuild_intake import ACTOR, wait_for, write


@contextmanager
def model_peer():
    observations = []
    control = {"mode": "active", "actions": []}
    accepted = threading.Event()
    release = threading.Event()

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            mode = control["mode"]
            observations.append({"route": self.path, "mode": mode, "wire": body})
            if mode == "unknown":
                self.close_connection = True
                return
            if mode == "held":
                accepted.set()
                assert release.wait(15)
            data = json.dumps({
                "choices": [{"message": {"role": "assistant",
                                         "content": json.dumps({"actions": control["actions"]}, ensure_ascii=False)},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
            }).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except ConnectionError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, control, observations, accepted, release
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join()


def configure(owner, root, binary, trace, entry, port, declaration):
    methods = [name for name in declaration["grants"] if name.startswith("maintenance.")]
    args = [str(root/"tests/peers/rebuild_stdio.py"), str(binary), str(trace),
            str(owner.control), declaration["args"][0]]
    fields = {"id": declaration["id"], "namespace": declaration["id"], "program": sys.executable,
              "args": args, "erasure_args": args, "env": declaration["env"], "grants": declaration["grants"]}
    policy = "\n[[plugins]]\n" + "\n".join(f"{key}={json.dumps(value)}" for key, value in fields.items())
    policy += (f'\n[plugins.maintenance.scopes.own]\nactor="{ACTOR}"\nentry="{entry}"\n'
               f'methods={json.dumps(methods)}\npurposes=["reflect"]\nroutes=["review"]\n'
               f'write_subject={{kind="self",visibility="private",entry="{entry}"}}\n'
               '\n[plugins.aux_routes.review]\npurposes=["reflect"]\norigins=["maintenance"]\n'
               f'entries=["{entry}"]\n[plugins.aux_routes.review.profile]\n'
               f'endpoint="http://127.0.0.1:{port}/model"\nmodel="reflection-fixture"\n'
               'name="Reflection fixture"\nmerge_ms=0\nroot_slots=1\n'
               'max_input_units=1000000\nmax_output=1024\n')
    with (owner.data/"yuki.toml").open("a", encoding="utf-8") as config:
        config.write(policy)


def exercise(peer, root, working, output, host, binary, declaration):
    class Worker(peer.Worker):
        def submit(self, name, action, batch="first-batch", **args):
            tmp = self.jobs / (name + ".tmp")
            write(tmp, {"action": "reflection." + action, "batch": batch, **args})
            tmp.rename(self.jobs / (name + ".job"))

        def rows(self, sql, *args):
            with closing(sqlite3.connect((self.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                return db.execute(sql, args).fetchall()

    def until(predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if value := predicate():
                return value
            time.sleep(.04)
        raise TimeoutError("reflection did not reach expected barrier")

    owner = Worker(working, output, host, binary, root, declaration)
    primary_text = "original reflection canary takes exact notes"
    context_text = "earlier scene for continuity only"
    delayed_text = "late erasure strikes this original source"
    texts = [primary_text, context_text, "other input with no lesson", delayed_text,
             "unanswered original model request", "foreign entry"]
    with owner.running():
        owner.op("person", "create", ACTOR)
        user = owner.op("account", "open", "qq", "reflection-fixture", "200", 1, "--person", ACTOR, "--start", 1)
        bot = owner.op("account", "open", "qq", "reflection-fixture", "100", 1, "--start", 1)
        entry = owner.op("entry", "private", user["assignment"], bot["assignment"])["entry"]
        space = '["qq","reflection-fixture","701"]'
        foreign_entry = owner.op("entry", "group", space)["entry"]
        events = []
        for sequence, text in enumerate(texts, 1):
            frame = {"source": f"reflection-{sequence}", "account": user["account"],
                     "bot_stage": bot["assignment"], "reply_bot": "100", "kind": "message",
                     "occurred": 100 * sequence, "observed": 100 * sequence,
                     "segments": [{"type": "text", "text": text}]}
            if sequence == len(texts):
                frame["space"] = space
            events.append(owner.op("ingress", "record", json.dumps(frame), "--accept")["event"])
        assert owner.rows("SELECT entry_id FROM events WHERE id=?", events[-1]) == [(foreign_entry,)]
    primary, context, no_op, delayed, unknown, foreign = events

    trace = output / "wire.jsonl"
    with model_peer() as (port, model, requests, accepted, release):
        configure(owner, root, binary, trace, entry, port, declaration)

        def plan(source, background=()):
            return {"scope": "own", "route": "review", "events": [source], "context": list(background)}

        def action(key, source, quote, visibility="private"):
            scope = {"kind": "self", "visibility": visibility}
            if visibility == "private":
                scope["entry"] = entry
            return {"action": "add", "subject": scope, "fact_key": key,
                    "body": "retain the original scoped lesson",
                    "evidence": [{"kind": "event", "id": source, "quote": quote}]}

        def state(batch):
            return json.loads((owner.jobs / f"reflection-{batch}/state.json").read_bytes())

        def frames(method):
            records = [json.loads(line) for line in trace.read_bytes().splitlines(keepends=True)
                       if line.endswith(b"\n")]
            return [row["frame"]["params"] for row in records
                    if row["direction"] == "from_plugin" and row["frame"].get("method") == method]

        def erase(source, key):
            receipt = owner.op("privacy", "erase", key, ACTOR, json.dumps([source]))
            until(lambda: not owner.op("privacy", "pending", declaration["id"])["obligations"])
            return receipt

        original = plan(primary, [context])
        cases = {}
        with owner.running():
            owner.online()
            result = owner.job("foreign-source", "run", batch="foreign", plan=plan(foreign))
            assert result["state"] == "not_completed" and not requests
            model["actions"] = [action("own-lesson", primary, primary_text)]
            (owner.control / "kill-model-call").write_text("first-batch", encoding="utf-8")
            owner.submit("before-model-ack", "run", plan=original)
            cases["paid_before_kill"] = wait_for(owner.control/"model-paid-before-kill.json")["result"]
            assert cases["paid_before_kill"]["state"] in {"response", "paired"}
            assert state("first-batch")["phase"]["phase"] == "prepared"
            assert not (owner.jobs/"before-model-ack.result").exists() and not owner.facts()
            assert len(requests) == 1 and requests[0]["route"] == "/model"
            assert primary_text in str(requests[0]["wire"]) and context_text in str(requests[0]["wire"])
        with owner.running():
            owner.online()
            cases["after_restart"] = peer.completed(owner.job("recover-model-ack", "run", plan=original))
            assert cases["after_restart"]["request"] == cases["paid_before_kill"]["request"]
            assert len(cases["after_restart"]["receipts"]["applied"]) == 1
            assert len(requests) == 1 and owner.facts() == [("own-lesson",1)]
            assert owner.rows("SELECT kind,visibility,visibility_entry FROM memory_facts") == [("self","private",entry)]
            assert owner.rows("SELECT event,quote FROM memory_evidence") == [(primary,primary_text)]
            changed = owner.job("changed-input", "run", plan=plan(primary))
            assert changed["state"] == "not_completed" and len(requests) == 1
            recovered = owner.job("same-input", "run", plan=original)
            assert peer.completed(recovered) == cases["after_restart"] and len(requests) == 1

            for name, model_action, expected in [
                ("global", action("leak-global", primary, primary_text, "global"), 2),
                ("context", action("context-imposter", context, context_text), 3),
            ]:
                model["actions"] = [model_action]
                unsupported = owner.job(name, "run", batch=name, plan=original)
                assert unsupported["state"] == "not_completed" and len(requests) == expected
                assert owner.facts() == [("own-lesson",1)]
            model["actions"] = []
            cases["empty"] = peer.completed(owner.job("empty", "run", batch="empty", plan=plan(no_op)))
            assert cases["empty"]["receipts"]["applied"] == [] and len(requests) == 4

            model["mode"] = "unknown"
            unresolved = owner.job("unknown-model", "run", batch="unknown", plan=plan(unknown))
            assert unresolved["state"] == "not_completed" and len(requests) == 5
            cases["unknown"] = peer.completed(owner.job("unknown-status", "status", batch="unknown"))
            assert cases["unknown"]["phase"] == "requested"
            denied = owner.job("unknown-recover", "run", batch="unknown", plan=plan(unknown))
            assert denied["state"] == "not_completed" and len(requests) == 5
            assert len([f for f in frames("llm.complete") if f["call_id"] == "unknown"]) == 1

            model.update(mode="held", actions=[action("false-late-lesson", delayed, delayed_text)])
            owner.submit("late-model", "run", batch="late", plan=plan(delayed))
            assert accepted.wait(12)
            cases["erase_late"] = erase(delayed, "reflection-late")
            release.set()
            until(lambda: owner.rows("SELECT id FROM model_attempts WHERE diagnostic='source_erased' "
                                     "AND json_extract(usage_json,'$.total')=12"))
            assert not (owner.jobs/"late-model.job").exists()
            assert not (owner.jobs/"late-model.result").exists()
            assert state("late")["phase"]["phase"] == "erased"
            assert owner.facts() == [("own-lesson",1)]
            assert len(requests) == 6

        with owner.running():
            owner.online()
            cases["erase_retained"] = erase(primary, "reflection-source")
            assert not (owner.jobs/"recover-model-ack.result").exists()
            assert (owner.jobs/"empty.result").exists()
            assert state("first-batch")["plan"] is None
            assert owner.rows("SELECT status FROM memory_facts") == [("erased",)]
            assert len(owner.rows("SELECT id FROM model_attempts")) == 6
        with owner.running():
            owner.online()
            erased = peer.completed(owner.job("erased-batch-resubmitted", "run", plan=original))
            assert erased == {"phase":"erased"} and len(requests) == 6
            assert not (owner.jobs/"erased-batch-resubmitted.job").exists()

        cases["provider_observations"] = [
            {"mode": row["mode"], "route": row["route"]} for row in requests
        ]
        cases["original_model_callback_count"] = len(frames("llm.complete"))
        cases["original_physical_attempts"] = len(requests)
        cases["foreign_entry_rejected_before_model"] = True
        cases["private_global_and_context_writes_rejected"] = True
        cases["erased_batch_resubmission_refused"] = True
        return cases


def exercise_tool_receipts(peer, root, working, output, host, binary, declaration):
    class Worker(peer.Worker):
        def submit(self, name, action, batch, **args):
            pending = self.jobs / (name + ".tmp")
            write(pending, {"action": "reflection." + action, "batch": batch, **args})
            pending.rename(self.jobs / (name + ".job"))

        def rows(self, sql, *args):
            with closing(sqlite3.connect((self.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                return db.execute(sql, args).fetchall()

    output.mkdir()
    owner = Worker(working, output, host, binary, root, declaration)
    tool_text = "confirmed tool receipt retains exact source"
    long_text = "unselected tail " + "x" * 540
    with owner.running():
        owner.op("person", "create", ACTOR)
        user = owner.op("account", "open", "qq", "reflection-tools", "200", 1, "--person", ACTOR, "--start", 1)
        bot = owner.op("account", "open", "qq", "reflection-tools", "100", 1, "--start", 1)
        entry = owner.op("entry", "private", user["assignment"], bot["assignment"])["entry"]
        space = '["qq","reflection-tools","701"]'
        owner.op("entry", "group", space)

        def confirm(sequence, text, *, foreign=False):
            frame = {"source": f"receipt-{sequence}", "account": user["account"],
                     "bot_stage": bot["assignment"], "reply_bot": "100", "kind": "message",
                     "occurred": 100 * sequence, "observed": 100 * sequence,
                     "segments": [{"type": "text", "text": "original request"}]}
            if foreign:
                frame["space"] = space
            event = owner.op("ingress", "record", json.dumps(frame), "--accept")["event"]
            execution = owner.op("ingress", "claim", event)["execution"]
            operation = f"receipt-{sequence}"
            owner.op("effect", "intent", execution, operation, ACTOR, "put", operation,
                     json.dumps({"value": text}))
            result = owner.op("effect", "local", execution, operation, ACTOR)
            assert result["state"] == "confirmed" and result["result"]["value"]["value"] == text
            receipt, = owner.rows("SELECT rowid FROM operations WHERE namespace=? AND operation_id=?",
                                  execution, operation)[0]
            return {"execution": execution, "receipt": receipt, "sources": [event]}, operation

        original, operation = confirm(1, tool_text)
        unselected, unselected_operation = confirm(2, "second actual receipt")
        foreign, _ = confirm(3, "another entry", foreign=True)
        long, _ = confirm(4, long_text)

    trace = output / "wire.jsonl"
    with model_peer() as (port, model, requests, _accepted, _release):
        configure(owner, root, binary, trace, entry, port, declaration)

        def plan(*tools):
            return {"scope": "own", "route": "review", "tools": list(tools)}

        def action(key, execution, op, quote):
            return {"action": "add", "subject": {"kind": "self", "visibility": "private", "entry": entry},
                    "fact_key": key, "body": "retain a fact from the confirmed tool result",
                    "evidence": [{"kind": "tool", "execution": execution, "operation": op, "quote": quote}]}

        def frames(method):
            rows = [json.loads(line) for line in trace.read_bytes().splitlines(keepends=True) if line.endswith(b"\n")]
            return [row["frame"]["params"] for row in rows if row["direction"] == "from_plugin"
                    and row["frame"].get("method") == method]

        def state():
            return json.loads((owner.jobs / "reflection-tool-original/state.json").read_bytes())

        with owner.running():
            owner.online()
            wrong_source = dict(original, sources=unselected["sources"])
            missing_receipt = dict(original, receipt=unselected["receipt"])
            for name, selected in [("foreign-tool", foreign), ("wrong-source", wrong_source),
                                   ("missing-receipt", missing_receipt), ("oversize-tool", long)]:
                rejected = owner.job(name, "run", batch=name, plan=plan(selected))
                assert rejected["state"] == "not_completed", rejected
            assert not requests and not frames("maintenance.model.open")
            model["actions"] = [action("other-tool", unselected["execution"], unselected_operation,
                                       "second actual receipt")]
            unbound = owner.job("unselected-evidence", "run", batch="unselected-evidence", plan=plan(original))
            assert unbound["state"] == "not_completed" and not owner.facts()
            model["actions"] = [action("false-quote", original["execution"], operation, "fabricated quote")]
            false = owner.job("false-quote", "run", batch="false-quote", plan=plan(original))
            assert false["state"] == "not_completed" and not owner.facts()
            assert len(requests) == 2
            model["actions"] = [action("tool-lesson", original["execution"], operation, tool_text)]
            (owner.control / "kill-model-call").write_text("tool-original", encoding="utf-8")
            owner.submit("before-tool-ack", "run", batch="tool-original", plan=plan(original))
            paid = wait_for(owner.control / "model-paid-before-kill.json")["result"]
            assert paid["state"] in {"response", "paired"} and len(requests) == 3
            assert state()["phase"]["phase"] == "prepared"
            assert tool_text in str(requests[-1]["wire"])
            assert not owner.facts() and not (owner.jobs / "before-tool-ack.result").exists()

        with owner.running():
            owner.online()
            result = peer.completed(owner.job("recover-tool-ack", "run", batch="tool-original",
                                              plan=plan(original)))
            assert result["request"] == paid["request"] and len(requests) == 3
            assert len(result["receipts"]["applied"]) == 1 and owner.facts() == [("tool-lesson", 1)]
            assert owner.rows("SELECT kind, visibility, visibility_entry FROM memory_facts") == [
                ("self", "private", entry)]
            evidence, = owner.rows("SELECT kind, source_key, origin_execution, quote FROM memory_evidence")
            assert (evidence[0], json.loads(evidence[1]), evidence[2], evidence[3]) == (
                "tool", [original["execution"], operation], original["execution"], tool_text)
            roots = [frame for frame in frames("maintenance.model.open") if frame["key"] == "tool-original"]
            preview, = [frame for frame in frames("maintenance.extract.preview") if frame["key"] == "tool-original"]
            assert len(roots) == 2 and roots[0] == roots[1]
            assert roots[0]["tools"] == preview["tools"] and roots[0]["sources"] == preview["sources"] == []
            assert roots[0]["tools"][0]["receipt"] == original["receipt"]
            assert roots[0]["tools"][0]["role"] == "primary"
            owner.op("privacy", "erase", "original-tool-source", ACTOR, json.dumps(original["sources"]))
            deadline = time.monotonic() + 12
            while owner.op("privacy", "pending", declaration["id"])["obligations"]:
                assert time.monotonic() < deadline, "tool receipt erasure did not settle"
                time.sleep(.05)
            assert owner.rows("SELECT status FROM memory_facts") == [("erased",)]
            assert owner.rows("SELECT quote FROM memory_evidence") == [(None,)]
            assert owner.rows("SELECT count(*) FROM model_attempts WHERE json_extract(usage_json,'$.total')=12") == [(3,)]
            assert state()["plan"] is None and state()["phase"]["phase"] == "erased"
            assert not (owner.jobs / "recover-tool-ack.result").exists()
            assert not (owner.jobs / "before-tool-ack.job").exists()

        with owner.running():
            owner.online()
            stale = peer.completed(owner.job("erased-tool", "run", batch="tool-original", plan=plan(original)))
            assert stale == {"phase": "erased"} and len(requests) == 3
            assert not (owner.jobs / "erased-tool.job").exists()

    return {"original": original, "operation": operation, "frozen_tools": roots[0]["tools"],
            "original_model": result["request"], "model_transport_attempts": len(requests),
            "cold_recovery_with_original_model_receipt": True, "source_erased_fact_and_checkpoint": True,
            "unselected_receipt_and_fabricated_quote_denied": True,
            "foreign_wrong_source_missing_and_oversize_denied_before_model": True}


def prepare(root, output):
    spec = importlib.util.spec_from_file_location("paired_maintenance", root/"tests/cases/EXT-034.py")
    peer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(peer)
    with tempfile.TemporaryDirectory(prefix="r035-") as work:
        work = Path(work).resolve()
        host, lock, producer_receipts = peer.candidate(root, work)
        package = build(root, "memory-maintenance", output/"packages")
        binary = output/"packages"/("yuki-memory-maintenance.exe" if os.name == "nt" else "yuki-memory-maintenance")
        declaration = tomllib.loads((output/"packages/plugin-reflection.toml").read_text(encoding="utf-8"))
        assert declaration["version"] == package["version"] == "0.1.0-alpha.6"
        tools = tomllib.loads((output/"packages/plugin-reflection-tools.toml").read_text(encoding="utf-8"))
        assert tools["version"] == declaration["version"] and tools["id"] != declaration["id"]
        cases = exercise(peer, root, work/"r", output, host, binary, declaration)
        tool_cases = exercise_tool_receipts(peer, root, work/"t", output/"tools", host, binary, tools)
    return "reflection-scope.json", {"status":"PASS", "card_status":"UNPUBLISHED_EVENT_AND_TOOL_REFLECTION",
        "candidate":lock, "producer_receipts":producer_receipts, "plugin":package["artifacts"],
        "cases":cases, "tool_cases":tool_cases, "paid_provider_calls":0, "published":False,
        "remaining":["original batch scheduling", "foreground quiet policy",
                     "instance-level daily quota and published installation tuple"]}


def run(root, output):
    name, result = prepare(root, output)
    result["status"] = "BLOCKED"
    return name, result
