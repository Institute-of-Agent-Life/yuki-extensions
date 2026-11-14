"""Exercise the packaged Rust Rule through the actual Host and original ingress."""

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
from threading import Thread
import time

from rebuild_intake import Owner, sha


def run(work, executable, worker, output):
    owner = Owner(work, executable, output)
    person = "00000000-0000-4000-8000-000000000241"
    entries = ['["qq","rule-fixture","740"]', '["qq","rule-fixture","741"]']
    with owner.running():
        entry, foreign = [owner.op("entry", "group", space)["entry"] for space in entries]
        owner.op("person", "create", person)
        author = owner.op("account", "open", "qq", "rule-fixture", "200", 1,
                          "--person", person, "--start", 1)
        selected = owner.op("account", "open", "qq", "rule-fixture", "100", 1, "--start", 1)
        other = owner.op("account", "open", "qq", "rule-fixture", "101", 1, "--start", 1)

    def query(statement, *arguments):
        with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute(statement, arguments).fetchall()

    def await_original(action):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if result := action():
                return result
            time.sleep(0.05)
        raise TimeoutError("Rust participation did not complete the original operation")

    timestamps = {}

    def observe(identity, native, segments, space=entries[0]):
        now = timestamps.setdefault(identity, time.time_ns() // 1_000_000)
        frame = {"source": identity, "native_id": native, "account": author["account"],
                 "bot_stage": selected["assignment"], "reply_bot": "100", "space": space,
                 "kind": "message", "observed": now, "occurred": now, "segments": segments}
        return owner.op("ingress", "record", json.dumps(frame))["event"]

    model_calls = []

    class Quiet(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            model_calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "quiet"},
                                           "finish_reason": "stop"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Quiet) as model:
        thread = Thread(target=model.serve_forever)
        thread.start()
        try:
            owner.env.update(YUKI_RULE_STAGE_A="test-stage-a", YUKI_RULE_STAGE_B="test-stage-b")
            with (owner.data / "yuki.toml").open("a", encoding="utf-8") as stream:
                stream.write(
                    '\n[main]\nendpoint=' + json.dumps(f"http://127.0.0.1:{model.server_port}/main")
                    + '\nmodel="rule-fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=3\n'
                    'max_input_units=200000\nmax_output=128\n'
                    '[qq]\nnamespace="rule-fixture"\ndesignated_ingress="100"\n'
                    '[qq.groups]\n"740"="observe"\n"741"="observe"\n'
                    '[[qq.bots]]\nself_id="100"\nstage=' + json.dumps(selected["assignment"])
                    + '\ntoken_env="YUKI_RULE_STAGE_A"\n[[qq.bots]]\nself_id="101"\nstage='
                    + json.dumps(other["assignment"]) + '\ntoken_env="YUKI_RULE_STAGE_B"\n'
                    '[[plugins]]\nid="participation"\nnamespace="participation"\nprogram='
                    + json.dumps(str(worker)) + '\nargs=' + json.dumps([entry, selected["assignment"]])
                    + '\ngrants=["observe.metadata","participation.source","participation.promote","forget.owner"]\n'
                    '[plugins.participation]\nentries=' + json.dumps([entry]) + '\n'
                )
            with owner.running():
                def plugin_ready():
                    return any(item["online"] for item in owner.op("host", "status")["plugins"])

                await_original(plugin_ready)
                text = {"type": "text", "text": "Yuki fixture"}
                native = {"type": "mention", "account": selected["account"], "native": "100", "label": "Yuki"}
                different = {"type": "mention", "account": other["account"], "native": "101", "label": "Other"}
                members = [{"type": "mention", "account": author["account"], "native": "200", "label": "Member"}] * 16
                literal = observe("literal", "74001", [text])
                ambiguous = observe("two-yuki-stages", "74002", [text, native, *members, different])
                out_of_scope = observe("foreign-entry", "74101", [text, native], entries[1])
                assert not query("SELECT event_id FROM accepted_sources")
                event = observe("one-original-stage", "74003", [text, *members, native])
                original = await_original(lambda: query(
                    "SELECT x.id FROM main_inputs input JOIN executions x ON x.id=input.execution "
                    "WHERE input.event=? AND x.state='completed'", event))
                replayed = observe("one-original-stage", "74003", [text, *members, native])
                assert replayed == event and query("SELECT event_id FROM accepted_sources") == [(event,)]
                assert query("SELECT event FROM participation_promotions WHERE plugin='participation'") == [(event,)]
                held = query("SELECT DISTINCT source FROM source_holds WHERE owner='participation' ORDER BY source")
                assert held == [(literal,), (ambiguous,), (event,)] and (out_of_scope,) not in held
                erasure = owner.op("privacy", "erase", "erase-volatile-rule", person, json.dumps([literal]))
                proof = await_original(lambda: query(
                    "SELECT proof FROM owner_erasures WHERE watermark=? AND owner='participation' AND proof IS NOT NULL",
                    erasure["watermark"],
                ))
                assert len(proof) == 1 and len(model_calls) == 1
        finally:
            model.shutdown()
            thread.join()
    return {"worker_sha256": sha(worker), "entry": entry, "foreign_entry": foreign,
            "events": {"literal": literal, "ambiguous": ambiguous, "outside_entry": out_of_scope, "admitted": event},
            "main": original[0][0],
            "same_input": replayed == event, "model_attempts": len(model_calls), "paid_calls": 0,
            "erasure_watermark": erasure["watermark"], "erasure_proof": proof[0][0]}
