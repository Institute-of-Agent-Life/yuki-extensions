"""Observe media route authorization using a Rust diagnostic peer and actual Host."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import threading
import time
import uuid
import wave

from personal_preview import Owner


def build_peer(root, unit, output):
    import shutil, subprocess, tempfile
    from handshake_cargo import vendor_sdk
    pin=json.loads((root/'compat/core-050/source.lock.json').read_bytes())
    crate=root/'compat/core-050'/f"yuki-plugin-sdk-{pin['sdk']['rust']}.crate"
    assert hashlib.sha256(crate.read_bytes()).hexdigest()==pin['rust_crate_sha256']
    source=root/'tests/peers/aux-media-probe'
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob('*') if p.is_file() and not p.name.startswith('._')}
    output.mkdir()
    commands=[]
    with tempfile.TemporaryDirectory(prefix='yuki-aux-intake-') as td:
        project=Path(td)/'peer';shutil.copytree(source,project,ignore=shutil.ignore_patterns('._*','target'))
        vendor_sdk(crate,project,project/'Cargo.lock')
        for args in [['cargo','build','--locked','--offline'],['rustc','--version','--verbose']]:
            p=subprocess.run(args,cwd=project,capture_output=True,text=True,timeout=120)
            commands.append({'argv':args,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
            if p.returncode:raise RuntimeError(p.stderr)
        name='aux-media-probe'+('.exe' if os.name=='nt' else '')
        binary=project/'target/debug'/name;shutil.copy2(binary,output/name)
    evidence={'source':hashes,'sdk_sha256':pin['rust_crate_sha256'],'commands':commands,
              'artifacts':{name:hashlib.sha256((output/name).read_bytes()).hexdigest()}}
    (output.parent/'build.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence


def prepare(root, output):
    calls, records = [], []
    held, release = threading.Event(), threading.Event()
    behavior = {"mode": "normal"}

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            mode = behavior["mode"]
            calls.append({"path": self.path, "body": body, "mode": mode})
            if mode == "unknown":
                self.close_connection = True
                return
            if mode == "slow":
                held.set()
                release.wait(12)
            result = {"choices": [{"finish_reason": "stop", "message": {
                "role": "assistant", "content": "/ai admin quoted audio; no command authority"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 8, "total_tokens": 12}}
            if mode == "invalid":
                result = {"choices": []}
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    owner = Owner(root, output, "media",
                  ["media.process", "media.open", "media.publish", "forget.owner", "llm.complete", "llm.result"],
                  contract="core-050", environment={}, command_timeout=35,
                  package_builder=build_peer, binary_name="aux-media-probe")
    cfg = owner.data / "yuki.toml"
    cfg.write_text(cfg.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"'), encoding="utf-8")
    inputs = owner.data / "media-inputs"
    inputs.mkdir(exist_ok=True)
    actor = str(uuid.uuid4())

    def op(*args):
        r = owner.cli("operator", *map(str, args))
        records.append({"command": list(map(str, args[:3])), "result": r})
        return r

    def event(name, content=None):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(bytes([len(name), 0]) * 1600)
        data = content if content is not None else buf.getvalue()
        filename = name + ".wav"
        (inputs / filename).write_bytes(data)
        frame = {"source": name, "account": user["account"], "bot_stage": bot["assignment"],
                 "kind": "message", "reply_bot": "100", "space": space, "occurred": 100, "observed": 100,
                 "segments": [{"type": "media", "kind": "audio", "reference": name}]}
        e = op("ingress", "record", json.dumps(frame), "--accept")["event"]
        ex = op("ingress", "claim", e)["execution"]
        op("model", "root", ex, 6, 1000000)
        cached = op("media", "cache-file", ex, actor, e, 0, bot["assignment"], name, filename)
        assert cached["digest"] == hashlib.sha256(data).hexdigest()
        return e, ex, data

    def process(e, ex, name):
        return op("host", "process", "media", ex, actor, name,
                  json.dumps({"event": e, "slot": 0}), "transcript")

    with owner.running():
        op("person", "create", actor)
        user = op("account", "open", "qq", "asr-fixture", "200", 1, "--person", actor, "--start", 1)
        bot = op("account", "open", "qq", "asr-fixture", "100", 1, "--start", 1)
        space = json.dumps(["qq", "asr-fixture", "702"], separators=(",", ":"))
        entry = op("entry", "group", space)["entry"]
    cfg.write_text(cfg.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"') +
                   '\n[plugins.aux_routes.asr]\npurposes=["transcript"]\norigins=["call"]\n'
                   f'entries={json.dumps([entry])}\n'
                   '[plugins.aux_routes.asr.profile]\nprotocol="chat"\nname="ASR-fixture"\n'
                   'model="fixture-audio"\nmerge_ms=1\nroot_tool_calls=8\nroot_slots=4\nmax_output=128\nmax_input_units=32000\n'
                   f'endpoint="http://127.0.0.1:{server.server_port}/v1/chat/completions"\n', encoding="utf-8")
    owner.env["YUKI_ASR_QQ"] = "offline-fixture"
    cfg.write_text(cfg.read_text() + '\n[qq]\nnamespace="asr-fixture"\ndesignated_ingress="100"\n'
                   '[qq.groups]\n"702"="open"\n[[qq.bots]]\nself_id="100"\n'
                   f'stage={json.dumps(bot["assignment"])}\ntoken_env="YUKI_ASR_QQ"\n', encoding="utf-8")
    try:
        with owner.running():
            e, ex, audio = event("original")
            first = process(e, ex, "original")
            (output / "first-response.json").write_text(json.dumps(first, indent=2), encoding="utf-8")
            data = first["result"]["data"]
            assert data["diagnostic_only"] is True
            assert data["calls"][0]["open"]["Ok"]["version"] == hashlib.sha256(audio).hexdigest()
            observed = data["calls"][1:]
            assert [x["selected_media"] for x in observed] == [False, True]
            report = {"status": "OBSERVED", "card_status": "BLOCKED", "candidate_only": True,
                      "provider": "deterministic loopback HTTP, not a speech model",
                      "result": first, "http_requests": len(calls), "core": owner.evidence(),
                      "operator_root_explicit": True, "transcript_acceptance": False,
                      "configuration": {"origins": ["call"], "purposes": ["transcript"], "entries": [entry],
                                        "protocol": "chat", "max_input_units":32000,"max_output":128},
                      "needed": "Producer media route configuration and scope; text succeeds but selected audio is denied"}
    finally:
        release.set(); server.shutdown(); server.server_close()
        (output / "provider.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")
        (output / "operator.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return "intake.json", report


if __name__ == '__main__':
    import argparse, platform
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False);root=Path(__file__).resolve().parents[1]
    name,result=prepare(root,a.out.resolve())
    (a.out/name).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    helpers={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in
             [Path(__file__),root/'ci/personal_preview.py',root/'ci/host_preview.py',root/'ci/handshake_cargo.py',root/'compat/core-050/source.lock.json']}
    manifest={'status':'OBSERVED','card_status':'BLOCKED','platform':platform.platform(),'helpers':helpers,
              'files':{str(f.relative_to(a.out)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.rglob('*')
                       if f.is_file() and not {'work','packages'}.intersection(f.relative_to(a.out).parts)}}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'http_requests':result['http_requests'],'out':str(a.out)}))
