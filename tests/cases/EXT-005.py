"""Exercise the shipped Windows host and a real RFC6455/pbbp2 native fixture."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import zipfile

from host_preview import materialize
from package import build


def wait(check, timeout=30):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        if check(): return
        time.sleep(.1)
    raise RuntimeError("native fixture/host readiness timeout")


def fixture_imports(root, work):
    peers=root/"tests/peers"
    pin=json.loads((peers/"lark-fixture.lock.json").read_bytes())
    assert hashlib.sha256((peers/"lark_frames.py").read_bytes()).hexdigest()==pin["schema_sha256"]
    target=work/"native-fixture"
    target.mkdir()
    for pkg in pin["wheels"]:
        wheel=Path(os.environ["UV_FIND_LINKS"])/pkg["filename"]
        assert hashlib.sha256(wheel.read_bytes()).hexdigest()==pkg["sha256"]
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(target)
    sys.path[:0]=[str(target),str(peers)]
    from lark_frames import Frame
    from websockets.sync.server import serve
    return Frame,serve


def prepare(root, output, *, contract="core-032", package_builder=build, reader_archives=None, message_sample=None):
    work=output/"work"
    work.mkdir()
    Frame,serve=fixture_imports(root,work)
    host,pin,platform=materialize(root,work,contract)
    packages=output/"packages"
    binary=packages/("yuki-feishu.exe" if os.name=="nt" else "yuki-feishu")
    if reader_archives:
        import feishu_reader_replay as readers
        reader_pins = readers.packages(reader_archives, packages)
        private = work/"installed-state"
    else:
        built=package_builder(root,"feishu",packages)
        (output/"build.txt").write_text("\n".join(cmd["stdout"]+cmd["stderr"] for cmd in built["commands"]),encoding="utf-8")
    data=work/"host"; proc=None
    routes={"cli_a":("a","feishu"),"cli_b":("b","lark")}
    auth=[]; native=[]; failures=[]
    phase="break"
    complete=threading.Event()
    release=threading.Event()
    trace=work/"observer";trace.mkdir()
    if not reader_archives:
        (trace/"break-before-writer").touch()

    def frame(kind, raw=b"", seq=0, count=1, *, serial=1):
        f=Frame(SeqID=serial,LogID=100+serial,service=9,method=0 if kind=="pong" else 1,payload=raw)
        for k,v in {"type":kind,"message_id":str(serial),"sum":str(count),"seq":str(seq)}.items():
            f.headers.add(key=k,value=v)
        return f.SerializeToString()

    def packet(app, wrong_tenant=False):
        slug,region=routes[app]
        content = "hi @_user_1"
        mentions = [{"key":"@_user_1","id":{"open_id":app},"name":"Yuki"}]
        if not reader_archives:
            # The short key sorts first in one tenant, and last in the other.
            content = "🌨 @_user_10 / @_user_1 / @_user_10 / @_user_100"
            mentions.append({"key":"@_user_10","id":{"open_id":"ou_ten"},"name":"Ten"})
            if region == "lark":
                mentions.reverse()
        message = {"message_type":"text","content":json.dumps({"text":content})}
        if message_sample:
            message, _ = message_sample(app)
        return json.dumps({"header":{"app_id":app,"event_type":"im.message.receive_v1",
            "tenant_key":"wrong" if wrong_tenant else "tenant-"+slug},"event":{
            "sender":{"sender_type":"user","sender_id":{"open_id":"ou_shared"}},
            "message":{"message_id":"om_shared","chat_id":"oc_room","chat_type":"group",
            "thread_id":"thread","parent_id":"om_original","create_time":"1000",**message,"mentions":mentions}}}).encode()

    def scenario(conn):
        local_phase=phase
        app=urlsplit(conn.request.path).path.strip("/")
        def receive():
            msg=Frame.FromString(conn.recv(timeout=10))
            ty=next(h.value for h in msg.headers if h.key=="type")
            native.append({"phase":local_phase,"app":app,"type":ty,"seq":msg.SeqID,"log":msg.LogID,
                "headers":{h.key:h.value for h in msg.headers},
                "payload":json.loads(msg.payload) if msg.HasField("payload") and msg.payload else None})
            return ty,msg
        def ack(serial,code):
            while True:
                ty,msg=receive()
                if ty=="ping":
                    conn.send(frame("pong",b'{"PingInterval":1}'));continue
                assert msg.SeqID==serial and msg.LogID==serial+100 and json.loads(msg.payload)=={"code":code}
                assert any(h.key=="biz_rt" for h in msg.headers)
                return
        try:
            assert receive()[0]=="ping"
            conn.send(frame("pong",b'{"PingInterval":1}'))
            event=packet(app)
            if reader_archives:
                readers.send_phase(local_phase,conn,frame,ack,event)
                complete.set()
                release.wait(18)
                return
            split=len(event)//2
            second=frame("event",event[split:],1,2)
            conn.send(second);conn.send(second)
            # An independent card round trip proves both fragments were processed without a premature ACK.
            conn.send(frame("card",b"{}",serial=2));ack(2,200)
            conn.send(frame("event",event[:split],0,2))
            if local_phase=="break":
                from websockets.exceptions import ConnectionClosed
                try:ack(1,200)
                except ConnectionClosed:pass
                else:raise AssertionError("success before native writer")
            else:
                ack(1,200)
                conn.send(frame("event",event,serial=3));ack(3,200)
                conn.send(frame("event",packet(app,wrong_tenant=True),serial=4));ack(4,500)
            complete.set()
            release.wait(18)
        except Exception as exc:
            failures.append(repr(exc));complete.set()

    ws=serve(scenario,"127.0.0.1",0,ping_interval=None)
    port=ws.socket.getsockname()[1]
    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            app=body.get("AppID")
            valid=app in routes and body.get("AppSecret")=="fixture-"+app
            auth.append({"path":self.path,"app":app,"authenticated":valid})
            assert self.path=="/callback/ws/endpoint"
            result={"code":0,"data":{"URL":f"ws://127.0.0.1:{port}/{app}?service_id=9",
                "ClientConfig":{"PingInterval":1,"ReconnectInterval":1,"ReconnectCount":2,"ReconnectNonce":0}}} if valid else {"code":1000040342}
            payload=json.dumps(result).encode()
            self.send_response(200);self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
    api=ThreadingHTTPServer(("127.0.0.1",0),Endpoint)
    for server in (ws,api):threading.Thread(target=server.serve_forever,daemon=True).start()
    env=dict(os.environ,YUKI_FEISHU_API=f"http://127.0.0.1:{api.server_port}")
    def cli(*args,check=True):
        r=subprocess.run([host,"--data",data,*args],cwd=work,env=env,text=True,capture_output=True,timeout=20)
        if check and r.returncode:raise RuntimeError(str(args[:3])+": "+r.stderr[:400])
        return json.loads(r.stdout) if not r.returncode and r.stdout.strip() else None
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
    def install(app,stage):
        slug,domain=routes[app]
        env.update(YUKI_FEISHU_APP_ID=app,YUKI_FEISHU_APP_SECRET="fixture-"+app,YUKI_FEISHU_TENANT="tenant-"+slug,YUKI_FEISHU_DOMAIN=domain)
        cfg=data/"yuki.toml"
        base=cfg.read_text(encoding="utf-8").split("[[plugins]]")[0]
        # Distinct production installations retain independent IDs. The historical
        # CORE-032 witness used a single ID, and its original scenario is preserved.
        ident = "feishu-"+slug if contract=="core-038-main" else "feishu"
        vals={"id":ident,"namespace":"fs."+slug,"program":sys.executable,
            "args":[str(root/"tests/peers/feishu_relay.py"),str(binary),str(trace)],
            "platform":domain,"bot_stage":stage,"grants":["gateway.inbound"],
            "env":[k for k in env if k.startswith("YUKI_FEISHU_")]}
        if reader_archives:
            vals["args"] = [str(root/"tests/peers/base_relay.py"), str(binary),
                            str(trace/"wire.jsonl"), str(private), "none"]
        cfg.write_text(base+"\n[[plugins]]\n"+"\n".join(f"{k} = {json.dumps(v)}" for k,v in vals.items())+"\n",encoding="utf-8")
    try:
        cli("init")
        if contract=="core-038-main":
            # This Host requires an explicit offline memory mode when no embedder is installed.
            cfg=data/"yuki.toml"
            cfg.write_text(cfg.read_text(encoding="utf-8").replace('mode = "hybrid"','mode = "lexical-only"'),encoding="utf-8")
        start()
        stages={}; accounts={}
        for n,(app,(slug,domain)) in enumerate(routes.items(),1):
            person=f"00000000-0000-4000-8000-00000000005{n}"
            cli("operator","person","create",person)
            accounts[app]=cli("operator","account","open",domain,"fs."+slug,"ou_shared","1","--person",person,"--start","1")
            stages[app]=cli("operator","account","open",domain,"fs."+slug,app,"1","--start","1")["assignment"]
        stop()
        if reader_archives:
            observations = {}
            killed = {}
            wire = trace/"wire.jsonl"
            for app in routes:
                install(app,stages[app])
                ids = {}
                for phase, version in [("old","0.1.0-alpha.1"),("new","0.1.0-alpha.2"),("rollback","0.1.0-alpha.1")]:
                    # Restore the previous stopped copy at the installation's stable cwd.
                    if phase == "old":
                        private.mkdir()
                    else:
                        shutil.copytree(stopped,private)
                    package = reader_pins[version]
                    shutil.copyfile(packages/package["binary"],binary)
                    assert hashlib.sha256(binary.read_bytes()).hexdigest() == package["binary_sha256"]
                    cursor = len(wire.read_bytes().splitlines()) if wire.exists() else 0
                    complete.clear()
                    start()
                    wait(complete.is_set)
                    assert not failures, failures
                    # Stop the native child while its observing relay still owns the handle.
                    wire.with_suffix(".kill").touch()
                    marker = wire.with_suffix(".killed")
                    wait(marker.exists)
                    killed[app + "-" + phase] = int(marker.read_text(encoding="ascii"))
                    marker.unlink()
                    stop()
                    rows = [json.loads(line) for line in wire.read_bytes().splitlines()[cursor:]]
                    ids[phase] = readers.event_ids(rows,phase)
                    stopped = work/(app+"-"+phase+"-stopped")
                    private.rename(stopped)
                    assert not list(stopped.iterdir())
                assert ids["old"][0] == ids["new"][1] and ids["new"][0] == ids["rollback"][0]
                assert ids["old"][0] != ids["rollback"][0]
                observations[app] = ids
            assert set(observations["cli_a"]["new"]).isdisjoint(observations["cli_b"]["new"])
            return "reader-replay.json", {"status":"PASS","scope":"stopped-plugin-copy","host":platform,
                "host_source":pin["source_commit"],"packages":reader_pins,"events":observations,
                "accounts":accounts,"killed_native_pids":killed,"stopped_private_files":{p.name:[] for p in work.glob("*-stopped")}}
        install("cli_a",stages["cli_a"])
        start()
        wait(complete.is_set)
        assert not failures,failures
        assert (trace/"broken").exists()
        stop()
        for phase,app in [("replay","cli_a"),("other-app","cli_b")]:
            complete.clear()
            install(app,stages[app]);start()
            wait(complete.is_set);assert not failures,failures
            stop()
        phase="invalid-auth"
        env["YUKI_FEISHU_APP_SECRET"]="invalid-fixture"
        start();wait(lambda:any(not a["authenticated"] for a in auth))
        stop()
        records=[json.loads(s) for s in (trace/"wire.jsonl").read_text(encoding="utf-8").splitlines()]
        calls=[r["frame"] for r in records if r["frame"].get("method")=="gateway.inbound"]
        results=[r["frame"]["result"] for r in records if "event" in r["frame"].get("result",{})]
        assert len(calls)==5 and len(results)==4,(len(calls),results)
        ids=[r["event"] for r in results]
        assert ids[0]==ids[1] and ids[2]==ids[3] and ids[0]!=ids[2],ids
        assert accounts["cli_a"]["account"]!=accounts["cli_b"]["account"]
        for call, app in zip(calls, ["cli_a"] * 3 + ["cli_b"] * 2, strict=True):
            p=call["params"];assert p["space"]=="oc_room" and p["topic"]=="thread"
            expected = [
                {"type":"text","text":"🌨 "}, {"type":"mention","native":"ou_ten","label":"@Ten"},
                {"type":"text","text":" / "}, {"type":"mention","native":app,"label":"@Yuki"},
                {"type":"text","text":" / "}, {"type":"mention","native":"ou_ten","label":"@Ten"},
                {"type":"text","text":" / @_user_100"}, {"type":"reply","native_id":"om_original"},
            ]
            if message_sample:
                _, expected = message_sample(app)
            assert p["segments"] == expected, (app, p["segments"])
            assert p["occurred"]==1000 and p["sender"]=="ou_shared"
        assert all(e["type"]!="event" for e in native if e["phase"]=="break")
        return "lark-frames.json",{"status":"PASS","card_status":"VERIFIED_ON_UNPUBLISHED_CANDIDATE",
            "source_commit":pin["source_commit"],"host":platform,"sdk":pin["rust_crate_sha256"],
            "plugin":built["artifacts"][binary.name],"accounts":accounts,"durable_events":ids,"native":native,"auth":auth,"transcript":records}
    except Exception:
        if contract != "core-032" and proc and proc.poll() is None:
            status=subprocess.run([host,"--data",data,"operator","host","status"],cwd=work,env=env,
                text=True,capture_output=True,timeout=8)
            (output/"host-status.json").write_text(json.dumps({"phase":phase,"exit_code":status.returncode,
                "stdout":status.stdout,"stderr":status.stderr},indent=2),encoding="utf-8")
        raise
    finally:
        release.set();stop();api.shutdown();api.server_close();ws.shutdown()
        if (trace/"wire.jsonl").exists():(output/"wire.jsonl").write_bytes((trace/"wire.jsonl").read_bytes())
        (output/"native.json").write_text(json.dumps({"native":native,"auth":auth,"failures":failures},indent=2),encoding="utf-8")


def run(root, output):
    return "lark-frames.json",{"status":"BLOCKED","card_status":"AWAITING_CORE_032_HANDOFF",
        "reason":"The locked host is a pre-merge candidate."}
