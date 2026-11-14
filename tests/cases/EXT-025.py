"""Replay one authorized Jev review through the real SDK and pinned library."""

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

from rebuild_intake import Owner, sha, wait_for, write


HOST_METHODS = ["observe.metadata", "participation.source", "forget.owner", "llm.complete", "llm.result"]
FIXTURE_KEY = "ext025-fixture"
FOCUS_PERSON = "00000000-0000-4000-8000-000000000025"
MENTION_PERSON = "00000000-0000-4000-8000-000000000026"


def prepare(root, output):
    archive = Path(os.environ["YUKI_CORE050_CANDIDATE"])
    source = Path(os.environ["YUKI_PARTICIPATION_SOURCE"])
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
    return "native-jev-intake.json", report


def replay(root, output, workspace, executable, library, sdk, expected_reader):
    owner = Owner(workspace, executable, output)
    space = '["qq","ext025","720"]'
    with owner.running():
        entry = owner.op("entry", "group", space)["entry"]
        actors = []
        for person, native in ((FOCUS_PERSON, "200"), (MENTION_PERSON, "202")):
            owner.op("person", "create", person)
            actors.append(owner.op("account", "open", "qq", "ext025", native, 1,
                                   "--person", person, "--start", 1))
        bot = owner.op("account", "open", "qq", "ext025", "100", 1, "--start", 1)

    requests = []

    class Jev(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"path": self.path, "body": body,
                             "credential": self.headers.get("Authorization") == f"Bearer {FIXTURE_KEY}"})
            answers = {}
            for name, question in body["questions"].items():
                criteria = question["criteria"]
                choice = "unknown"
                answers[name] = {"type": "choice", "choice": choice,
                                 "probabilities": {key: float(key == choice) for key in criteria}}
            data = json.dumps({"model": "jev-response-fixture", "answers": answers,
                               "usage": {"input_tokens": 21, "output_tokens": 4}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    with ThreadingHTTPServer(("127.0.0.1", 0), Jev) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            owner.env["YUKI_EXT025_KEY"] = FIXTURE_KEY
            owner.env["PYTHONPATH"] = os.pathsep.join(
                (str(library), str(sdk), *(path for path in sys.path if "site-packages" in path))
            )
            write(owner.probe_root / "config.json", {"entry": entry})
            peer = root / "tests/peers/participation-source-probe/jev_replay.py"
            with (owner.data / "yuki.toml").open("a", encoding="utf-8") as stream:
                stream.write(
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
                def record(key, native, who, segments, timestamp):
                    frame = {"source": key, "native_id": native, "account": who["account"],
                             "bot_stage": bot["assignment"], "reply_bot": "100",
                             "space": space, "kind": "message", "observed": timestamp,
                             "occurred": timestamp, "segments": segments}
                    return owner.op("ingress", "record", json.dumps(frame, ensure_ascii=False))["event"]

                for _ in range(240):
                    status = owner.op("host", "status")
                    if len(status["plugins"]) == 1 and status["plugins"][0]["online"]:
                        break
                    time.sleep(0.05)
                else:
                    raise TimeoutError("diagnostic SDK peer never became online")
                anchor = record("original-anchor", "36011", actors[1],
                                [{"type": "text", "text": "原先的群消息"}], 100)
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
                ], 200)
                result = wait_for(owner.probe_root / "result.json", timeout=20)
                with closing(sqlite3.connect((owner.data / "core.sqlite").as_uri() + "?mode=ro", uri=True)) as db:
                    attempts = db.execute("SELECT state,usage_json FROM model_attempts").fetchall()
                    accepted, = db.execute("SELECT count(*) FROM accepted_sources").fetchone()
                    reader, = db.execute("SELECT max(version) FROM _sqlx_migrations").fetchone()
        finally:
            server.shutdown()
            thread.join()

    assert len(requests) == 1 and requests[0]["path"] == "/systemone" and requests[0]["credential"]
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
    assert [(state, json.loads(usage)) for state, usage in attempts] == [("response", {"input": 21, "output": 4})]
    assert accepted == 0 and reader == expected_reader
    assert len(result["observations"]) == 2 and result["observations"][0] == result["observations"][1]
    assert not result["observations"][0]["invalid"]
    return {"status": "PASS", "card_status": "in_progress", "published": False,
            "reader": reader, "paid_calls": 0, "physical_attempts": len(attempts),
            "accepted_main": accepted, "model_wire": body, "peer": result}
