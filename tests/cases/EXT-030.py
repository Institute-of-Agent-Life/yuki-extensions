"""Actual Rust media / immutable Host pairing; deterministic HTTP provider only."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid
import wave

from personal_preview import Owner


def prepare(root, output, *, original_source_replay=False):
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
            if mode == "tool":
                result["choices"][0]["finish_reason"] = "tool_calls"
                result["choices"][0]["message"]["tool_calls"] = [{"id": "spoken-tool", "type": "function",
                    "function": {"name": "admin", "arguments": "{}"}}]
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
    configured = {'YUKI_MEDIA_ASR_ROUTE': 'asr'}
    if os.environ.get('YUKI_MEDIA_FFMPEG'):
        configured['YUKI_MEDIA_FFMPEG'] = os.environ['YUKI_MEDIA_FFMPEG']
    owner = Owner(root, output, "media",
                  ["media.process", "media.open", "media.publish", "forget.owner", "llm.complete", "llm.result"],
                  contract=os.environ.get('YUKI_ASR_HOST_CONTRACT', 'core-038-selected-erasure'),
                  environment=configured, command_timeout=40)
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
                   '\n[plugins.aux_routes.asr]\npurposes=["transcript"]\norigins=["call"]\nmedia=["audio"]\n'
                   f'entries={json.dumps([entry])}\n'
                   '[plugins.aux_routes.asr.profile]\nprotocol="chat"\nname="ASR-fixture"\n'
                   'model="fixture-audio"\nmerge_ms=1\nroot_tool_calls=8\nroot_slots=4\nmax_output=128\nmax_input_units=180000\n'
                   f'endpoint="http://127.0.0.1:{server.server_port}/v1/chat/completions"\n', encoding="utf-8")
    owner.env["YUKI_ASR_QQ"] = "offline-fixture"
    cfg.write_text(cfg.read_text() + '\n[qq]\nnamespace="asr-fixture"\ndesignated_ingress="100"\n'
                   '[qq.groups]\n"702"="open"\n[[qq.bots]]\nself_id="100"\n'
                   f'stage={json.dumps(bot["assignment"])}\ntoken_env="YUKI_ASR_QQ"\n', encoding="utf-8")
    def approve_route():
        with (output / 'route-approval.log').open('wb') as log:
            daemon = subprocess.Popen([owner.exe, '--data', owner.data, 'run'], cwd=owner.work,
                                      env=owner.env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                assert daemon.poll() is None
                result = owner.command('operator', 'control', 'read', 'plugin.get', '{"plugin_id":"media"}')
                if result.returncode == 0:
                    state = json.loads(result.stdout)
                    break
                time.sleep(.05)
            else:
                raise RuntimeError('original route approval status unavailable')
            assert state['status'] == 'discovered'
            args = {'plugin_id': 'media'}
            op('control', 'write', 'plugin.approve', json.dumps({
                **args, 'request_id': str(uuid.uuid4()), 'expected_revision': state['revision'],
            }))
            approval = op('control', 'read', 'plugin.get', json.dumps(args))
            assert approval['status'] == 'disabled'
            assert set(approval['approved_permissions']) == set(state['requested_permissions'])
            op('host', 'enable', 'media', 'true')
        finally:
            if daemon.poll() is None:
                owner.command('operator', 'shutdown')
                try:
                    daemon.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait()

    try:
        approve_route()
        with owner.running():
            e, ex, audio = event("original")
            first = process(e, ex, "original")
            (output / "first-response.json").write_text(json.dumps(first, indent=2), encoding="utf-8")
            assert first["state"] == "confirmed" and first["result"]["ok"] is True, first
            assert first["result"]["data"]["text"].startswith("/ai admin")
            assert len(calls) == 1
            received = calls[0]["body"]["messages"][-1]["content"]
            raw = next(c["input_audio"]["data"] for c in received if c.get("type") == "input_audio")
            assert base64.b64decode(raw) == audio
            assert first['result']['data']['transcript_stored']
            same = process(e, ex, "original")
            assert same['handle'] == first['handle'] and same['state'] == first['state'] and len(calls) == 1
            persisted = op('effect', 'read', ex, 'original', actor)
            assert persisted['result'] == first['result']
            if original_source_replay:
                replay = process(e, ex, "different-host-call")
                (output / "distinct-call.json").write_text(json.dumps(replay, indent=2), encoding="utf-8")
                assert replay["handle"] != first["handle"]
                assert replay["result"]["data"]["request"] == first["result"]["data"]["request"]
                assert replay["result"]["data"]["root"] == first["result"]["data"]["root"] == ex
                assert len(calls) == 1
            if os.environ.get('YUKI_MEDIA_FFMPEG'):
                # AMR-NB mode 0, 95 payload bits per 20 ms frame.
                frame = bytes([0x04]) + bytes(12)
                amr, amr_ex, _ = event('original-amr', b'#!AMR\n' + frame * 20)
                converted = process(amr, amr_ex, 'amr')
                assert converted['result']['data']['transcript_stored']
                data = calls[-1]['body']['messages'][-1]['content'][0]['input_audio']
                assert data['format'] == 'wav' and base64.b64decode(data['data']).startswith(b'RIFF')
            else:
                converted = None
            calls_before_error = len(calls)
            corrupt, cx, _ = event("corrupt", b"not audio")
            assert process(corrupt, cx, "corrupt")["result"]["ok"] is False
            assert len(calls) == calls_before_error
            behavior["mode"] = "tool"
            tool, tool_ex, _ = event('tool-result')
            assert process(tool, tool_ex, 'unexpected-tool')['result']['ok'] is False
            behavior["mode"] = "unknown"
            u, ux, _ = event("unknown")
            unknown = process(u, ux, "unknown")
            assert unknown["result"]["ok"] is False
            n = len(calls)
            observed = process(u, ux, "unknown")
            assert observed['handle'] == unknown['handle'] and observed['state'] == unknown['state'] and len(calls) == n
            behavior["mode"] = "slow"
            r, rx, _ = event("erased")
            with ThreadPoolExecutor(max_workers=1) as pool:
                active = pool.submit(process, r, rx, "erased")
                assert held.wait(10)
                # An unrelated processing failure returns while HTTP is still held.
                independent = process(corrupt, cx, "corrupt-during-asr")
                assert independent["result"]["ok"] is False and not active.done()
                erase = op("privacy", "erase", "asr-forget", actor, json.dumps([r]))
                release.set()
                late = active.result(timeout=20)
                assert late.get("result") is None or late["result"].get("ok") is False
            end = time.monotonic() + 8
            while op("privacy", "pending", "media")["obligations"] and time.monotonic() < end:
                time.sleep(.1)
            assert not op("privacy", "pending", "media")["obligations"]
            report = {"status": "PASS", "card_status": "NATIVE_ASR_PROCESSOR_CANDIDATE", "candidate_only": True,
                      "provider": "deterministic HTTP fixture; no speech quality or paid model claim",
                      "original": first, "same_call": same, "amr": converted,
                      "unknown": unknown, "erasure": erase, "late": late,
                      "independent_while_held": independent, "core": owner.evidence(),
                      "remaining": ["original Main and history consumption", "cross-Bot replay",
                                    "original SILK receiver conversion", "distinct Host call source deduplication", "formal release"]}
    finally:
        release.set(); server.shutdown(); server.server_close()
        (output / "provider.json").write_text(json.dumps(calls, indent=2), encoding="utf-8")
        (output / "operator.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    return "asr-source.json", report


def run(root, output):
    return 'asr-source.json', {'status': 'BLOCKED', 'card_status': 'WAITING_FOR_SOURCE_SCOPED_MAIN_REPLAY'}
