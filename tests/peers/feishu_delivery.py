"""Drive real native Feishu/Lark gateways through Main and original effect receipts."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from urllib.parse import parse_qs, unquote, urlsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ci"))
from personal_preview import free_address
from telegram_attachment_delivery import materialize, write
from feishu_upload import Upload
from feishu_mentions import Mentions


def exercise(root, package, output, domain, scenario):
    output.mkdir(parents=True)
    manifest = json.loads((package / "package-manifest.json").read_bytes())
    binary = package / ("yuki-feishu.exe" if os.name == "nt" else "yuki-feishu")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    assert digest == manifest["artifacts"][binary.name]
    assert all(row["exit_code"] == 0 for row in manifest["commands"])
    with tempfile.TemporaryDirectory(
        prefix="fs-send-", dir="/tmp" if os.name != "nt" else None
    ) as temporary:
        work = Path(temporary)
        contract = json.loads((root / "catalog/feishu.json").read_bytes())["source"][
            "sdk_contract"
        ]
        host, pin, target = materialize(root, work, Path(contract).parent.name)
        spec = importlib.util.spec_from_file_location(
            "native_feishu", root / "tests/cases/EXT-005.py"
        )
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        Frame, serve = fixture.fixture_imports(root, work)
        app, tenant, namespace = "cli_" + domain, "tenant-" + domain, "fs." + domain
        person = str(uuid.uuid4())
        mentions = Mentions(scenario) if scenario.startswith("mention-") else None
        upload = Upload(scenario) if scenario.startswith("upload-") else None
        if scenario == "mention-caption":
            upload = Upload("upload-file")
            upload.caption = mentions.text
        private = scenario in {"private", "upload-private", "mention-private"}
        thread = scenario not in {
            "private",
            "group",
            "upload-private",
            "mention-private",
            "mention-group",
        }
        quoted = scenario in {"reply", "upload-reply", "upload-reply-only"}
        recalling = scenario.startswith("recall")
        long = scenario in {"parts", "lost", "rejected", "expiry", "reply"}
        text = '雪\n"\\🌨' * 21000 if long else "原應用 original text"
        native, tokens, models, errors, acks, operations = [], [], [], [], [], []
        done, shutting = threading.Event(), threading.Event()
        data, trace = work / "owner", output / "wire.jsonl"
        env = dict(
            os.environ,
            NO_PROXY="127.0.0.1,localhost",
            no_proxy="127.0.0.1,localhost",
            YUKI_FEISHU_APP_ID=app,
            YUKI_FEISHU_APP_SECRET="fixture-" + app,
            YUKI_FEISHU_TENANT=tenant,
            YUKI_FEISHU_DOMAIN=domain,
            YUKI_FEISHU_PROXY="",
            YUKI_FEISHU_CURL=os.environ.get("YUKI_FEISHU_CURL", "curl"),
        )

        def cli(*args, check=True):
            result = subprocess.run(
                [host, "--data", data, *map(str, args)],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf8",
                timeout=15,
            )
            if result.returncode:
                if check:
                    raise RuntimeError(result.stderr)
                return None
            return json.loads(result.stdout) if result.stdout.strip() else None

        def operator(*args):
            result = cli("operator", *args)
            operations.append({"arguments": args, "result": result})
            write(output / "operations.json", operations)
            return result

        def event():
            return {
                "header": {
                    "app_id": app,
                    "tenant_key": tenant,
                    "event_type": "im.message.receive_v1",
                },
                "event": {
                    "sender": {
                        "sender_type": "user",
                        "sender_id": {"open_id": "ou_original"},
                    },
                    "message": {
                        "message_id": "om_original",
                        "chat_id": "oc_original",
                        "chat_type": "p2p" if private else "group",
                        "create_time": str(int(time.time() * 1000)),
                        "message_type": "text",
                        "content": json.dumps({"text": "@_user_1 send original text"}),
                        "mentions": [
                            {"key": "@_user_1", "id": {"open_id": app}, "name": "Yuki"}
                        ],
                        **(
                            {"thread_id": "omt_original", "root_id": "om_root"}
                            if thread
                            else {}
                        ),
                    },
                },
            }

        packet = event()
        if mentions:
            mentions.event(packet)

        def socket(conn):
            try:
                initial = Frame.FromString(conn.recv(timeout=8))
                assert any(
                    h.key == "type" and h.value == "ping" for h in initial.headers
                )
                frame = Frame(
                    SeqID=17,
                    LogID=81,
                    service=9,
                    method=1,
                    payload=json.dumps(packet).encode(),
                )
                for key, value in {
                    "type": "event",
                    "message_id": "17",
                    "sum": "1",
                    "seq": "0",
                }.items():
                    frame.headers.add(key=key, value=value)
                conn.send(frame.SerializeToString())
                while not shutting.is_set():
                    try:
                        received = Frame.FromString(conn.recv(timeout=1))
                    except TimeoutError:
                        continue
                    kind = next(h.value for h in received.headers if h.key == "type")
                    if kind == "ping":
                        pong = Frame(
                            SeqID=0,
                            LogID=0,
                            service=9,
                            method=0,
                            payload=b'{"PingInterval":1}',
                        )
                        pong.headers.add(key="type", value="pong")
                        conn.send(pong.SerializeToString())
                    else:
                        assert received.SeqID == 17 and json.loads(
                            received.payload
                        ) == {"code": 200}
                        acks.append({"app": app, "message": "om_original", "code": 200})
            except Exception as exc:
                from websockets.exceptions import ConnectionClosed

                if not isinstance(exc, ConnectionClosed):
                    errors.append(traceback.format_exc())

        websocket = serve(socket, "127.0.0.1", 0, ping_interval=None)

        class API(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, value, status=200):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                try:
                    self.dispatch(False)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    errors.append(traceback.format_exc())
                    done.set()
                    self.reply({"code": -1}, 500)

            def do_DELETE(self):
                try:
                    self.dispatch(True)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as exc:
                    errors.append(traceback.format_exc())
                    done.set()
                    self.reply({"code": -1}, 500)

            def dispatch(self, recall):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if upload and self.path in {
                    "/open-apis/im/v1/images",
                    "/open-apis/im/v1/files",
                }:
                    return upload.receive(self, raw, native, domain, len(tokens))
                body = json.loads(raw) if raw else None
                if self.path == "/callback/ws/endpoint":
                    assert body == {"AppID": app, "AppSecret": "fixture-" + app}
                    return self.reply(
                        {
                            "code": 0,
                            "data": {
                                "URL": f"ws://127.0.0.1:{websocket.socket.getsockname()[1]}/socket?service_id=9",
                                "ClientConfig": {
                                    "PingInterval": 1,
                                    "ReconnectInterval": 1,
                                    "ReconnectCount": 0,
                                    "ReconnectNonce": 0,
                                },
                            },
                        }
                    )
                if self.path == "/model":
                    models.append(body)
                    count, call = len(models), None
                    if count == 1:
                        call = ("get_my_capabilities", {})
                    elif count == 2:
                        args = (
                            upload.args(operator, models, person)
                            if upload
                            else {"text": mentions.text if mentions else text}
                        )
                        if quoted:
                            wire = [
                                json.loads(line)
                                for line in trace.read_bytes().splitlines()
                            ]
                            original = next(
                                v["frame"]
                                for v in wire
                                if v["frame"].get("method") == "gateway.inbound"
                            )
                            accepted = next(
                                v["frame"]["result"]
                                for v in wire
                                if v["direction"] == "from_host"
                                and v["frame"].get("id") == original["id"]
                            )
                            args["reply_to_event_id"] = accepted["event"]
                        call = ("send", args)
                    elif (
                        scenario in {"token-rejected", "upload-token-recovered"}
                        and count == 3
                    ):
                        refused = json.loads(
                            next(
                                v["content"]
                                for v in reversed(body["messages"])
                                if v.get("role") == "tool"
                            )
                        )
                        assert (
                            refused["state"] == "failed"
                            and len(native) == len(tokens) == 1
                        )
                        call = ("send", {"text": upload.caption if upload else text})
                    elif recalling and count == 3:
                        call = (
                            "query_chat_history",
                            {"view": "recent", "author_kind": "yuki", "limit": 1},
                        )
                    elif recalling and count in (4, 5):
                        history = json.loads(
                            next(
                                v["content"]
                                for v in body["messages"]
                                if v.get("tool_call_id") == "original-3"
                            )
                        )["result"]
                        assert len(history["events"]) == 1
                        call = (
                            "recall_own_message",
                            {"event_id": history["events"][0]["event_id"]},
                        )
                    message = {"role": "assistant", "content": "finished"}
                    if call:
                        message.update(
                            content=None,
                            tool_calls=[
                                {
                                    "id": "original-" + str(count),
                                    "type": "function",
                                    "function": {
                                        "name": call[0],
                                        "arguments": json.dumps(
                                            call[1], ensure_ascii=False
                                        ),
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
                    if count == (
                        6
                        if recalling
                        else (
                            4
                            if scenario in {"token-rejected", "upload-token-recovered"}
                            else 3
                        )
                    ):
                        done.set()
                    return
                if self.path == "/open-apis/auth/v3/tenant_access_token/internal":
                    assert body == {"app_id": app, "app_secret": "fixture-" + app}
                    tokens.append(
                        {"app": app, "tenant": tenant, "number": len(tokens) + 1}
                    )
                    return self.reply(
                        {
                            "code": 0,
                            "tenant_access_token": f"fixture-{domain}-{len(tokens)}",
                            "expire": 1 if scenario == "expiry" else 300,
                        }
                    )
                assert (
                    self.headers["Authorization"]
                    == f"Bearer fixture-{domain}-{len(tokens)}"
                )
                native.append(
                    {
                        "method": "DELETE" if recall else "POST",
                        "path": self.path,
                        "body": body,
                        "token": len(tokens),
                        "app": app,
                        "tenant": tenant,
                    }
                )
                if recall:
                    assert self.path == "/open-apis/im/v1/messages/om_sent_1"
                    if scenario == "recall-rejected":
                        return self.reply({"code": 230006}, 403)
                    if scenario == "recall-lost":
                        self.close_connection = True
                        return
                    return self.reply({"code": 0, "data": {}})
                index = len(native) - int(upload is not None)
                location = urlsplit(self.path)
                if thread:
                    parent = "om_original" if quoted and index == 1 else "om_root"
                    assert (
                        unquote(location.path)
                        == "/open-apis/im/v1/messages/" + parent + "/reply"
                    ), self.path
                    assert body["reply_in_thread"] is True
                else:
                    assert location.path == "/open-apis/im/v1/messages"
                    assert parse_qs(location.query) == {
                        "receive_id_type": ["open_id" if private else "chat_id"]
                    }
                    assert body["receive_id"] == (
                        "ou_original" if private else "oc_original"
                    )
                if upload:
                    return upload.visible(self, body, native)
                assert body["msg_type"] == "text" and isinstance(
                    json.loads(body["content"])["text"], str
                )
                if scenario == "token-rejected" and index == 1:
                    return self.reply({"code": 99991663}, 400)
                if scenario == "expiry":
                    time.sleep(1.05)
                if scenario in {"lost", "mention-lost"} and index == 2:
                    self.close_connection = True
                    return
                if scenario in {"rejected", "mention-rejected"} and index == 2:
                    return self.reply({"code": 230006}, 403)
                if scenario == "malformed":
                    return self.reply({"code": 0, "data": {}})
                return self.reply(
                    {"code": 0, "data": {"message_id": "om_sent_" + str(index)}}
                )

        server = ThreadingHTTPServer(("127.0.0.1", 0), API)
        threads = [
            threading.Thread(target=obj.serve_forever, daemon=True)
            for obj in (server, websocket)
        ]
        for t in threads:
            t.start()
        env["YUKI_FEISHU_API"] = "http://127.0.0.1:" + str(server.server_port)

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
                until = time.monotonic() + 12
                while not cli("operator", "database-info", check=False):
                    assert (
                        time.monotonic() < until and proc.poll() is None
                    ), "Host startup failed"
                    time.sleep(0.05)
                yield
                operator("shutdown")
                assert proc.wait(timeout=15) == 0
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

        try:
            cli("init", "--memory-mode", "lexical-only")
            cfg = data / "yuki.toml"
            initial = cfg.read_text().replace(
                '"127.0.0.1:0"', json.dumps(free_address())
            )
            initial += (
                "\n[main]\nendpoint="
                + json.dumps(env["YUKI_FEISHU_API"] + "/model")
                + '\nmodel="fixture"\nname="Yuki"\nmax_output=12000\nroot_slots=8\nroot_tool_calls=8\nmerge_ms=1\nmax_input_units=1200000\ncompact_soft_tokens=4000000\n'
            )
            cfg.write_text(initial)
            if upload:
                inputs = data / "media-inputs"
                inputs.mkdir(exist_ok=True)
                (inputs / "original.bin").write_bytes(upload.payload)
            with running():
                operator("person", "create", person)
                original_account = operator(
                    "account",
                    "open",
                    domain,
                    namespace,
                    "ou_original",
                    1,
                    "--person",
                    person,
                    "--start",
                    1,
                )
                if mentions:
                    mentions.account(original_account)
                stage = operator(
                    "account", "open", domain, namespace, app, 1, "--start", 1
                )["assignment"]
            grants = [
                "gateway.inbound",
                "gateway.media",
                "gateway.send",
                "forget.owner",
            ]
            if upload and scenario != "upload-denied":
                grants.append("media.open")
            if scenario == "denied":
                grants.remove("gateway.send")
            if recalling and scenario != "recall-denied":
                grants.append("gateway.recall")
            fields = {
                "id": "feishu",
                "namespace": namespace,
                "platform": domain,
                "bot_stage": stage,
                "program": sys.executable,
                "args": [
                    str(root / "tests/peers/observe_stdio.py"),
                    str(binary),
                    str(trace),
                ],
                "grants": grants,
                "env": [k for k in env if k.startswith("YUKI_FEISHU_")],
            }
            fields["erasure_args"] = fields["args"]
            cfg.write_text(
                initial
                + "\n[[plugins]]\n"
                + "\n".join(k + "=" + json.dumps(v) for k, v in fields.items())
                + "\n[plugins.gateway_media]\napplication="
                + json.dumps(app)
                + "\ntenant="
                + json.dumps(tenant)
                + "\n"
            )
            with running():
                assert done.wait(60), "Main did not finish"
                assert not errors, errors
                ack_deadline = time.monotonic() + 10
                while not acks:
                    assert (
                        time.monotonic() < ack_deadline
                    ), "initial durable ACK missing"
                    time.sleep(0.05)
                result = json.loads(
                    next(
                        v["content"]
                        for v in reversed(models[-1]["messages"])
                        if v.get("role") == "tool"
                    )
                )
            expected = (
                "unknown"
                if scenario in {"lost", "malformed", "recall-lost"}
                else (
                    "failed"
                    if scenario
                    in {"denied", "rejected", "recall-rejected", "recall-denied"}
                    else "confirmed"
                )
            )
            if upload:
                expected = upload.expected
            if mentions:
                expected = mentions.expected
            assert result["state"] == expected, result
            counts = len(native), len(models), len(tokens)
            with running():
                assert (
                    operator(
                        "effect", "read", result["namespace"], result["id"], person
                    )
                    == result
                )
                if scenario == "upload-token-recovered":
                    first = json.loads(
                        next(
                            v["content"]
                            for v in models[-1]["messages"]
                            if v.get("tool_call_id") == "original-2"
                        )
                    )
                    assert (
                        first["state"] == "failed"
                        and len(first["result"]["parts"]) == 1
                    )
                    assert (
                        operator(
                            "effect", "read", first["namespace"], first["id"], person
                        )
                        == first
                    )
                until = time.monotonic() + 10
                while len(acks) < 2:
                    assert time.monotonic() < until, "cold duplicate not acknowledged"
                    time.sleep(0.05)
                time.sleep(0.2)
            assert (
                len(native),
                len(models),
                len(tokens),
            ) == counts, "cold duplicate dispatched another effect"
            assert acks and not errors, errors
            if (
                expected == "confirmed"
                and not upload
                and not mentions
                and not recalling
                and scenario != "token-rejected"
            ):
                assert (
                    "".join(
                        json.loads(row["body"]["content"])["text"] for row in native
                    )
                    == text
                )
            if upload:
                upload.verify(
                    result,
                    native,
                    tokens,
                    [json.loads(line) for line in trace.read_bytes().splitlines()],
                    rendered_caption=mentions.rendered if mentions else None,
                )
            elif mentions:
                assert len(native) >= 1
            elif long:
                assert len(native) == (2 if scenario in {"lost", "rejected"} else 3), {
                    "scenario": scenario,
                    "native_requests": len(native),
                }
            elif scenario == "token-rejected":
                assert len(native) == len(tokens) == 2
            elif scenario == "denied":
                assert native == tokens == []
            elif recalling:
                assert len(native) == (1 if scenario == "recall-denied" else 2)
            else:
                assert len(native) == 1
            if scenario == "expiry":
                assert len(tokens) == len(native)
            mention_proof = (
                mentions.verify(
                    result,
                    native,
                    [json.loads(line) for line in trace.read_bytes().splitlines()],
                )
                if mentions
                else None
            )
            proof = {
                "status": "PASS",
                "domain": domain,
                "scenario": scenario,
                "state": expected,
                "receipt": result,
                "native_requests": len(native),
                "token_issuances": len(tokens),
                "original_receipt_reopened": True,
                "source_commit": pin["source_commit"],
                "host_sha256": target["binary_sha256"],
                "host_zip_sha256": target["sha256"],
                "plugin_sha256": digest,
                "paid_calls": 0,
                **({"mentions": mention_proof} if mentions else {}),
            }
            write(output / "delivery.json", proof)
            return proof
        finally:
            shutting.set()
            websocket.shutdown()
            server.shutdown()
            server.server_close()
            for t in threads:
                t.join(timeout=3)
            for name, value in [
                ("native", native),
                ("models", models),
                ("tokens", tokens),
                ("errors", errors),
                ("acks", acks),
            ]:
                write(output / (name + ".json"), value)
