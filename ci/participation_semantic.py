"""Run the installed Rust review and Rule workers against one real Host."""

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import sys
from threading import Event, Thread
import time

from rebuild_intake import Owner


def run(work, executable, worker, adapter, upstream, output):
    owner = Owner(work, executable, output)
    person = "00000000-0000-4000-8000-000000000253"
    space = '["qq","review-fixture","753"]'
    with owner.running():
        entry = owner.op("entry", "group", space)["entry"]
        owner.op("person", "create", person)
        author = owner.op("account", "open", "qq", "review-fixture", "200", 1,
                          "--person", person, "--start", 1)
        bot = owner.op("account", "open", "qq", "review-fixture", "100", 1, "--start", 1)

    def query(statement, *args):
        with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
            return db.execute(statement, args).fetchall()

    def review_receipt(event):
        return query(
            "SELECT a.state,a.usage_json FROM model_attempts a "
            "JOIN host_aux_requests r ON r.logical=a.logical "
            "JOIN host_aux_origins o ON o.plugin=r.plugin AND o.original=r.origin WHERE o.event=? "
            "AND a.usage_json IS NOT NULL",
            event,
        )

    def await_result(action):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if value := action():
                return value
            time.sleep(0.05)
        raise TimeoutError("original participation review did not settle")

    timestamps = {}

    def ingress(native, text, *, quoted=False, mentioned=False):
        parts = [{"type": "text", "text": text}]
        if quoted:
            parts.append({"type": "reply", "native_id": "75301"})
        if mentioned:
            parts.append({"type": "mention", "account": bot["account"], "native": "100", "label": "Yuki"})
        now = timestamps.setdefault(native, time.time_ns() // 1_000_000)
        packet = {"source": native, "native_id": native, "account": author["account"],
                  "bot_stage": bot["assignment"], "reply_bot": "100", "space": space,
                  "kind": "message", "observed": now, "occurred": now, "segments": parts}
        return owner.op("ingress", "record", json.dumps(packet))["event"]

    main_calls, review_calls = [], []
    wait_for_review, release_review = Event(), Event()
    late_review, release_late = Event(), Event()

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/main":
                main_calls.append(request)
                response = {"choices": [{"message": {"role": "assistant", "content": "quiet"},
                                         "finish_reason": "stop"}]}
            else:
                assert self.path == "/systemone" and request["model"] == "jev-request-fixture"
                review_calls.append(request)
                focus = request["state"]["focus"]["text"]
                if "explicit-rule" in focus:
                    wait_for_review.set()
                    assert release_review.wait(10)
                if "withdrawn while reviewing" in focus:
                    late_review.set()
                    assert release_late.wait(10)
                choices = ({"floor_state": "yuki", "interaction_mark": "invite_yuki"}
                           if "literal-name" not in focus else {})
                answers = {}
                for name, question in request["questions"].items():
                    choice = choices.get(name, "unknown")
                    answers[name] = {"type": "choice", "choice": choice,
                                     "probabilities": {key: float(key == choice) for key in question["criteria"]}}
                response = {"model": "incorrect-fixture" if "wrong-response" in focus else "jev-response-fixture",
                            "answers": answers,
                            "usage": {"input_tokens": 17, "output_tokens": 3}}
            body = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    checkpoint = work / "review-checkpoint.sqlite"
    canary = "private-original-participation-anchor-753"
    with ThreadingHTTPServer(("127.0.0.1", 0), Model) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            owner.env["YUKI_REVIEW_FIXTURE"] = "deterministic-test-key"
            base = f"http://127.0.0.1:{server.server_port}"
            common = ["observe.metadata", "participation.source", "participation.promote", "forget.owner"]
            def plugin(name, args, grants):
                return (
                    '\n[[plugins]]\nid=' + json.dumps(name) + '\nnamespace=' + json.dumps(name)
                    + '\nprogram=' + json.dumps(str(worker)) + '\nargs=' + json.dumps(args)
                    + '\ngrants=' + json.dumps(grants) + '\n[plugins.participation]\nentries=' + json.dumps([entry]) + '\n'
                )
            with (owner.data / "yuki.toml").open("a", encoding="utf-8") as stream:
                stream.write(
                    '\n[main]\nendpoint=' + json.dumps(base + "/main")
                    + '\nmodel="main-review-fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=3\n'
                    'max_input_units=200000\nmax_output=128\n'
                    '[qq]\nnamespace="review-fixture"\ndesignated_ingress="100"\n'
                    '[qq.groups]\n"753"="observe"\n[[qq.bots]]\nself_id="100"\nstage='
                    + json.dumps(bot["assignment"]) + '\ntoken_env="YUKI_REVIEW_FIXTURE"\n'
                    + plugin("rule", [entry, bot["assignment"]], common)
                    + plugin("review", [entry, bot["assignment"], "--review", sys.executable, str(adapter),
                                        str(upstream), str(checkpoint), "jev", "jev-response-fixture", "Yuki"],
                             [*common, "llm.complete", "llm.result"])
                    + '\n[plugins.aux_routes.jev]\npurposes=["review"]\norigins=["event"]\nentries='
                    + json.dumps([entry]) + '\n[plugins.aux_routes.jev.profile]\nendpoint=' + json.dumps(base + "/systemone")
                    + '\nmodel="jev-request-fixture"\nname="Jev"\nmerge_ms=0\nroot_slots=2\n'
                    'max_input_units=200000\nmax_output=128\nkey_env="YUKI_REVIEW_FIXTURE"\n'
                    '[plugins.aux_routes.jev.jev]\nresponse_model="jev-response-fixture"\ntimeout_seconds=14.0\n'
                )
            with owner.running():
                await_result(lambda: sum(1 for item in owner.op("host", "status")["plugins"] if item["online"]) == 2)
                anchor = ingress("75301", canary)
                literal = ingress("75302", "literal-name Yuki", quoted=True)
                wrong = ingress("75305", "wrong-response", quoted=True)
                explicit = ingress("75303", "explicit-rule", quoted=True, mentioned=True)
                assert wait_for_review.wait(14)
                await_result(lambda: query("SELECT 1 FROM main_inputs WHERE event=?", explicit))
                assert query("SELECT event FROM participation_promotions WHERE plugin='review'") == []
                release_review.set()
                await_result(lambda: query("SELECT 1 FROM participation_promotions WHERE plugin='review' AND event=?", explicit))
                semantic = ingress("75304", "ordinary continuation", quoted=True)
                await_result(lambda: query("SELECT 1 FROM main_inputs WHERE event=?", semantic))
                await_result(lambda: len(main_calls) == 2)
                assert query("SELECT event_id FROM accepted_sources ORDER BY event_id") == [(explicit,), (semantic,)]
                assert query("SELECT event FROM participation_promotions WHERE plugin='rule'") == [(explicit,)]
                assert len(review_calls) == 4
                assert canary.encode() in checkpoint.read_bytes()

            with owner.running():
                await_result(lambda: sum(1 for item in owner.op("host", "status")["plugins"] if item["online"]) == 2)
                assert ingress("75304", "ordinary continuation", quoted=True) == semantic
                after_restart = ingress("75306", "literal-name after restart", quoted=True)
                await_result(lambda: len(review_calls) >= 5)
                await_result(lambda: review_receipt(after_restart))
                assert len(review_calls) == 5
                assert query("SELECT event_id FROM accepted_sources ORDER BY event_id") == [(explicit,), (semantic,)]
                for reviewed in (literal, explicit, semantic, after_restart):
                    (state, usage), = review_receipt(reviewed)
                    assert state == "response" and json.loads(usage) == {"input": 17, "output": 3}
                assert len(review_receipt(wrong)) == 1 and review_receipt(wrong)[0][0] != "response"
                late = ingress("75308", "withdrawn while reviewing", quoted=True)
                assert late_review.wait(14)
                assert not query("SELECT event_id FROM accepted_sources WHERE event_id=?", late)
                erasure = owner.op("privacy", "erase", "forget-native-review", person, json.dumps([anchor]))
                release_late.set()
                await_result(lambda: query("SELECT 1 FROM owner_erasures WHERE owner='review' AND watermark=? "
                                          "AND proof IS NOT NULL", erasure["watermark"]))
                (late_state, late_usage), = await_result(lambda: review_receipt(late))
                assert late_state == "response_held" and json.loads(late_usage) == {"input": 17, "output": 3}
                assert not query("SELECT event_id FROM accepted_sources WHERE event_id=?", late)
                with closing(sqlite3.connect(checkpoint.as_uri() + "?mode=ro", uri=True)) as snapshot:
                    assert all(canary.encode() not in body for (body,) in
                               snapshot.execute("SELECT body FROM snapshot_body"))
                paths = [checkpoint, checkpoint.with_name(checkpoint.name + "-wal")]
                remaining = [path.name for path in paths if path.exists() and canary.encode() in path.read_bytes()]
                assert not remaining, f"erased anchor remains in {remaining}"

            config = owner.data / "yuki.toml"
            config.write_text(config.read_text(encoding="utf-8").replace('"753"="observe"', '"753"="paused"'),
                              encoding="utf-8")
            with owner.running():
                await_result(lambda: sum(1 for item in owner.op("host", "status")["plugins"] if item["online"]) == 2)
                paused = ingress("75307", "paused group", quoted=True, mentioned=True)
                assert not review_receipt(paused)
                assert not query("SELECT 1 FROM main_inputs WHERE event=?", paused)
        finally:
            release_review.set()
            release_late.set()
            server.shutdown()
            thread.join()
    assert len(review_calls) == 6 and len(main_calls) == 2
    return {"accepted": [explicit, semantic], "ignored_literal": literal, "ignored_invalid_response": wrong,
            "anchor": anchor, "paused": paused, "cold_replay": semantic,
            "withdrawn_during_review": late, "withdrawn_receipt": {"state": late_state, "usage": json.loads(late_usage)},
            "main_attempts": len(main_calls), "review_attempts": len(review_calls), "paid_calls": 0,
            "rule_accepted_before_review": True, "source_erasure": erasure["watermark"]}
