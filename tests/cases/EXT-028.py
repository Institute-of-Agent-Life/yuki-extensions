"""Dispatch the real web-fetch tool through the native host and a loopback CONNECT proxy."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from host_preview import materialize
from package import build


def prepare(root, output):
    work=output/"work"
    work.mkdir()
    host, pin, platform=materialize(root,work)
    packages=output/"packages"
    fixtures=work/"http-fixtures"
    fixtures.mkdir()
    distribution=build(root,"web-fetch",packages,test_evidence=fixtures)
    binary=packages/("yuki-web-fetch.exe" if os.name=="nt" else "yuki-web-fetch")
    (output/"build.txt").write_text("\n".join(cmd["stdout"]+cmd["stderr"] for cmd in distribution["commands"]),encoding="utf-8")
    data=work/"host-data"
    trace=work/"wire.jsonl"
    pages=[]
    model_requests=[]
    finished=threading.Event()
    source="http://93.184.216.34:8100/document"
    html=b"<html><style>hidden</style><p>Original &amp; public</p></html>"
    big_text="記錄 one two three 雪 "*250
    large_url=source.replace("/document","/large")

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
            if self.path=="/document":
                self.body(200,html,"text/html")
            elif self.path=="/large":
                self.body(200,big_text.encode(),"text/plain")
            else:
                self.send_error(404)

    class Model(HTTP):
        def do_POST(self):
            received=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            model_requests.append(received)
            n=len(model_requests)
            calls=[{"type":"function","id":f"fixture-tool-{n}","function":{
                "name":"web_fetch","arguments":json.dumps({"url":source if n==1 else large_url})}}] if n in (1,3) else []
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

    try:
        cli("init");start()
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
        wires=[json.loads(l) for l in trace.read_text(encoding="utf-8").splitlines()]
        calls=[x["frame"] for x in wires if x["frame"].get("method")=="tool.call"]
        checks=[x["frame"] for x in wires if x["frame"].get("method")=="tool.status"]
        assert len(calls)==2 and len(checks)==4
        for call in calls:
            assert sum(c["params"]["handle"]==call["params"]["handle"] for c in checks)==2
        fixture_results={p.stem:json.loads(p.read_bytes()) for p in fixtures.glob("*.json")}
        assert set(fixture_results)=={"R07-port","R07-host","R07-denied-and-304","failed-proxy"}
        owner=json.loads((root/"plugins/web-fetch/owner-disposition.json").read_bytes())
        (output/"owner-disposition.json").write_bytes((json.dumps(owner,indent=2)+"\n").encode())
        return "fetch-source.json",{"status":"PASS","card_status":"VERIFIED_ON_UNPUBLISHED_CANDIDATE",
            "source_commit":pin["source_commit"],"host":platform,"sdk":pin["rust_crate_sha256"],
            "plugin":distribution["artifacts"][binary.name],"published":False,"ingress_receipt":original,
            "page":page,"connections":pages,
            "network_fixtures":fixture_results,"large_result":{"receipt":large_follow,"pages":parts,"original_pages":original_parts},"tool_result_received_by_main":follow,"transcript":wires}
    finally:
        stop()
        for server in (proxy,model):
            server.shutdown();server.server_close()
        if trace.exists():(output/"wire.jsonl").write_bytes(trace.read_bytes())
        (output/"native.json").write_bytes((json.dumps({"requests":pages,"model_requests":model_requests},indent=2)+"\n").encode())


def run(root, output):
    return "fetch-source.json",{"status":"BLOCKED","card_status":"AWAITING_CORE_032_HANDOFF",
        "reason":"The pinned development host has no merged producer handoff in this lock."}
