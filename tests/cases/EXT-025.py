"""Replay human and confirmed SELF replies through the installed SDK and Jev library."""

from contextlib import closing
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from zipfile import ZipFile

from package import build
from personal_preview import free_address
from participation_rule import run as replay_rule
from participation_semantic import run as replay_semantic
from rebuild_intake import Owner, sha, wait_for, write


HOST_METHODS = ["observe.metadata", "participation.source", "participation.promote",
                "participation.feedback", "forget.owner", "llm.complete", "llm.result"]
FIXTURE_KEY = "ext025-fixture"
FOCUS_PERSON = "00000000-0000-4000-8000-000000000025"
MENTION_PERSON = "00000000-0000-4000-8000-000000000026"
DELIVERY_TEXT = "已確認送達的 Yuki 回覆"


def prepare(root, output):
    archive = Path(os.environ["YUKI_CORE050_CANDIDATE"])
    source = Path(os.environ["YUKI_PARTICIPATION_SOURCE"]).resolve()
    manifest_path = Path(os.environ["YUKI_CORE050_MANIFEST"])
    producer = json.loads((root / "compat/participation-library/native-host.lock.json").read_bytes())
    upstream = json.loads((root / "compat/participation-library/source.lock.json").read_bytes())
    manifest = json.loads(manifest_path.read_bytes())
    assert manifest["status"] == "verified" and manifest["exit_code"] == 0
    assert manifest["source"]["commit"] == producer["commit"] and not manifest["source"]["dirty"]
    assert manifest["source"]["tree_sha256"] == producer["tree_sha256"]
    assert manifest["card"] == "CORE-050" and "native-jev-wire" in manifest["capabilities"]
    assert manifest["assertions"] and all(row["passed"] for row in manifest["assertions"])
    assert sha(source) == upstream["source_sha256"]
    with tempfile.TemporaryDirectory(prefix="ext025-") as directory:
        work = Path(directory)
        with tarfile.open(source) as bundle:
            bundle.extractall(work, filter="data")
        library = work / ("Yuki-Semantic-Participation-" + upstream["source_commit"])
        for name, expected in upstream["inspected_files"].items():
            assert sha(library / name) == expected
        with ZipFile(archive) as package:
            candidate = json.loads(package.read("candidate.json"))
            assert candidate["source_commit"] == producer["commit"] and not candidate["dirty"]
            assert candidate["status"] == producer["status"]
            assert candidate["source_tree_sha256"] == producer["tree_sha256"]
            assert candidate["host_schema_sha256"] == producer["host_schema_sha256"]
            assert candidate["aux_schema_sha256"] == producer["aux_schema_sha256"]
            assert candidate["sdk_versions"] == producer["sdk_versions"]
            assert candidate["validation"]["card"] == "CORE-050"
            assert candidate["validation"]["manifest_sha256"] == sha(manifest_path)
            assert candidate["validation"]["platform"] == manifest["platform"]
            assert candidate["validation"]["assertions"] == len(manifest["assertions"])
            assert set(HOST_METHODS) - {"observe.metadata", "forget.owner"} <= set(candidate["implemented_methods"])
            assert sorted(package.namelist()) == sorted(["candidate.json", *candidate["members"]])
            for name, member in candidate["members"].items():
                assert package.getinfo(name).file_size == member["bytes"]
                with package.open(name) as stream:
                    assert file_digest(stream, "sha256").hexdigest() == member["sha256"], name
            executable = work / ("yuki-core.exe" if os.name == "nt" else "yuki-core")
            with package.open("bin/" + executable.name) as stream, executable.open("xb") as binary:
                shutil.copyfileobj(stream, binary)
            executable.chmod(0o700)
            proof = package.read("evidence/aux-attempts.json")
            assert sha256(proof).hexdigest() == manifest["artifacts"]["aux-attempts.json"]
            assert json.loads(proof)["binary_sha256"] == sha(executable)
            sdk = work / "sdk"
            wheel = "sdk/yuki_plugin_sdk-" + producer["sdk_versions"]["python"] + "-py3-none-any.whl"
            wheel_path = work / "sdk.whl"
            wheel_path.write_bytes(package.read(wheel))
        with ZipFile(wheel_path) as package:
            package.extractall(sdk)
        report = replay(root, output, work, executable, library / "src", sdk, producer["reader"])
        report["host"] = {"archive_sha256": sha(archive), "binary_sha256": sha(executable),
                          "manifest_sha256": candidate["validation"]["manifest_sha256"], **producer}
        report["library"] = {"commit": upstream["source_commit"], "sha256": upstream["source_sha256"]}
        packages = output / "packages"
        build(root, "participation", packages)
        worker = packages / ("yuki-participation.exe" if os.name == "nt" else "yuki-participation")
        rule_output = output / "native-rule"
        rule_output.mkdir()
        report["native_rule"] = replay_rule(work / "rule-owner", executable, worker, rule_output)
        report["native_rule"]["package_manifest_sha256"] = sha(packages / "package-manifest.json")
        semantic_output = output / "native-semantic"
        semantic_output.mkdir()
        report["native_semantic"] = replay_semantic(work / "review-owner", executable, worker,
                                                    packages / "semantic_bridge.py", source, semantic_output)
        write(output / "ordinary-replay.json", {
            "status": "PASS", "card_status": "in_progress", "published": False,
            "host": report["host"], "library": report["library"], "worker_sha256": sha(worker),
            "package_manifest_sha256": sha(packages / "package-manifest.json"), **report["native_semantic"],
        })
    return "native-jev-intake.json", report


