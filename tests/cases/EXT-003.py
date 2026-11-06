"""Exercise the native Telegram poller and a real, digest-verified CORE-032 host."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import runpy
import sys
import threading
import time

from package import build


def wait(until, seconds=25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = until()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError("timed out waiting for " + until.__name__)


def messages():
    def message(update, chat, mid, **fields):
        return {"update_id": update, "message": {"chat": {"id": chat, "type": "supergroup" if chat < 0 else "private"},
            "date": 1, "from": {"id": 17, "is_bot": False}, "message_id": mid, **fields}}
    first = message(10, 17, 1, text="🌨 @YukiBot", entities=[{"type": "mention", "offset": 3, "length": 8}])
    second = message(11, -80, 2, message_thread_id=7, caption="照片", photo=[{"file_id": "photo-id"}],
                     reply_to_message=first["message"])
    third = message(12, -81, 2, text="other group")
    edited = message(13, -80, 2, text="edited", message_thread_id=7, edit_date=2)
    edited["edited_message"] = edited.pop("message")
    migration = message(14, -81, 3, migrate_to_chat_id=-82)
    replay = dict(third, update_id=15)
    media_only = message(16, -80, 4, sticker={"file_id":"sticker", "is_animated":True})
    return [first, second, third, edited, migration, replay, media_only]


def prepare(root, output):
    from host_preview import materialize
    work = output / "work"
    work.mkdir()
    host, pin, expected = materialize(root, work)
    packages = output / "packages"
    package = build(root, "telegram", packages)
    consumer = json.loads((root / package["source"]["sdk_contract"]).read_bytes())
    plugin = packages / ("yuki-telegram.exe" if os.name == "nt" else "yuki-telegram")
    return exercise(root, output, host, plugin, {
        "card_status": "VERIFIED_ON_UNPUBLISHED_CANDIDATE", "scope": "development-host-crosswire",
        "published": False, "source_commit": pin["source_commit"], "host": expected,
        "host_sdk": pin["rust_crate_sha256"], "sdk": consumer["rust_crate_sha256"], "schema": pin["schema_sha256"],
    })


def exercise(root, output, host, plugin, qualification):
    work = output / "work"
    published = qualification["published"]
    data = work / "host-data"
    cursor_dir = work / "cursor"
    trace = work / "relay"
    trace.mkdir()
    (trace / "disconnect").touch()
    batches = messages()
    polls = []
    models = []
    data_only = threading.Event()
    resumed = threading.Event()
    finish_replay = threading.Event()

    class Native(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/model":
                models.append(body)
                payload = json.dumps({"id": "fixture", "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "done"}}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            path = self.path.split("/")
            bot = path[1].split(":")[0].removeprefix("bot")
            if bot not in ("101", "202") or path[-1] not in ("getMe", "getUpdates"):
                self.send_error(404)
                return
            if path[-1] == "getMe":
                result = {"id": int(bot), "username": "YukiBot", "is_bot": True}
            else:
                polls.append({"bot": bot, **body})
                available = batches if bot == "101" else [batches[0]]
                if bot == "101" and data_only.is_set():
                    available = [dict(batches[4], update_id=4)]
                result = [u for u in available if u["update_id"] >= body.get("offset", 0)]
                if (trace / "disconnected").exists() and not resumed.is_set() and bot == "101":
                    resumed.wait(15)
                if (trace / "reply-lost").exists() and bot == "101":
                    finish_replay.wait(15)
                if not result:
                    time.sleep(.2)
            payload = json.dumps({"ok":True,"result":result}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def handle(self):
            try:
                super().handle()
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                # A killed long poll can close its socket before the fixture responds.
                if not self.path.endswith("/getUpdates"):
                    raise

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = dict(os.environ, YUKI_TELEGRAM_BOT_ID="101", YUKI_TELEGRAM_TOKEN="101:fixture",
               YUKI_TELEGRAM_API=f"http://127.0.0.1:{server.server_port}", YUKI_TELEGRAM_STATE=str(cursor_dir))

    def cli(*args, check=True):
        result = subprocess.run([host,"--data",data,*args], cwd=work, env=env,
                                capture_output=True, text=True, timeout=20)
        if result.returncode and check:
            raise RuntimeError(f"{args} failed: {result.stderr[:400]}")
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None

    def start():
        nonlocal proc
        with (output / "host.txt").open("ab") as log:
            proc = subprocess.Popen([host,"--data",data,"run"], cwd=work, env=env, stdout=log, stderr=log)
        def ready():
            if proc.poll() is not None:
                raise RuntimeError((output / "host.txt").read_text(encoding="utf-8")[-900:])
            return cli("operator", "database-info", check=False)
        wait(ready)

    def stop():
        if proc and proc.poll() is None:
            cli("operator","shutdown",check=False)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    def install(bot, stage):
        cfg=data / "yuki.toml"
        base=cfg.read_text(encoding="utf-8").split("[[plugins]]")[0]
        values={"id":f"telegram-{bot}" if published else "telegram","namespace":f"tg.bot{bot}","program":sys.executable,
            "args":[str(root/"tests/peers/telegram_relay.py"),str(plugin),str(trace)],
            "platform":"telegram","bot_stage":stage,"grants":["gateway.inbound"],
            "env":["YUKI_TELEGRAM_BOT_ID","YUKI_TELEGRAM_TOKEN","YUKI_TELEGRAM_API","YUKI_TELEGRAM_STATE"]}
        cfg.write_text(base+"\n[[plugins]]\n"+"\n".join(f"{k} = {json.dumps(v)}" for k,v in values.items())+"\n",
                       encoding="utf-8")
        env.update(YUKI_TELEGRAM_BOT_ID=str(bot),YUKI_TELEGRAM_TOKEN=f"{bot}:fixture")

    def wire():
        return [json.loads(line) for line in (trace/"wire.jsonl").read_text(encoding="utf-8").splitlines()]

    proc = None
    try:
        cli("init")
        if published:
            from personal_preview import free_address
            cfg = data / "yuki.toml"
            top = cfg.read_text(encoding="utf-8").replace('"127.0.0.1:0"', json.dumps(free_address()))
            top = top.replace('mode = "hybrid"', 'mode = "lexical-only"')
            cfg.write_text(top + '\n[main]\nendpoint=' + json.dumps(env["YUKI_TELEGRAM_API"] + "/model")
                           + '\nmodel="fixture"\nname="Yuki"\nmax_output=2000\nroot_slots=24\nroot_tool_calls=24\n'
                           + 'merge_ms=1\nmax_input_units=1200000\nresult_page_budget=2000\nresult_storage_bytes=262144\n', encoding="utf-8")
        start()
        person = "00000000-0000-4000-8000-000000000003"
        cli("operator","person","create",person)
        for bot in (101,202):
            cli("operator","account","open","telegram",f"tg.bot{bot}","17","1","--person",person,"--start","1")
        stages={bot:cli("operator","account","open","telegram",f"tg.bot{bot}",str(bot),"1","--start","1")["assignment"]
                for bot in (101,202)}
        stop()
        if published:
            before = len(models)
            data_only.set()
            install(101, stages[101])
            start()
            wait(lambda: any(p.get("offset") == 5 and p["bot"] == "101" for p in polls))
            stop()
            frames = wire()
            data_call, = [r["frame"] for r in frames if r["frame"].get("method") == "gateway.inbound"]
            assert data_call["params"]["kind"] == "data" and not data_call["params"]["accept"]
            receipt, = [r["frame"]["result"] for r in frames if r["direction"] == "from_host"
                        and r["frame"].get("id") == data_call["id"] and "result" in r["frame"]]
            assert receipt["event"] > 0 and not receipt["accepted"] and len(models) == before
            qualification.update(data_only_event=receipt, model_http_before_data=before,
                                 model_http_after_data=len(models))
            data_only.clear()
        prior_frames = len(wire()) if published else 0
        install(101,stages[101])
        start()
        wait(lambda:(trace/"disconnected").exists())
        prefix = int((cursor_dir/"101.offset").read_text())
        assert prefix == 11
        stop()
        (trace/"lose-reply").touch()
        resumed.set()
        start()
        wait(lambda:(trace/"reply-lost").exists())
        lost_prefix = int((cursor_dir/"101.offset").read_text())
        assert lost_prefix == 12
        stop()
        finish_replay.set()
        start()
        wait(lambda:any(p.get("offset")==17 and p["bot"]=="101" for p in polls))
        stop()
        first_wire=wire()[prior_frames:]
        calls=[e["frame"] for e in first_wire if e["direction"]=="from_plugin" and e["frame"].get("method")=="gateway.inbound"]
        responses={e["frame"]["id"]:e["frame"]["result"] for e in first_wire
                   if e["direction"]=="from_host" and "result" in e["frame"] and e["frame"]["id"]!=1}
        assert [c["id"] for c in calls]==[10,11,11,12,12,13,14,15,16]
        delivered = [e["frame"]["result"]["event"] for e in first_wire
                     if e["direction"]=="from_host" and e["frame"].get("id")==12]
        assert len(delivered)==2 and delivered[0]==delivered[1]
        assert responses[12]["event"]==responses[15]["event"] and responses[11]["event"]!=responses[12]["event"]
        assert calls[1]["params"]["topic"]=="7" and calls[3]["params"]["topic"] is None
        assert calls[0]["params"]["segments"][1]["native"]=="101"
        assert [s["type"] for s in calls[1]["params"]["segments"]]==["text","media","reply"]
        assert calls[0]["params"]["occurred"]==1000 and calls[5]["params"]["occurred"]==2000
        assert calls[5]["params"]["kind"]=="edit" and calls[5]["params"]["native_version"]=="13"
        assert calls[6]["params"]["kind"]=="data" and responses[14]["accepted"] is False
        assert calls[-1]["params"]["segments"][0]["reference"]=="sticker"
        models_before_second_bot = len(models)
        install(202,stages[202])
        start()
        wait(lambda:any(p.get("offset")==11 and p["bot"]=="202" for p in polls))
        if published:
            wait(lambda: len(models) > models_before_second_bot)
        stop()
        assert int((cursor_dir/"101.offset").read_text())==17
        assert next(p for p in polls if p["bot"]=="202").get("offset") is None
        second_wire=wire()[prior_frames + len(first_wire):]
        second_event=next(e["frame"]["result"]["event"] for e in second_wire if
                          e["direction"]=="from_host" and e["frame"].get("id")==10)
        assert responses[10]["event"]!=second_event
        return "telegram-offset.json", {"status":"PASS", **qualification,
            "plugin": hashlib.sha256(plugin.read_bytes()).hexdigest(),
            "committed_prefix_after_disconnect":prefix,"prefix_after_lost_reply":lost_prefix,
            "lost_and_recovered_event":delivered,"polls":polls,"transcript":wire(),
            "first_bot_receipts":responses,"second_bot_event":second_event}
    finally:
        stop()
        if published:
            (output / "model.json").write_text(json.dumps(models, ensure_ascii=False), encoding="utf-8")
        resumed.set()
        finish_replay.set()
        server.shutdown()
        server.server_close()
        if (trace/"plugin.err").exists():
            (output/"plugin.txt").write_bytes((trace/"plugin.err").read_bytes())
        if (trace/"wire.jsonl").exists():
            (output/"wire.jsonl").write_bytes((trace/"wire.jsonl").read_bytes())


def run(root, output):
    required = ["YUKI_STABLE_BASE_ZIP", "YUKI_QUALIFIED_TELEGRAM_ZIP"]
    if sys.platform != "win32" or not all(os.environ.get(k) for k in required):
        return "telegram-offset.json", {"status": "BLOCKED", "reason": "Requires Windows and the qualified inputs",
                                        "inputs": required}
    work = output / "work"
    work.mkdir()
    archive, package = [Path(os.environ[k]).resolve() for k in required]
    host, pin, schema = runpy.run_path(str(root / "tests/peers/joint_base.py"))["published_host"](root, archive, work)
    proof = json.loads((root / "artifacts/EXT-043/01/extension-release-lock.json").read_bytes())
    qualified = proof["cases"]["confirmed"]["observed"]["packages"]["telegram"]
    members = {**qualified["artifacts"], "package-manifest.json": qualified["manifest_sha256"]}
    package_sha = "9d62709fbf0a28b6f774e4961c7b736ac84cf0e9dc934e094f03788e7e8271e0"
    runpy.run_path(str(root / "tests/cases/EXT-043.py"))["unpack"](
        package, {"sha256": package_sha, "members": members}, work)
    return exercise(root, output, host, work / "yuki-telegram.exe", {
        "scope": "published-base-loopback-telegram", "card_status": "VERIFIED_ON_PUBLISHED_BASE",
        "source_commit": pin["source_commit"], "host": pin["platforms"]["windows-x86_64"], "published": True,
        "host_sdk": pin["rust_crate_sha256"], "sdk": proof["cases"]["confirmed"]["observed"]["sdk_by_package"]["telegram"],
        "schema": schema, "extension_version": qualified["version"], "extension_published": False,
        "package_sha256": package_sha, "package_manifest_sha256": qualified["manifest_sha256"],
    })
