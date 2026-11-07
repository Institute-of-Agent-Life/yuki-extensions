"""Read an original immutable attachment and send it through a real Rust gateway."""

import argparse
from contextlib import contextmanager
from email import policy
from email.parser import BytesParser
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ci"))
from personal_preview import free_address


def write(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def materialize(root, work, contract="core-038-outbound"):
    sys.path.insert(0, str(root / "compat/base"))
    from verify_dist import native_target, verify

    pin = json.loads((root / "compat" / contract / "source.lock.json").read_bytes())
    expected = pin["platforms"]["-".join(native_target())]
    key = work / "signer.pub"
    key.write_bytes((expected["signer"] + "\n").encode("ascii"))
    assert hashlib.sha256(key.read_bytes()).hexdigest() == expected["signer_sha256"]
    meta = verify(
        os.environ["YUKI_HOST_CANDIDATE"],
        key,
        pin["source_commit"],
        expected["sha256"],
        pin["fixtures_sha256"],
        destination=work / "host",
    )
    assert not meta["dirty"] and meta["source_tree_sha256"] == pin["source_tree_sha256"]
    assert meta["host_schema_sha256"] == pin["schema_sha256"]
    binary = work / "host/bin" / ("yuki-core.exe" if os.name == "nt" else "yuki-core")
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == expected["binary_sha256"]
    return binary, pin, expected


def exercise(root, package, output, scenario):
    output.mkdir()
    manifest = json.loads((package / "package-manifest.json").read_bytes())
    binary = package / ("yuki-telegram.exe" if os.name == "nt" else "yuki-telegram")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert digest == manifest["artifacts"][binary.name]
    assert all(command["exit_code"] == 0 for command in manifest["commands"])
    with tempfile.TemporaryDirectory(
        prefix="tg-out-", dir="/tmp" if os.name != "nt" else None
    ) as scratch:
        work = Path(scratch)
        host, pin, target = materialize(root, work)
        data = work / "owner"
        trace = output / "gateway.jsonl"
        native, models, operations, errors, activity = [], [], [], [], []
        person = str(uuid.uuid4())
        finished = threading.Event()
        cleanup_started = threading.Event()
        quoted = scenario.startswith("reply")
        recalling = scenario.startswith("recall")
        typing = scenario.startswith("typing")
        grouped = quoted or recalling or (typing and scenario != "typing-private")
        chat = -15 if grouped else 8
        topic = 7 if grouped else None
        payload = b"Yuki original attachment\n" + bytes(range(251)) * 97
        caption = (
            "雪" * 1023 + "🌨" + "a" * 4097
            if scenario.startswith("caption") or quoted else ""
        )
        env = dict(
            os.environ,
            NO_PROXY="127.0.0.1,localhost",
            no_proxy="127.0.0.1,localhost",
            YUKI_TELEGRAM_BOT_ID="101",
            YUKI_TELEGRAM_TOKEN="101:fixture",
            YUKI_TELEGRAM_STATE=str(work / "cursor"),
            YUKI_TELEGRAM_CURL=os.environ.get("YUKI_TELEGRAM_CURL")
            or shutil.which("curl")
            or "curl",
        )

        def cli(*args, check=True):
            proc = subprocess.run(
                [host, "--data", data, *map(str, args)],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            if not check and proc.returncode:
                return None
            if proc.returncode:
                raise RuntimeError(proc.stderr)
            return json.loads(proc.stdout) if proc.stdout.strip() else None

        def operator(*args):
            value = cli("operator", *args)
            operations.append({"arguments": list(args), "result": value})
            write(output / "operations.json", operations)
            return value

        class Endpoint(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, body, status=200):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                try:
                    self.dispatch()
                except ConnectionError:
                    pass
                except Exception as exc:
                    errors.append(str(exc))
                    finished.set()
                    self.reply({"error": "fixture failure"}, 500)

            def dispatch(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/bot101:fixture/getMe":
                    if cleanup_started.is_set():
                        frames = [
                            json.loads(line)["frame"]
                            for line in trace.read_bytes().splitlines()
                        ]
                        request = next(
                            v for v in frames if v.get("method") == "forget.request"
                        )
                        assert any(
                            v.get("id") == request["id"]
                            and v.get("result", {}).get("key")
                            == request["params"]["key"]
                            for v in frames
                        ), "Bot connection opened before cleanup acknowledgement"
                    return self.reply(
                        {
                            "ok": True,
                            "result": {
                                "id": 101,
                                "username": "OriginalBot",
                                "is_bot": True,
                            },
                        }
                    )
                if self.path == "/bot101:fixture/getUpdates":
                    offset = json.loads(body).get("offset", 0)
                    if offset > 41:
                        time.sleep(0.08)
                    event = {
                        "update_id": 41,
                        "message": {
                            "message_id": 9,
                            "date": int(time.time()),
                            "from": {"id": 8},
                            "chat": {"id": chat, "type": "supergroup" if grouped else "private"},
                            "text": "@OriginalBot send the selected original attachment.",
                            "entities": [{"type":"mention","offset":0,"length":12}],
                            **({"message_thread_id": topic} if grouped else {}),
                        },
                    }
                    return self.reply(
                        {"ok": True, "result": [] if offset > 41 else [event]}
                    )
                if self.path == "/model":
                    models.append(json.loads(body))
                    count = len(models)
                    call = None
                    if count == 1:
                        if typing:
                            time.sleep(3.6)
                        call = ("get_my_capabilities", {})
                    elif count == 2:
                        receipt = json.loads(
                            next(
                                v["content"]
                                for v in reversed(models[-1]["messages"])
                                if v.get("role") == "tool"
                            )
                        )
                        selected = operator(
                            "media",
                            "snapshot",
                            receipt["namespace"],
                            person,
                            receipt["id"],
                            "original.bin",
                            "original.bin",
                            "file",
                        )
                        args = {
                            "artifact_id": selected["artifact_id"],
                            "attachment_kind": "file",
                            "name": "shared.bin",
                        }
                        if caption:
                            args["text"] = caption
                        if quoted:
                            frames = [json.loads(line) for line in trace.read_bytes().split(b"\n")[:-1]]
                            inbound = next(v["frame"] for v in frames if v["frame"].get("method") == "gateway.inbound")
                            original = next(v["frame"]["result"] for v in frames
                                if v["direction"] == "from_host" and v["frame"].get("id") == inbound["id"])
                            if scenario == "reply-text":
                                args = {"text": caption}
                            args["reply_to_event_id"] = original["event"]
                        call = ("send", args)
                    elif recalling and count == 3:
                        call = ("query_chat_history", {"view":"recent","author_kind":"yuki","limit":1})
                    elif recalling and count in (4, 5):
                        history = json.loads(next(v["content"] for v in models[-1]["messages"]
                            if v.get("tool_call_id") == "original-3"))["result"]
                        assert len(history["events"]) == 1, history
                        original_event = history["events"][0]
                        assert original_event["direction"] == "outbound", original_event
                        call = ("recall_own_message", {"event_id":original_event["event_id"]})
                    message = {"role": "assistant", "content": "finished"}
                    if scenario == "typing-disabled" and count == 3:
                        operator("host", "enable", "telegram", "false")
                        before = len(activity)
                        time.sleep(3.6)
                        assert len(activity) == before, "typing continued after disable"
                    if call:
                        message.update(
                            content=None,
                            tool_calls=[
                                {
                                    "id": "original-" + str(count),
                                    "type": "function",
                                    "function": {
                                        "name": call[0],
                                        "arguments": json.dumps(call[1]),
                                    },
                                }
                            ],
                        )
                    self.reply(
                        {
                            "choices": [
                                {
                                    "message": message,
                                    "finish_reason": "tool_calls" if call else "stop",
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 2,
                                "completion_tokens": 1,
                                "total_tokens": 3,
                            },
                        }
                    )
                    if count == (6 if recalling else 3):
                        finished.set()
                    return
                if self.path == "/bot101:fixture/sendChatAction":
                    args = json.loads(body)
                    assert args == {"chat_id":str(chat), "action":"typing",
                        **({"message_thread_id":topic} if grouped else {})}, args
                    activity.append({"method":"sendChatAction", "time":time.monotonic(), **args})
                    if scenario == "typing-lost":
                        time.sleep(8)
                        self.close_connection = True
                        return
                    if scenario == "typing-rejected":
                        return self.reply({"ok":False, "error_code":403}, 403)
                    return self.reply({"ok":True, "result":{} if scenario == "typing-malformed" else True})
                if self.path == "/bot101:fixture/deleteMessage":
                    args = json.loads(body)
                    assert args == {"chat_id":str(chat),"message_id":121}, args
                    native.append({"method":"deleteMessage", **args})
                    if scenario == "recall-lost":
                        self.close_connection = True
                        self.connection.shutdown(socket.SHUT_RDWR)
                        return
                    if scenario == "recall-rejected":
                        return self.reply({"ok":False,"error_code":403}, 403)
                    return self.reply({"ok":True,"result":{} if scenario == "recall-malformed" else True})
                if self.path == "/bot101:fixture/sendDocument":
                    header = (
                        "Content-Type: "
                        + self.headers["content-type"]
                        + "\r\nMIME-Version: 1.0\r\n\r\n"
                    ).encode()
                    message = BytesParser(policy=policy.default).parsebytes(
                        header + body
                    )
                    fields = {
                        p.get_param("name", header="content-disposition"): p
                        for p in message.iter_parts()
                    }
                    raw = fields["document"].get_payload(decode=True)
                    assert (
                        raw == payload
                        and fields["document"].get_filename() == "shared.bin"
                    )
                    assert fields["chat_id"].get_content().strip() == str(chat)
                    observed_topic = int(fields["message_thread_id"].get_content()) if "message_thread_id" in fields else None
                    assert observed_topic == topic
                    reply = json.loads(fields["reply_parameters"].get_content()) if "reply_parameters" in fields else None
                    assert reply == ({"message_id":9,"allow_sending_without_reply":False} if quoted else None)
                    observed_caption = (
                        fields["caption"].get_payload(decode=True).decode()
                        if "caption" in fields
                        else ""
                    )
                    assert observed_caption == caption[:1024]
                    native.append(
                        {
                            "method": "sendDocument",
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "size": len(raw),
                            "caption": observed_caption,
                            "chat": str(chat),
                            "topic": observed_topic,
                            "reply_parameters": reply,
                        }
                    )
                elif self.path == "/bot101:fixture/sendMessage":
                    args = json.loads(body)
                    assert args["chat_id"] == str(chat)
                    assert args.get("message_thread_id") == topic
                    assert args.get("reply_parameters") == (
                        {"message_id":9,"allow_sending_without_reply":False}
                        if quoted and not native else None
                    )
                    native.append(
                        {"method": "sendMessage", "text": args["text"], "chat": str(chat),
                         "topic": topic, "reply_parameters": args.get("reply_parameters")}
                    )
                else:
                    raise AssertionError("unexpected Telegram route " + self.path)
                if scenario == "lost" or (
                    scenario == "caption-lost" and len(native) == 2
                ):
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                if scenario == "rejected":
                    return self.reply({"ok": False, "error_code": 403}, 403)
                if scenario == "reply-rejected":
                    return self.reply({"ok": False, "error_code": 400,
                        "description": "Bad Request: message to be replied not found"}, 400)
                self.reply(
                    {
                        "ok": True,
                        "result": {"chat": {"id": chat}, "message_id": 120 + len(native)},
                    }
                )

        @contextmanager
        def running():
            with (output / "host.log").open("ab") as log:
                proc = subprocess.Popen(
                    [host, "--data", data, "run"],
                    cwd=work,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
            try:
                deadline = time.monotonic() + 15
                while not cli("operator", "database-info", check=False):
                    if proc.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("original Host failed to start")
                    time.sleep(0.05)
                yield
                operator("shutdown")
                assert proc.wait(timeout=15) == 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

        with ThreadingHTTPServer(("127.0.0.1", 0), Endpoint) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            api = "http://127.0.0.1:" + str(server.server_port)
            env["YUKI_TELEGRAM_API"] = api
            try:
                cli("init", "--memory-mode", "lexical-only")
                cfg = data / "yuki.toml"
                initial = cfg.read_text(encoding="utf-8").replace(
                    '"127.0.0.1:0"', json.dumps(free_address())
                )
                initial += (
                    "\n[main]\nendpoint="
                    + json.dumps(api + "/model")
                    + '\nmodel="fixture"\nname="Yuki"\nmax_output=12000\nroot_slots=8\nroot_tool_calls=8\nmerge_ms=1\nmax_input_units=1200000\n'
                )
                cfg.write_text(initial, encoding="utf-8")
                inputs = data / "media-inputs"
                inputs.mkdir(exist_ok=True)
                (inputs / "original.bin").write_bytes(payload)
                with running():
                    operator("person", "create", person)
                    operator(
                        "account",
                        "open",
                        "telegram",
                        "tg.original",
                        "8",
                        1,
                        "--person",
                        person,
                        "--start",
                        1,
                    )
                    stage = operator(
                        "account",
                        "open",
                        "telegram",
                        "tg.original",
                        "101",
                        1,
                        "--start",
                        1,
                    )["assignment"]
                grants = ["gateway.inbound", "gateway.media", "gateway.send"]
                if typing and scenario != "typing-denied":
                    grants.append("gateway.activity")
                if scenario != "denied":
                    grants.extend(["media.open", "forget.owner"])
                if recalling and scenario != "recall-denied":
                    grants.append("gateway.recall")
                fields = {
                    "id": "telegram",
                    "namespace": "tg.original",
                    "platform": "telegram",
                    "bot_stage": stage,
                    "program": sys.executable,
                    "args": [
                        str(root / "tests/peers/observe_stdio.py"),
                        str(binary),
                        str(trace),
                    ],
                    "grants": grants,
                    "env": [key for key in env if key.startswith("YUKI_TELEGRAM_")],
                }
                if scenario != "denied":
                    fields["erasure_args"] = fields["args"]
                cfg.write_text(
                    initial
                    + "\n[[plugins]]\n"
                    + "\n".join(
                        key + "=" + json.dumps(value) for key, value in fields.items()
                    )
                    + '\n[plugins.gateway_media]\napplication="101"\n',
                    encoding="utf-8",
                )
                with running():
                    assert finished.wait(45), (
                        "Main did not receive the original delivery result"
                    )
                    assert not errors, errors
                    result = json.loads(
                        next(
                            v["content"]
                            for v in reversed(models[-1]["messages"])
                            if v.get("role") == "tool"
                        )
                    )
                    if typing:
                        if scenario not in {"typing-denied", "typing-disabled"}:
                            deadline = time.monotonic() + 8
                            while True:
                                frames = [json.loads(line)["frame"] for line in trace.read_bytes().splitlines()]
                                if any(v.get("method") == "gateway.activity" and
                                    v["params"]["enabled"] is False for v in frames):
                                    break
                                assert time.monotonic() < deadline, "turn did not end its activity lease"
                                time.sleep(.05)
                            assert len(activity) >= 2, activity
                        elif scenario == "typing-denied":
                            assert activity == [], activity
                        else:
                            assert len(activity) >= 2, activity
                        before = len(activity)
                        time.sleep(3.6)
                        assert len(activity) == before, "typing renewed after turn ended"
                expected = (
                    "unknown"
                    if scenario in {"lost", "caption-lost", "recall-lost", "recall-malformed"}
                    else "failed"
                    if scenario in {"denied", "rejected", "reply-rejected", "recall-rejected", "recall-denied"}
                    else "confirmed"
                )
                assert result["state"] == expected, result
                count = len(native)
                with running():
                    cold = operator(
                        "effect", "read", result["namespace"], result["id"], person
                    )
                    assert cold == result
                    time.sleep(0.15)
                    if scenario == "forget":
                        operator("host", "enable", "telegram", "false")
                        forgotten = operator(
                            "privacy", "forget", "erase-original", person
                        )
                        assert "telegram" in forgotten["owners_pending"], forgotten
                        cleanup_started.set()
                        operator("host", "enable", "telegram", "true")
                        deadline = time.monotonic() + 10
                        while operator("privacy", "pending", "telegram")["obligations"]:
                            assert time.monotonic() < deadline, (
                                "original cleanup acknowledgement missing"
                            )
                            time.sleep(0.05)
                        assert not errors, errors
                assert len(native) == count
                expected_calls = {"denied": 0, "caption": 3, "caption-lost": 2,
                    "reply": 3, "reply-text": 2}.get(
                    scenario, 1
                )
                if recalling:
                    expected_calls = 1 if scenario == "recall-denied" else 2
                assert len(native) == expected_calls, native
                if recalling:
                    for model in models[4:]:
                        for message in model["messages"]:
                            if message.get("tool_call_id") in {"original-4", "original-5"}:
                                assert json.loads(message["content"])["state"] == expected
                if scenario in {"caption", "reply"}:
                    assert (
                        native[0]["caption"] + "".join(v["text"] for v in native[1:])
                        == caption
                    )
                if scenario == "reply-text":
                    assert "".join(v["text"] for v in native) == caption
            finally:
                server.shutdown()
                thread.join()
                write(output / "native.json", native)
                write(output / "models.json", models)
                write(output / "errors.json", errors)
                write(output / "activity.json", activity)
        proof = {
            "status": "PASS",
            "scenario": scenario,
            "plugin_sha256": digest,
            "host_sha256": target["binary_sha256"],
            "host_zip_sha256": target["sha256"],
            "core_source": pin["source_commit"],
            "paid_calls": 0,
            "native_requests": len(native),
            "activity_requests": len(activity),
            "activity_did_not_change_delivery": typing and result["state"] == "confirmed",
            "state": result["state"],
            "original_receipt_reopened": True,
            "receipt": result,
            "wire_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
        }
        write(output / "attachment-delivery.json", proof)
        return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--scenario",
        choices=[
            "confirmed",
            "lost",
            "rejected",
            "denied",
            "caption",
            "caption-lost",
            "forget",
            "reply",
            "reply-text",
            "reply-rejected",
            "recall", "recall-lost", "recall-rejected", "recall-denied", "recall-malformed",
            "typing", "typing-private", "typing-rejected", "typing-lost", "typing-malformed", "typing-denied", "typing-disabled",
        ],
        required=True,
    )
    args = parser.parse_args()
    exercise(
        Path(__file__).resolve().parents[2],
        args.package.resolve(),
        args.out.resolve(),
        args.scenario,
    )
