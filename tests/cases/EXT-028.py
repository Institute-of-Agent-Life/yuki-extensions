"""Dispatch the real web-fetch tool through the native host and a loopback CONNECT proxy."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time

from host_preview import materialize
from package import build


def exercise(root, output, signed, *, published=False):
    work=output/"work"
    work.mkdir()
    packages = output / "packages"
    fixtures = work / "http-fixtures"
    fixtures.mkdir()
    if published:
        archive = Path(os.environ["YUKI_STABLE_BASE_ZIP"])
        host, pin, _ = runpy.run_path(str(root / "tests/peers/joint_base.py"))["published_host"](root, archive, work)
        platform = pin["platforms"]["windows-x86_64"]
        packages.mkdir()
        runpy.run_path(str(root / "tests/cases/EXT-043.py"))["unpack"](
            Path(os.environ["YUKI_FROZEN_WEB_FETCH_ZIP"]), pin["windows_fallback"]["web-fetch"], packages)
    elif signed:
        from runpy import run_path
        contract = root/"compat/base"
        verifier = run_path(str(contract/"verify_dist.py"))
        pin = json.loads((contract/"source.lock.json").read_bytes())
        platform = pin["platforms"]["-".join(verifier["native_target"]())]
        key = work/"source-signer.pub"
        key.write_bytes((platform["signer"]+"\n").encode("ascii"))
        assert hashlib.sha256(key.read_bytes()).hexdigest()==platform["signer_sha256"]
        release = verifier["verify"](Path(os.environ["YUKI_BASE_HOST_ARCHIVE"]), key,
                                    pin["source_commit"], platform["sha256"], pin["fixtures_sha256"],
                                    destination=work/"signed")
        assert not release["dirty"] and release["host_schema_sha256"]==pin["schema_sha256"]
        host = work/"signed"/"bin"/("yuki-core.exe" if os.name=="nt" else "yuki-core")
        assert hashlib.sha256(host.read_bytes()).hexdigest()==platform["binary_sha256"]
    else:
        host, pin, platform=materialize(root,work)
    distribution = (json.loads((packages / "package-manifest.json").read_bytes()) if published
                    else build(root, "web-fetch", packages, test_evidence=fixtures))
    consumer_pin = json.loads((root / distribution["source"]["sdk_contract"]).read_bytes())
    binary=packages/("yuki-web-fetch.exe" if os.name=="nt" else "yuki-web-fetch")
    (output/"build.txt").write_text("\n".join(cmd["stdout"]+cmd["stderr"] for cmd in distribution["commands"]),encoding="utf-8")
    data=work/"host-data"
    trace=work/"wire.jsonl"
    empty_html=b"<html><style>hidden</style><script>unused()</script></html>"
    pages=[]
    model_requests=[]
    finished=threading.Event()
    source="http://93.184.216.34:8100/document"
    html=b"<html><style>hidden</style><p>Original &amp; public</p></html>"
    big_text="記錄 one two three 雪 "*250
    large_url=source.replace("/document","/large")

    limit = 2 * 1024 * 1024
    oversize = b"abcdefghijk " * (limit // 12 + 1000) if published else b""
    denied_url = source.replace("/document", "/private-redirect")
    oversized_url = source.replace("/document", "/oversized")

    class HTTP(BaseHTTPRequestHandler):
        protocol_version="HTTP/1.1"
        def log_message(self,*args):
            pass
        def body(self,status,data,mime):
            self.send_response(status)
            self.send_header("Content-Type",mime)
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    class Proxy(HTTP):
        def do_CONNECT(self):
            pages.append({"method":"CONNECT","target":self.path})
            if self.path!="93.184.216.34:8100":
                self.send_error(403)
                return
            self.send_response(200,"Connection established")
            self.end_headers()
            self.close_connection=False
        def do_GET(self):
            pages.append({"method":"GET","host":self.headers["Host"],"path":self.path})
            if published and self.path == "/private-redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/tripwire")
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif published and self.path == "/oversized":
                try:
                    self.body(200, oversize, "text/plain")
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                    pass  # The reader can stop as soon as it reaches its byte ceiling.
            elif self.path=="/document":
                self.body(200,html,"text/html")
            elif self.path=="/empty":
                self.body(200,empty_html,"text/html")
            elif self.path=="/large":
                self.body(200,big_text.encode(),"text/plain")
            else:
                self.send_error(404)

    class Model(HTTP):
        def do_POST(self):
            received=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            model_requests.append(received)
            n=len(model_requests)
            targets = {1: source, 3: large_url}
            if published:
                targets = {1: denied_url, 3: oversized_url}
            elif signed:
                targets[5] = source.replace("/document", "/empty")
            calls=[{"type":"function","id":f"fixture-tool-{n}","function":{
                "name":"web_fetch","arguments":json.dumps({"url":targets[n]})}}] if n in targets else []
            reply={"id":"fixture-completion","choices":[{"index":0,"finish_reason":"tool_calls" if calls else "stop",
                "message":{"role":"assistant","content":None if calls else "complete",
                           **({"tool_calls":calls} if calls else {})}}],
                "usage":{"prompt_tokens":2,"completion_tokens":1,"total_tokens":3}}
            self.body(200,json.dumps(reply).encode(),"application/json")
            if not calls:
                finished.set()

    proxy=ThreadingHTTPServer(("127.0.0.1",0),Proxy)
    model=ThreadingHTTPServer(("127.0.0.1",0),Model)
    for server in (proxy,model):
        threading.Thread(target=server.serve_forever,daemon=True).start()
    addr=f"http://127.0.0.1:{proxy.server_port}"
    # Only the plugin receives the configured proxy. Exclude the fixture model from proxying.
    env=dict(os.environ,YUKI_WEB_FETCH_HTTP_PROXY=addr,YUKI_WEB_FETCH_NO_PROXY="",NO_PROXY="127.0.0.1,localhost",no_proxy="127.0.0.1,localhost")

    def cli(*args,check=True):
        result=subprocess.run([host,"--data",data,*args],cwd=work,env=env,capture_output=True,text=True,timeout=20)
        if check and result.returncode:raise RuntimeError(f"{args[:2]}: {result.stderr[:400]}")
        return json.loads(result.stdout) if result.returncode==0 and result.stdout.strip() else None

    proc=None
    def wait_for(action):
        end=time.monotonic()+20
        while time.monotonic()<end:
            if action():return
            time.sleep(.1)
        raise RuntimeError("host readiness timeout")
    def start():
        nonlocal proc
        with (output/"host.txt").open("ab") as log:
            proc=subprocess.Popen([host,"--data",data,"run"],cwd=work,env=env,stdout=log,stderr=log)
        wait_for(lambda:cli("operator","database-info",check=False))
    def stop():
        if proc and proc.poll() is None:
            cli("operator","shutdown",check=False)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()

    def public_result(refused):
        denial = refused["result"]
        assert denial["error"] == "destination_denied" and not denial["ok"]
        assert denial["data"]["source"] == denied_url
        assert denial["data"]["url"] == f"http://127.0.0.1:{proxy.server_port}/tripwire"
        cli("operator", "main", "register", "plugin", "web-reader", entry)
        finished.clear()
        run = cli("operator", "main", "trigger", "web-reader", "oversize",
                  json.dumps({"text":"Read the oversized test page"}))["execution"]
        if not finished.wait(40):
            raise RuntimeError("missing partial-result continuation")
        assert len(model_requests) == 4
        result = json.loads(model_requests[-1]["messages"][-1]["content"])["result"]
        artifact = result["artifact"]

        def read(field):
            return cli("operator", "tools", "read-artifact", run, "web-reader", json.dumps({
                "handle":artifact["handle"], "version":artifact["version"],
                "path":"/result/data/" + field, "offset":0, "limit":128}))

        frames = [json.loads(row) for row in trace.read_bytes().splitlines()]
        exchange = runpy.run_path(str(root / "tests/peers/joint_base.py"))["exchange"]
        dispatched = list(exchange(frames, "tool.call", "from_host"))
        assert [call["params"]["arguments"]["url"] for call, _ in dispatched] == [denied_url, oversized_url]
        checks = list(exchange(frames, "tool.status", "from_plugin"))
        for call, _ in dispatched:
            handle = call["params"]["handle"]
            receipts = [reply["result"] for req, reply in checks if req["params"]["handle"] == handle]
            assert len(receipts) == 2 and all(row["state"] == "dispatched" and row["handle"] == handle for row in receipts)
        raw = dispatched[1][1]["result"]["data"]
        assert raw["source"] == raw["url"] == oversized_url and raw["state"] == "partial"
        assert raw["observed_bytes"] == limit < len(oversize)
        assert not raw["transport_complete"] and not raw["original_complete"] and raw["text_truncated"]
        assert raw["observed_sha256"] == hashlib.sha256(oversize[:limit]).hexdigest()
        retained = bytes.fromhex(raw["original_hex"])
        assert 0 < len(retained) < limit and retained == oversize[:len(retained)]
        assert raw["text"] and oversize.startswith(raw["text"].encode("utf-8"))
        projections = {field: read(field) for field in ["original_hex", "text", "source", "state", "observed_sha256"]}
        for field, page in projections.items():
            assert page["value"] == raw[field][:128]
        assert projections["original_hex"]["next_offset"] == projections["text"]["next_offset"] == 128
        assert pages == [row for url in (denied_url, oversized_url) for row in (
            {"method":"CONNECT", "target":"93.184.216.34:8100"},
            {"method":"GET", "host":"93.184.216.34:8100", "path":"/" + url.rsplit("/", 1)[1]})]
        owner = (root / "plugins/web-fetch/owner-disposition.json").read_bytes()
        (output / "owner-disposition.json").write_bytes(owner)
        return "fetch-source.json", {"status":"PASS", "card_status":"VERIFIED_ON_PUBLISHED_BASE",
            "host":platform, "source_commit":pin["source_commit"], "host_sdk":pin["rust_crate_sha256"],
            "sdk":consumer_pin["rust_crate_sha256"], "package":pin["windows_fallback"]["web-fetch"],
            "plugin":hashlib.sha256(binary.read_bytes()).hexdigest(), "extension_published":False,
            "ingress":original, "redirect_refusal":denial, "requests":pages, "private_destination_requests":0,
            "served_bytes":len(oversize), "observed_bytes":limit, "retained_bytes":len(retained),
            "observed_sha256":raw["observed_sha256"], "run":run, "artifact":artifact, "projections":projections,
            "signed_candidate_evidence":"artifacts/EXT-028/01"}

    try:
        cli("init")
        if signed:
            from personal_preview import free_address
            cfg=data/"yuki.toml"
            settings=cfg.read_text(encoding="utf-8").replace('"127.0.0.1:0"',json.dumps(free_address()))
            cfg.write_text(settings.replace('mode = "hybrid"','mode = "lexical-only"'),encoding="utf-8")
        start()
        person="00000000-0000-4000-8000-000000000028"
        cli("operator","person","create",person)
        human=cli("operator","account","open","telegram","web-test","17","1","--person",person,"--start","1")
        bot=cli("operator","account","open","telegram","web-test","101","1","--start","1")
        entry=cli("operator","entry","private",human["assignment"],bot["assignment"])["entry"]
        stop()
        with (data/"yuki.toml").open("a",encoding="utf-8") as cfg:
            print('\n[main]\nendpoint="http://127.0.0.1:%d/v1/chat/completions"\nmodel="fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=5\nmax_input_units=200000\nmax_output=128\nresult_page_budget=2000\nresult_storage_bytes=65536\n'%model.server_port,file=cfg)
            print("[[plugins]]",file=cfg)
            values={"id":"web-fetch","namespace":"official.web-fetch","program":sys.executable,
                "args":[str(root/"tests/peers/observe_stdio.py"),str(binary),str(trace)],
                "grants":["tool.call"],"env":["YUKI_WEB_FETCH_HTTP_PROXY","YUKI_WEB_FETCH_NO_PROXY"]}
            for k,v in values.items():print(k,"=",json.dumps(v),file=cfg)
            print('[[plugins.tools]]\nname="web_fetch"\ndescription="Read a public page."\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={url={type="string"}},required=["url"],additionalProperties=false}',file=cfg)
        start()
        def online():
            status=cli("operator","host","status",check=False)
            return status and any(p["online"] for p in status["plugins"])
        wait_for(online)
        envelope={"source":"web-1","native_id":"web-1","account":human["account"],"bot_stage":bot["assignment"],
            "space":None,"topic":None,"occurred":10,"observed":11,"kind":"message",
            "segments":[{"type":"text","text":"read the fixture page"}]}
        original=cli("operator","ingress","record",json.dumps(envelope),"--accept")
        if not finished.wait(40):
            raise RuntimeError("missing model continuation after tool dispatch")
        follow=json.loads(model_requests[1]["messages"][-1]["content"])
        if published:
            return public_result(follow)
        page=follow["result"]["data"]
        assert page["state"]=="read" and page["text"]=="Original & public"
        assert page["source"]==source and bytes.fromhex(page["original_hex"])==html
        assert page["observed_sha256"]==hashlib.sha256(html).hexdigest()
        assert pages==[{"method":"CONNECT","target":"93.184.216.34:8100"},
                       {"method":"GET","host":"93.184.216.34:8100","path":"/document"}]
        cli("operator","main","register","plugin","web-reader",entry)
        finished.clear()
        run=cli("operator","main","trigger","web-reader","large-page",json.dumps({"text":"large fixture"}))["execution"]
        if not finished.wait(40):raise RuntimeError("missing continuation after large tool result")
        large_follow=json.loads(model_requests[3]["messages"][-1]["content"])
        artifact=large_follow["result"]["artifact"]
        def read_pages(path):
            cursor=0
            parts=[]
            while True:
                section=cli("operator","tools","read-artifact",run,"web-reader",json.dumps({
                    "handle":artifact["handle"],"version":artifact["version"],"path":path,
                    "offset":cursor,"limit":256}))
                parts.append(section)
                if section["next_offset"] is None:break
                assert section["next_offset"]>cursor
                cursor=section["next_offset"]
            return parts
        parts=read_pages("/result/data/text")
        original_parts=read_pages("/result/data/original_hex")
        assert bytes.fromhex("".join(p["value"] for p in original_parts))==big_text.encode()
        assert "".join(p["value"] for p in parts)==" ".join(big_text.split()) and len(parts)>1
        empty_page = None
        if signed:
            finished.clear()
            cli("operator","main","trigger","web-reader","empty-page",json.dumps({"text":"read empty fixture"}))
            if not finished.wait(40):
                raise RuntimeError("missing tool result for the empty HTML document")
            final_messages = model_requests[-1]["messages"]
            empty_page = json.loads(final_messages[-1]["content"])["result"]["data"]
            assert empty_page["state"] == "empty_page" and "text" not in empty_page
            assert bytes.fromhex(empty_page["original_hex"]) == empty_html
            assert empty_page["observed_sha256"] == hashlib.sha256(empty_html).hexdigest()
            assert empty_page["source"] == source.replace("/document","/empty")
            assert [q["path"] for q in pages if q["method"]=="GET"] == ["/document","/large","/empty"]
            assert len(model_requests) == 6
        wires=[json.loads(l) for l in trace.read_text(encoding="utf-8").splitlines()]
        calls=[x["frame"] for x in wires if x["frame"].get("method")=="tool.call"]
        checks=[x["frame"] for x in wires if x["frame"].get("method")=="tool.status"]
        expected_calls = 3 if signed else 2
        assert len(calls)==expected_calls and len(checks)==2*expected_calls
        for call in calls:
            assert sum(c["params"]["handle"]==call["params"]["handle"] for c in checks)==2
        fixture_results={p.stem:json.loads(p.read_bytes()) for p in fixtures.glob("*.json")}
        assert set(fixture_results)=={"R07-port","R07-host","R07-denied-and-304","failed-proxy"}
        owner=json.loads((root/"plugins/web-fetch/owner-disposition.json").read_bytes())
        (output/"owner-disposition.json").write_bytes((json.dumps(owner,indent=2)+"\n").encode())
        return "fetch-source.json",{"status":"PASS",
            "card_status":"VERIFIED_ON_SIGNED_DEVELOPMENT_CANDIDATE" if signed else "VERIFIED_ON_UNPUBLISHED_CANDIDATE",
            "signed_distribution":signed,
            "source_commit":pin["source_commit"],"host":platform,"host_sdk":pin["rust_crate_sha256"],"sdk":consumer_pin["rust_crate_sha256"],
            "plugin":distribution["artifacts"][binary.name],"published":False,"ingress_receipt":original,
            "page":page,"connections":pages,
            "empty_page":empty_page,"network_fixtures":fixture_results,"large_result":{"receipt":large_follow,"pages":parts,"original_pages":original_parts},"tool_result_received_by_main":follow,"transcript":wires}
    finally:
        stop()
        for server in (proxy,model):
            server.shutdown();server.server_close()
        if trace.exists():(output/"wire.jsonl").write_bytes(trace.read_bytes())
        (output/"native.json").write_bytes((json.dumps({"requests":pages,"model_requests":model_requests},indent=2)+"\n").encode())




def prepare(root, output):
    return exercise(root, output, signed=False)


def run(root, output):
    if os.environ.get("YUKI_STABLE_BASE_ZIP"):
        if sys.platform != "win32" or not os.environ.get("YUKI_FROZEN_WEB_FETCH_ZIP"):
            return "fetch-source.json", {"status":"BLOCKED", "reason":"The frozen public-base path requires Windows and YUKI_FROZEN_WEB_FETCH_ZIP."}
        return exercise(root, output, signed=True, published=True)
    if not os.environ.get("YUKI_BASE_HOST_ARCHIVE"):
        return "fetch-source.json", {
            "status": "BLOCKED",
            "reason": "Supply the signed CORE-039 archive pinned in compat/base via YUKI_BASE_HOST_ARCHIVE.",
        }
    return exercise(root, output, signed=True)
