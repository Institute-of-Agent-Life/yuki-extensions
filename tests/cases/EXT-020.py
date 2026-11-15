"""Run the packaged environment status tool through the released Host."""
import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
import tomllib
from tempfile import TemporaryDirectory

from package import build


def prepare(root, output):
    with TemporaryDirectory(prefix="env20-") as folder:
        return exercise(root, output, Path(folder).resolve())


def exercise(root, output, work):
    module=importlib.util.spec_from_file_location("inspect_source",root/"deploy/env/inspect-source.py")
    inspect=importlib.util.module_from_spec(module);module.loader.exec_module(inspect)
    backend=work/"backend"
    pin=inspect.extract(root/"deploy/env/manager-source.zip",root/"plugins/env/backend/source.lock.json",backend)
    # The original Manager owns a fresh, isolated test store.
    probe=subprocess.run([sys.executable,"-I",root/"tests/peers/env_manager_probe.py",backend,work/"isolated-store"],
                         check=False,capture_output=True,text=True,timeout=20)
    if probe.returncode:raise RuntimeError(probe.stderr[-1400:])
    original=json.loads(probe.stdout)
    archive = Path(os.environ["YUKI_STABLE_BASE_ZIP"])
    load_host = runpy.run_path(str(root/"tests/peers/joint_base.py"))["published_host"]
    host, producer, _ = load_host(root, archive, work)
    platform, = (value for value in producer["platforms"].values() if value["archive"] == archive.name)
    packages=output/"packages";dist=build(root,"env",packages)
    binary=packages/("yuki-env.exe" if os.name=="nt" else "yuki-env")
    declaration = tomllib.loads((packages/"plugin.toml").read_text(encoding="utf-8"))
    (output/"build.txt").write_text("\n".join(c["stdout"]+c["stderr"] for c in dist["commands"]),encoding="utf-8")
    model_requests=[];finished=threading.Event()
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            model_requests.append(body)
            initial=len(model_requests)%2==1
            message={"role":"assistant","content":"done"}
            if initial:
                message.update(content=None,tool_calls=[{"type":"function","id":"fixture-status-"+str(len(model_requests)),"function":{
                    "name":"environment_status","arguments":"{}"}}])
            response={"id":"fixture","choices":[{"index":0,"finish_reason":"tool_calls" if initial else "stop",
                       "message":message}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}
            data=json.dumps(response).encode()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            if not initial:finished.set()
    model=ThreadingHTTPServer(("127.0.0.1",0),Model)
    threading.Thread(target=model.serve_forever,daemon=True).start()
    data=work/"host";proc=None;manager=None;wire=work/"wire.jsonl"
    socket = work/"manager.sock"
    env=dict(os.environ,YUKI_ENV_MANAGER_SOCKET=str(socket),
             no_proxy="localhost,127.0.0.1",NO_PROXY="localhost,127.0.0.1")
    def cli(*args,check=True):
        r=subprocess.run([host,"--plugin-base-1","--data",data,*args],cwd=work,env=env,capture_output=True,text=True,timeout=20)
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
            proc=subprocess.Popen([host,"--plugin-base-1","--data",data,"run"],cwd=work,env=env,stdout=log,stderr=log)
        wait(lambda:proc.poll() is not None or cli("operator","database-info",check=False))
        if proc.poll() is not None:
            raise RuntimeError("published Host exited during initialization")
    def stop():
        if proc and proc.poll() is None:
            cli("operator","shutdown",check=False)
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
    try:
        cli("init")
        cfg = data/"yuki.toml"
        settings = cfg.read_text(encoding="utf-8")
        assert settings.count('mode = "hybrid"') == 1
        cfg.write_text(settings.replace('mode = "hybrid"', 'mode = "lexical-only"'), encoding="utf-8")
        start()
        person="00000000-0000-4000-8000-000000000020"
        cli("operator","person","create",person)
        account=cli("operator","account","open","telegram","env-test","17","1","--person",person,"--start","1")
        bot=cli("operator","account","open","telegram","env-test","101","1","--start","1")
        cli("operator","entry","private",account["assignment"],bot["assignment"])
        stop()
        with (data/"yuki.toml").open("a",encoding="utf-8") as cfg:
            print('\n[main]\nendpoint="http://127.0.0.1:%d/v1/chat/completions"\nmodel="fixture"\nname="Yuki"\nmerge_ms=0\nroot_slots=5\nmax_input_units=200000\nmax_output=128\n'%model.server_port,file=cfg)
            print("[[plugins]]",file=cfg)
            for k,v in {"id":declaration["id"],"namespace":"official.env","program":sys.executable,
                "args":[str(root/"tests/peers/observe_stdio.py"),str(binary),str(wire)],
                "grants":declaration["grants"],"env":declaration["env"]}.items():
                print(k,"=",json.dumps(v,ensure_ascii=False),file=cfg)
            tool, = declaration["tools"]
            print("[[plugins.tools]]",file=cfg)
            for key in ("name","description","parallel_read","code_direct","cacheable"):
                print(key,"=",json.dumps(tool[key],ensure_ascii=False),file=cfg)
            assert tool["schema"]=={"type":"object","properties":{},"additionalProperties":False}
            print('schema={type="object",properties={},additionalProperties=false}',file=cfg)
        start()
        def online():
            s=cli("operator","host","status",check=False)
            return s and any(p["online"] for p in s["plugins"])
        wait(online)
        def status(sequence):
            finished.clear()
            source = f"env-{sequence}"
            envelope={"source":source,"native_id":source,"account":account["account"],"bot_stage":bot["assignment"],
                "space":None,"topic":None,"occurred":10+sequence,"observed":10+sequence,"kind":"message",
                "segments":[{"type":"text","text":"environment status"}]}
            receipt=cli("operator","ingress","record",json.dumps(envelope),"--accept")
            if not finished.wait(40):raise RuntimeError("missing environment status continuation")
            return {"event":receipt["event"], "result":json.loads(model_requests[-1]["messages"][-1]["content"])["result"]}

        cases = {}
        if sys.platform.startswith("linux"):
            with (output/"manager.txt").open("wb") as log:
                manager = subprocess.Popen([sys.executable,"-I",root/"tests/peers/env_manager_probe.py",backend,work/"manager-state",socket],
                                           stdout=log, stderr=log)
                wait(lambda:socket.is_socket() or manager.poll() is not None)
                if manager.poll() is not None:
                    raise RuntimeError("original Manager exited before accepting connections")
                cases["original_socket"] = status(1)
                result = cases["original_socket"]["result"]
                assert result["ok"] and result["data"]["ready"] is False, result
                assert set(result["data"])=={"ready","home","workspace","storage"}, result
                assert result["data"]["home"]=="/home/yuki" and result["data"]["workspace"]=="/workspace", result
                assert result["data"]["storage"]["capacity_bytes"]>0, result
                assert (work/"manager-state/observed").is_file()
                manager.terminate()
                manager.wait(timeout=10)
        cases["manager_unavailable"] = status(2)
        result = cases["manager_unavailable"]["result"]
        assert result["ok"] is False and result["error"]=="manager_unavailable",result
        assert online()
        transcript=[json.loads(s) for s in wire.read_text(encoding="utf-8").splitlines()]
        calls=[v["frame"] for v in transcript if v["frame"].get("method")=="tool.call"]
        checks=[v["frame"] for v in transcript if v["frame"].get("method")=="tool.status"]
        assert len(calls)==len(cases) and len(checks)==2*len(cases)
        for frame in calls:
            handle=frame["params"]["handle"]
            assert sum(check["params"]["handle"]==handle for check in checks)==2
        return "env-preparation.json",{"status":"PASS","card_status":"PARTIAL_ORIGINAL_MANAGER_STATUS",
            "source_commit":producer["source_commit"],"host":platform,"sdk":producer["sdk"],
            "plugin":dist["artifacts"][binary.name],"backend_source":pin["archive_sha256"],"source_members":len(pin["source_members"]),
            "original_manager":original,"cases":cases,"host_online_after_missing_manager":True,
            "transcript":transcript,"paid_calls":0,"pending":["original run binding in the installed consumer",
            "real Linux gVisor/execd PTY, cancellation, replay and output rotation"]}
    finally:
        if manager and manager.poll() is None:
            manager.kill()
            manager.wait(timeout=10)
        stop();model.shutdown();model.server_close()
        if wire.exists():(output/"wire.jsonl").write_bytes(wire.read_bytes())


def run(root, output):
    return "env-terminal.json",{"status":"BLOCKED","card_status":"AWAITING_RUNTIME_AND_SCOPED_RUN_BINDING",
        "reason":"Full terminal acceptance requires the original authorized Work/run binding and an isolated Linux Manager/runsc/execd runtime."}
