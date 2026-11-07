"""Exercise the packaged gateway with stdio and two loopback HTTP boundaries.

The stdio peer supplies calls as a fixture; it does not grant real Host authority.
"""
import base64
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = bytes(range(251)) * 117
DIGEST = hashlib.sha256(DATA).hexdigest()
PAGE = 24576


def exercise(binary, work):
    work.mkdir()
    entered, release = threading.Event(), threading.Event()
    http, wire, checks = [], [], []
    cursor = work / '101.offset'

    class Native(BaseHTTPRequestHandler):
        def answer(self, payload, status=200, location=None):
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            owner, method = self.path.strip("/").split("/")
            assert owner == "bot101:fixture"
            http.append({"method": method, "bot": "101", "body": body})
            if method == "getMe":
                result = {"id": 101, "username": "OriginBot", "is_bot": True}
            elif method == "getUpdates":
                if body.get("offset") is None:
                    result = [{"update_id": 44, "message": {"message_id": 9, "from": {"id": 8},
                        "chat": {"id": -15, "type": "supergroup"}, "date": 1, "message_thread_id": 7,
                        "document": {"file_id": "origin-file"}}}]
                else:
                    entered.set()
                    release.wait(20)
                    result = []
            elif method == "getFile":
                fid = body["file_id"]
                paths = {"unsafe": "../private", "redirect": "m/redirect", "declared-large": "m/no",
                         "short": "m/short", "too-large": "m/large", "origin-file": "docs/雪 #.raw"}
                result = {"file_path": paths[fid]}
                if fid != "too-large":
                    result["file_size"] = {"declared-large": 16777217}.get(fid, len(DATA))
            elif method == "sendChatAction":
                assert body == {"chat_id":"-15","message_thread_id":7,"action":"typing"}
                result = True
            else:
                self.send_error(404)
                return
            self.answer(json.dumps({"ok": True, "result": result}).encode())

        def do_GET(self):
            prefix = "/file/bot101:fixture/"
            name = self.path.removeprefix(prefix)
            http.append({"method": "GET", "bot": "101" if self.path.startswith(prefix) else None, "path":name})
            if name == "m/redirect":
                self.answer(b"x", 302, "/unexpected-redirect")
            elif name == "m/short":
                self.answer(DATA[:13])
            elif name == "m/large":
                self.answer(b"x" * 16777217)
            elif name == "docs/%E9%9B%AA%20%23.raw":
                self.answer(DATA)
            else:
                self.answer(b"", 404)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    ns = "tg.bot101"
    grants = ["gateway.inbound", "gateway.media", "gateway.send", "gateway.activity", "media.open", "forget.owner"]
    binding = {"namespace": ns, "grants": grants, "manifest_revision": "e"*64, "declarations": []}
    env = dict(os.environ, YUKI_PLUGIN_BINDING=json.dumps(binding), YUKI_TELEGRAM_BOT_ID="101",
        YUKI_TELEGRAM_TOKEN="101:fixture", YUKI_TELEGRAM_API=f"http://127.0.0.1:{server.server_port}",
        YUKI_TELEGRAM_STATE=str(work))
    proc = subprocess.Popen([binary], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    lines = queue.Queue()

    def pump():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()

    def read():
        line = lines.get(timeout=6)
        if line is None:
            raise RuntimeError("gateway stopped: " + proc.stderr.read(500).decode(errors="replace"))
        msg = json.loads(line)
        wire.append({"from": "gateway", "frame": msg})
        return msg

    def send(msg):
        wire.append({"from": "fixture", "frame": msg})
        proc.stdin.write(json.dumps(msg).encode()+b"\n")
        proc.stdin.flush()

    seq = 100
    key = {"transfer":"test-stream","namespace":ns,"platform":"telegram","bot_stage":"tg-stage-fixture",
        "media_identity":{"application":"101"},"source_event":10,"attachment_index":0,"segment_index":0,
        "kind":"file","reference":"origin-file","locator":{"source":"-15:9","native_id":"-15:9",
        "native_version":None,"space":"-15","topic":"7","sender":"8"}}

    def call(changes=None, offset=0, ok=False):
        nonlocal seq
        seq += 1
        args = {**key, "offset":offset, "length":PAGE, **(changes or {})}
        send({"jsonrpc":"2.0","id":seq,"method":"gateway.media","params":args})
        reply = read()
        assert reply["id"] == seq
        if ok:
            assert "result" in reply
            page = reply["result"]
            assert page["transfer"] == args["transfer"] and page["offset"] == offset
            assert page["size"] == len(DATA) and page["sha256"] == DIGEST
            assert base64.b64decode(page["data"],validate=True) == DATA[offset:offset+args["length"]]
        else:
            assert "error" in reply and "result" not in reply

    def native():
        return [(r["method"],r.get("path", r.get("body",{}).get("file_id"))) for r in http
                if r["method"] in ("getFile","GET")]

    def actions():
        return [r for r in http if r["method"] == "sendChatAction"]

    def activity(enabled=True, bot="101"):
        send({"jsonrpc":"2.0", "method":"gateway.activity", "params":{
            "lease_id":"original-turn", "enabled":enabled,"ttl_ms":5000,
            "route":{"entry":"original-entry","bot":bot,"chat":"-15","topic":"7"}}})

    def await_action(count):
        deadline = time.monotonic() + 4
        while len(actions()) < count:
            assert time.monotonic() < deadline, "native typing did not arrive"
            time.sleep(.025)

    try:
        init = read()
        assert init["method"] == "initialize"
        send({"jsonrpc":"2.0","id":init["id"],"result":{"schema_revision":1,"version":{"major":1,"minor":0},
            "namespace":ns,"grants":grants,"manifest_revision":binding["manifest_revision"],
            "features":["initialize"],"extension_points":[],"host_schema_revision":2,
            "method_revisions":[{"name":m,"revision":1} for m in ["initialize",*grants,
                "gateway.plan_send", "gateway.dispatch_part", "forget.request"]]}})
        event = read()
        assert event["method"] == "gateway.inbound" and event["params"]["media_identity"] == {"application":"101"}
        assert event["params"]["segments"] == [{"type":"media","reference":"origin-file","kind":"file"}]
        assert not cursor.exists() and native() == []
        for patch in [{"namespace":"tg.bot202"},{"media_identity":{"application":"202"}},
                      {"media_identity":{"application":"101","tenant":"other"}},{"platform":"feishu"},
                      {"length":24577},{"length":0},{"transfer":""}]:
            call(patch)
        call(offset=1)
        assert not native()
        checks.append("foreign installation/tenant and invalid first page: zero platform requests")
        outbound_before = len(native())
        selected = {"artifact_id":"selected", "version":DIGEST}
        dispatch = {"handle":"original-bound-handle", "arguments":{
            "purpose":"deliver", "route":{"bot":"101","chat":"-15","topic":"7"},
            "part_ordinal":0, "media":selected,
            "part":{"media":selected,"kind":"file","name":"selected.bin"}}}
        send({"jsonrpc":"2.0","id":801,"method":"gateway.dispatch_part","params":dispatch})
        page_request = read()
        assert page_request["method"] == "media.open"
        send({"jsonrpc":"2.0","id":802,"method":"forget.request",
              "params":{"key":"erase-outbound","watermark":11}})
        assert read() == {"jsonrpc":"2.0","id":801,"result":{"state":"failed"}}
        assert read()["result"]["key"] == "erase-outbound"
        dispatch["handle"] = "new-bound-handle"
        send({"jsonrpc":"2.0","id":804,"method":"gateway.dispatch_part","params":dispatch})
        current_page = read()
        assert current_page["method"] == "media.open" and current_page["id"] != page_request["id"]
        send({"jsonrpc":"2.0","id":page_request["id"],"result":{
            "offset":0,"total":len(DATA),"version":DIGEST,"mime":"application/octet-stream",
            "bytes":base64.b64encode(DATA[:16384]).decode(),"done":False}})
        send({"jsonrpc":"2.0","id":current_page["id"],"result":{
            "offset":0,"total":len(DATA),"version":DIGEST,"mime":"application/octet-stream",
            "bytes":base64.b64encode(DATA[:16384]).decode(),"done":False}})
        continuation = read()
        assert continuation["method"] == "media.open" and continuation["params"]["offset"] == 16384
        send({"jsonrpc":"2.0","id":803,"method":"forget.request",
              "params":{"key":"drained","watermark":11}})
        assert read() == {"jsonrpc":"2.0","id":804,"result":{"state":"failed"}}
        assert read()["id"] == 803 and len(native()) == outbound_before
        checks.append("concurrent media replies before inbound ACK preserve the current handle after a late forgotten page")
        call(ok=True)
        assert not cursor.exists()
        fetched = [("getFile","origin-file"),("GET","docs/%E9%9B%AA%20%23.raw")]
        assert native() == fetched
        for patch in [{"source_event":11},{"segment_index":1},{"transfer":"other"},{"bot_stage":"other"}]:
            call(patch,offset=PAGE)
        call(offset=PAGE-1)
        assert native() == fetched
        send({"jsonrpc":"2.0","id":event["id"],"result":{"event":10,"accepted":True}})
        assert entered.wait(6) and cursor.read_text().strip() == "45"
        call(offset=PAGE,ok=True)
        call(offset=PAGE)
        assert native() == fetched and not release.is_set()
        checks.append("same digest and exact pages while waiting for admission and during getUpdates")
        activity(bot="202")
        time.sleep(.15)
        assert actions() == []
        activity()
        await_action(1)
        # With no Host renewal the last lease expires after five seconds.
        time.sleep(6.2)
        assert len(actions()) == 2, actions()
        activity(False)
        time.sleep(.1)
        assert len(actions()) == 2
        activity()
        await_action(3)
        activity(False)
        time.sleep(3.2)
        assert len(actions()) == 3
        checks.append("original Bot/topic typing expires without renewal and explicit end stops new requests")
        for fid, gets in [("declared-large",0),("unsafe",0),("short",1),("redirect",1),("too-large",1)]:
            before=len(native())
            call({"reference":fid,"transfer":fid})
            delta=native()[before:]
            assert len(delta)==1+gets and delta[0]==("getFile",fid)
            checks.append(fid+": denied; downloads="+str(gets))
        assert not any(r.get("path")=="unexpected-redirect" for r in http)
        call(ok=True)
        before = len(native())
        activity()
        await_action(4)
        send({"jsonrpc":"2.0","id":800,"method":"forget.request",
              "params":{"key":"erase-inbound","watermark":10}})
        assert read()["result"] == {"key":"erase-inbound","watermark":10,
            "proof":"volatile-media-cleared-and-upload-pipe-closed"}
        call(offset=PAGE)
        assert len(native()) == before
        time.sleep(3.2)
        assert len(actions()) == 4
        checks.append("forget ends typing before the original watermark acknowledgement")
        checks.append("forget clears cached inbound bytes before acknowledging the original watermark")

        proc.stdin.close()
        assert proc.wait(timeout=4)==0 and not release.is_set()
        checks.append("stdio EOF during long poll: exited before HTTP fixture released")
        return {"status":"PASS","scope":"packaged Rust stdio peer + loopback Telegram HTTP fixtures",
                "actual_host_consumption":False,"paid_calls":0,"native_http":http,"wire":wire,
                "source_bytes":len(DATA),"source_sha256":DIGEST,"checks":checks}
    finally:
        release.set()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        server.shutdown()
        server.server_close()