def replay(root, output, workspace, executable, library, sdk, expected_reader):
    owner = Owner(workspace, executable, output)
    space = '["qq","ext025","720"]'
    address = free_address()
    config = owner.data / "yuki.toml"
    initial = config.read_text(encoding="utf-8")
    assert '"127.0.0.1:0"' in initial
    config.write_text(initial.replace('"127.0.0.1:0"', json.dumps(address), 1), encoding="utf-8")
    sys.path.insert(0, str(root / "tests/peers"))
    try:
        from subscription_onebot import Peer
    finally:
        sys.path.pop(0)
    with owner.running():
        entry = owner.op("entry", "group", space)["entry"]
        actors = []
        for person, native in ((FOCUS_PERSON, "200"), (MENTION_PERSON, "202")):
            owner.op("person", "create", person)
            actors.append(owner.op("account", "open", "qq", "ext025", native, 1,
                                   "--person", person, "--start", 1))
        bot = owner.op("account", "open", "qq", "ext025", "100", 1, "--start", 1)

    requests = []
    main_requests = []

    class Model(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/main":
                main_requests.append(body)
                message = {"role": "assistant", "content": "fixture completed"}
                reason = "stop"
                if len(main_requests) == 1:
                    message["content"] = None
                    message["tool_calls"] = [{"id": "seed-delivery", "type": "function", "function": {
                        "name": "send", "arguments": json.dumps({"text": DELIVERY_TEXT}, ensure_ascii=False),
                    }}]
                    reason = "tool_calls"
                return self.respond({"choices": [{"message": message, "finish_reason": reason}]})
            if self.path != "/systemone":
                return self.send_error(404)
            requests.append({"path": self.path, "body": body,
                             "credential": self.headers.get("Authorization") == f"Bearer {FIXTURE_KEY}"})
            has_self = any(event["kind"] == "self" for event in body["state"]["context"])
            addressed = {"interaction_mark": "extend_yuki", "floor_state": "yuki"} if has_self else {}
            answers = {}
            for name, question in body["questions"].items():
                criteria = question["criteria"]
                choice = addressed.get(name, "unknown")
                answers[name] = {"type": "choice", "choice": choice,
                                 "probabilities": {key: float(key == choice) for key in criteria}}
            self.respond({"model": "jev-response-fixture", "answers": answers,
                          "usage": {"input_tokens": 21, "output_tokens": 4}})

        def respond(self, response):
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with ThreadingHTTPServer(("127.0.0.1", 0), Model) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            owner.env["YUKI_EXT025_KEY"] = FIXTURE_KEY
            owner.env["PYTHONPATH"] = os.pathsep.join(
                (str(library), str(sdk), *(path for path in sys.path if "site-packages" in path))
            )
            write(owner.probe_root / "config.json", {"entry": entry, "receiver": bot["assignment"]})
            peer = root / "tests/peers/participation-source-probe/jev_replay.py"
            with config.open("a", encoding="utf-8") as stream:
                stream.write(
                    '\n[main]\nendpoint=' + json.dumps(f"http://127.0.0.1:{server.server_port}/main")
                    + '\nmodel="main-fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=4\n'
                    'max_input_units=200000\nmax_output=128\n'
                    '\n[qq]\nnamespace="ext025"\ndesignated_ingress="100"\n'
                    '[qq.groups]\n"720"="open"\n[[qq.bots]]\nself_id="100"\nstage='
                    + json.dumps(bot["assignment"]) + '\ntoken_env="YUKI_EXT025_KEY"\n'
                    + '\n[[plugins]]\nid="participation-probe"\nnamespace="participation-probe"\nprogram='
                    + json.dumps(sys.executable) + '\nargs=' + json.dumps([str(peer), str(owner.probe_root)])
                    + '\nenv=["PYTHONPATH"]\ngrants=' + json.dumps(HOST_METHODS)
                    + '\n[plugins.participation]\nentries=' + json.dumps([entry])
                    + '\n[plugins.aux_routes.review]\npurposes=["review"]\norigins=["event"]\nentries='
                    + json.dumps([entry]) + '\n[plugins.aux_routes.review.profile]\nendpoint='
                    + json.dumps(f"http://127.0.0.1:{server.server_port}/systemone")
                    + '\nmodel="jev-request-fixture"\nname="Jev"\nmerge_ms=0\nroot_slots=2\n'
                    'max_input_units=200000\nmax_output=128\nkey_env="YUKI_EXT025_KEY"\n'
                    '[plugins.aux_routes.review.jev]\nresponse_model="jev-response-fixture"\ntimeout_seconds=12.0\n'
                )
            with owner.running():
                def record(key, native, who, segments, timestamp, *, accept=False):
                    frame = {"source": key, "native_id": native, "account": who["account"],
                             "bot_stage": bot["assignment"], "reply_bot": "100",
                             "space": space, "kind": "message", "observed": timestamp,
                             "occurred": timestamp, "segments": segments}
                    args = ["ingress", "record", json.dumps(frame, ensure_ascii=False)]
                    return owner.op(*args, *(["--accept"] if accept else []))["event"]

                for _ in range(240):
                    status = owner.op("host", "status")
                    if len(status["plugins"]) == 1 and status["plugins"][0]["online"]:
                        break
                    time.sleep(0.05)
                else:
                    raise TimeoutError("diagnostic SDK peer never became online")
                now = time.time_ns() // 1_000_000
                anchor = record("original-anchor", "36011", actors[1],
                                [{"type": "text", "text": "原先的群消息"}], now - 100)
                marks = [
                    {"account": actors[1]["account"], "label": "群友", "span": {"segment": 1, "start": 0, "end": 3}},
                    {"account": bot["account"], "label": "Yuki", "span": {"segment": 1, "start": 4, "end": 9}},
                    {"account": actors[1]["account"], "label": "群友", "span": None},
                    {"native": "all", "label": "全體", "span": None},
                    {"native": "999", "label": "未知", "span": None},
                ]
                event = record("native-mention", "36012", actors[0], [
                    {"type": "reply", "native_id": "36011"}, {"type": "text", "text": "@群友 @Yuki 雨停了嗎？"},
                    *({"type": "mention", **mark} for mark in marks),
                ], now)
                result = wait_for(owner.probe_root / f"result-{event}.json", timeout=20)
                literal = record("literal-name", "36016", actors[0], [
                    {"type": "reply", "native_id": "36011"},
                    {"type": "text", "text": "Yuki 是名字，不是此次提及的對象"},
                ], time.time_ns() // 1_000_000)
                literal_result = wait_for(owner.probe_root / f"result-{literal}.json", timeout=20)
                with closing(Peer(address, "100", FIXTURE_KEY)) as gateway:
                    seed = record("human-input-with-original-delivery", "36013", actors[0],
                                  [{"type": "text", "text": "請回覆群組"}], time.time_ns() // 1_000_000, accept=True)
                    delivery = gateway.receive()
                    assert delivery["action"] == "send_group_msg"
                    assert str(delivery["params"]["group_id"]) == "720"
                    gateway.send({"echo": delivery["echo"], "status": "ok", "retcode": 0,
                                  "data": {"message_id": 36014}})
                    with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                        for _ in range(240):
                            stored = db.execute(
                                "SELECT d.event FROM personal_deliveries d JOIN social_outbound o ON o.id=d.outbound "
                                "JOIN executions x ON x.id=o.namespace WHERE o.locator='36014' AND x.source=?",
                                (seed,),
                            ).fetchone()
                            if stored is not None:
                                break
                            time.sleep(0.05)
                        else:
                            raise TimeoutError("acknowledged SELF delivery")
                    self_focus = record("reply-to-original-self", "36015", actors[0], [
                        {"type": "reply", "native_id": "36014"}, {"type": "text", "text": "@群友 @Yuki 原回覆呢？"},
                        *({"type": "mention", **mark} for mark in marks),
                    ], time.time_ns() // 1_000_000)
                    self_result = wait_for(owner.probe_root / f"result-{self_focus}.json", timeout=20)
                with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                    attempts = db.execute(
                        "SELECT t.state,t.usage_json FROM model_attempts t JOIN host_aux_requests q ON q.logical=t.logical"
                    ).fetchall()
                    accepted = db.execute("SELECT event_id FROM accepted_sources ORDER BY event_id").fetchall()
                    turns = db.execute("SELECT event FROM main_inputs ORDER BY event").fetchall()
                    reader, = db.execute("SELECT max(version) FROM _sqlx_migrations").fetchone()
            prior_request = next(row["params"] for row in self_result["wire"] if row["method"] == "llm.complete")
            prior_result = next(row["response"]["result"]["sha256"] for row in self_result["wire"]
                                if row["method"] == "llm.result")
            write(owner.probe_root / "config.json", {"recover": {
                "scope": self_result["focus"]["scope"], "ref": self_result["focus"]["ref"], "review": prior_request,
            }})
            with owner.running():
                cold = wait_for(owner.probe_root / "cold-result.json", timeout=20)
                with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                    cold_attempts, = db.execute("SELECT count(*) FROM model_attempts t JOIN host_aux_requests q ON q.logical=t.logical").fetchone()
                    cold_inputs = db.execute("SELECT event FROM main_inputs ORDER BY event").fetchall()
        finally:
            server.shutdown()
            thread.join()

    assert len(requests) == 3 and all(row["path"] == "/systemone" and row["credential"] for row in requests)
    body = requests[0]["body"]
    assert set(body) == {"model", "questions", "state"} and body["model"] == "jev-request-fixture"
    assert result["event"] == event and result["anchor"]["event"] == anchor
    focus = body["state"]["focus"]
    assert focus["reply_to"] == body["state"]["context"][0]["id"]
    assert focus["target"] == FOCUS_PERSON and [mark["kind"] for mark in focus["mentions"]] == [
        "member", "yuki", "member", "all", "member",
    ]
    assert focus["mentions"][0]["person"] == MENTION_PERSON
    assert focus["mentions"][0]["account"] == focus["mentions"][2]["account"]
    assert "text_start" not in focus["mentions"][2] and "person" not in focus["mentions"][-1]
    assert result["focus"]["mentions"][0]["assignment_id"] == actors[1]["assignment"]
    assert result["focus"]["mentions"][1]["presence_id"] == bot["assignment"]
    literal_body = requests[1]["body"]
    assert literal_result["event"] == literal and "mentions" not in literal_body["state"]["focus"]
    assert literal_result["focus"]["mentions"] == [] and not literal_result["invited"]
    assert literal_result["rule"] is literal_result["semantic"] is None
    self_body = requests[2]["body"]
    self_reply = self_body["state"]["context"][0]
    assert set(self_body) == {"model", "questions", "state"} and self_body["model"] == "jev-request-fixture"
    assert self_result["event"] == self_focus and self_result["anchor"]["event"] == stored[0]
    assert (self_reply["kind"], self_reply["author"], self_reply["target"], self_reply["text"]) == (
        "self", "SELF", "group", DELIVERY_TEXT,
    )
    assert self_body["state"]["focus"]["reply_to"] == self_reply["id"]
    assert self_body["state"]["focus"]["target"] == FOCUS_PERSON
    assert [(state, json.loads(usage)) for state, usage in attempts] == [("response", {"input": 21, "output": 4})] * 3
    assert accepted == turns == [(seed,), (self_focus,)] and len(main_requests) == 3 and reader == expected_reader
    assert not result["invited"] and result["rule"] is result["semantic"] is None
    assert self_result["invited"] and self_result["rule"] == {
        "event": self_focus, "accepted": True, "newly_accepted": True,
    }
    assert self_result["semantic"] == {"event": self_focus, "accepted": True, "newly_accepted": False}
    assert [row["quiet"] for row in self_result["feedback"]["executions"]] == [True]
    assert self_result["binding"]["actor"] == FOCUS_PERSON
    assert self_result["binding"]["basis"] == [{"event_id": f"event:{self_focus}", "revision": 1}]
    assert (result["snapshot_revision"], literal_result["snapshot_revision"], self_result["snapshot_revision"]) == (1, 2, 3)
    assert cold == {"snapshot_revision": 3, "receipt": self_result["receipt"],
                    "result_sha256": prior_result, "ref": self_result["focus"]["ref"]}
    assert cold_attempts == len(attempts) and cold_inputs == turns
    for review in (result, literal_result, self_result):
        assert len(review["observations"]) == 2 and review["observations"][0] == review["observations"][1]
        assert not review["observations"][0]["invalid"]
    return {"status": "PASS", "card_status": "in_progress", "published": False,
            "reader": reader, "paid_calls": 0, "physical_attempts": len(attempts),
            "accepted_main": len(accepted) - 1, "seed_main": seed, "model_wire": body, "peer": result,
            "literal_model_wire": literal_body, "literal_peer": literal_result,
            "self_model_wire": self_body, "self_peer": self_result, "cold": cold}
