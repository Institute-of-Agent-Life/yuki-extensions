"""Exercise the original Manager package and a missing environment in the native Host."""
import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import time

from host_preview import materialize
from package import build


def prepare(root, output):
    work=output/"work";work.mkdir()
    module=importlib.util.spec_from_file_location("inspect_source",root/"deploy/env/inspect-source.py")
    inspect=importlib.util.module_from_spec(module);module.loader.exec_module(inspect)
    backend=work/"backend"
    pin=inspect.extract(root/"deploy/env/manager-source.zip",root/"plugins/env/backend/source.lock.json",backend)
    # The original Manager owns a fresh, isolated test store.
    probe=subprocess.run([sys.executable,"-I",root/"tests/peers/env_manager_probe.py",backend,work/"isolated-store"],
                         check=False,capture_output=True,text=True,timeout=20)
    if probe.returncode:raise RuntimeError(probe.stderr[-1400:])
    original=json.loads(probe.stdout)
    host,producer,platform=materialize(root,work)
    packages=output/"packages";dist=build(root,"env",packages)
    binary=packages/("yuki-env.exe" if os.name=="nt" else "yuki-env")
    (output/"build.txt").write_text("\n".join(c["stdout"]+c["stderr"] for c in dist["commands"]),encoding="utf-8")
    model_requests=[];finished=threading.Event()
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            model_requests.append(body)
            initial=len(model_requests)==1
            message={"role":"assistant","content":"done"}
            if initial:
                message.update(content=None,tool_calls=[{"type":"function","id":"fixture-status","function":{
                    "name":"environment_status","arguments":"{}"}}])
            response={"id":"fixture","choices":[{"index":0,"finish_reason":"tool_calls" if initial else "stop",
                       "message":message}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}
            data=json.dumps(response).encode()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            if not initial:finished.set()
    model=ThreadingHTTPServer(("127.0.0.1",0),Model)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    data=work/"host";proc=None;wire=work/"wire.jsonl"
    env=dict(os.environ,YUKI_ENV_MANAGER_SOCKET=str(work/"absent.sock"),
             no_proxy="localhost,127.0.0.1",NO_PROXY="localhost,127.0.0.1")
    def cli(*args,check=True):
        r=subprocess.run([host,"--data",data,*args],cwd=work,env=env,capture_output=True,text=True,timeout=20)
        if r.returncode and check:raise RuntimeError(str(args[:3])+": "+r.stderr[:400])
        return json.loads(r.stdout) if not r.returncode and r.stdout.strip() else None
    def wait(f):
        until=time.monotonic()+20
        while time.monotonic()<until:
            if f():return
            time.sleep(.1)
        raise RuntimeError("host readiness timeout")
    def start():
        nonlocal proc
        with (output/"host.txt").open("ab") as log:
            proc=subprocess.Popen([host,"--data",data,"run"],cwd=work,env=env,stdout=log,stderr=log)
        wait(lambda:cli("operator","database-info",check=False))
    def stop():
        if proc and proc.poll() is None:
            cli("operator","shutdown",check=False)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    try:
        cli("init");start()
        person="00000000-0000-4000-8000-000000000020"
        cli("operator","person","create",person)
        account=cli("operator","account","open","telegram","env-test","17","1","--person",person,"--start","1")
        bot=cli("operator","account","open","telegram","env-test","101","1","--start","1")
        cli("operator","entry","private",account["assignment"],bot["assignment"])
        stop()
        with (data/"yuki.toml").open("a",encoding="utf-8") as cfg:
            print('\n[main]\nendpoint="http://127.0.0.1:%d/v1/chat/completions"\nmodel="fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=5\nmax_input_units=200000\nmax_output=128\n'%model.server_port,file=cfg)
            print("[[plugins]]",file=cfg)
            for k,v in {"id":"env","namespace":"official.env","program":sys.executable,
                "args":[str(root/"tests/peers/observe_stdio.py"),str(binary),str(wire)],
                "grants":["tool.call"],"env":["YUKI_ENV_MANAGER_SOCKET"]}.items():
                print(k,"=",json.dumps(v),file=cfg)
            print('[[plugins.tools]]\nname="environment_status"\ndescription="Report readiness."\nparallel_read=false\ncode_direct=true\ncacheable=false\nschema={type="object",properties={},additionalProperties=false}',file=cfg)
        start()
        def online():
            s=cli("operator","host","status",check=False)
            return s and any(p["online"] for p in s["plugins"])
        wait(online)
        envelope={"source":"env-1","native_id":"env-1","account":account["account"],"bot_stage":bot["assignment"],
            "space":None,"topic":None,"occurred":10,"observed":11,"kind":"message",
            "segments":[{"type":"text","text":"environment status"}]}
        receipt=cli("operator","ingress","record",json.dumps(envelope),"--accept")
        if not finished.wait(40):raise RuntimeError("missing continuation for local unavailable tool")
        observed=json.loads(model_requests[1]["messages"][-1]["content"])
        assert observed["result"]["ok"] is False and observed["result"]["error"]=="manager_unavailable",observed
        assert online()
        transcript=[json.loads(s) for s in wire.read_text(encoding="utf-8").splitlines()]
        calls=[v["frame"] for v in transcript if v["frame"].get("method")=="tool.call"]
        checks=[v["frame"] for v in transcript if v["frame"].get("method")=="tool.status"]
        assert len(calls)==1 and len(checks)==2 and all(c["params"]["handle"]==calls[0]["params"]["handle"] for c in checks)
        return "env-preparation.json",{"status":"PASS","card_status":"PARTIAL_BACKEND_AND_UNAVAILABLE_TOOL",
            "source_commit":producer["source_commit"],"host":platform,"sdk":producer["rust_crate_sha256"],
            "plugin":dist["artifacts"][binary.name],"backend_source":pin["archive_sha256"],"source_members":len(pin["source_members"]),
            "original_manager":original,"receipt":receipt,"model_continuation":observed,"host_online_after_missing_manager":True,
            "transcript":transcript,"pending":["run authority and original Work binding in consumer SDK",
            "real Linux gVisor/execd PTY, cancellation, replay and output rotation"]}
    finally:
        stop();model.shutdown();model.server_close()
        if wire.exists():(output/"wire.jsonl").write_bytes(wire.read_bytes())


def run(root, output):
    return "env-terminal.json",{"status":"BLOCKED","card_status":"AWAITING_RUNTIME_AND_SCOPED_RUN_BINDING",
        "reason":"Full terminal acceptance requires the original authorized Work/run binding and an isolated Linux Manager/runsc/execd runtime."}
