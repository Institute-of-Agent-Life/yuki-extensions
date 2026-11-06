"""Compare direct and native Monty ordinary refusals on a fixed real Host.

Run on HJW Windows with the existing Arch runtime. The provider and binding
record actual HTTP; neither replaces the Host or manufactures a tool receipt.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import uuid

from host_preview import materialize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wait(predicate, label, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError('timed out: ' + label)


def inventory(binary):
    code = ("import pathlib,hashlib,json,subprocess;p=pathlib.Path(" + repr(binary) + ");"
            "r=subprocess.run(['docker','--host','unix:///run/yuki-ext023-docker/api.sock',"
            "'ps','-aq'],check=True,capture_output=True,text=True);"
            "print(json.dumps({'plugin_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),"
            "'containers':sorted(r.stdout.split())}))")
    return json.loads(subprocess.check_output([
        'C:/Program Files/WSL/wsl.exe', '-d', 'Arch', '-u', 'root', '--exec', 'python3', '-c', code]))


def run_case(root, out, exe, mode, fixture, binary, binary_sha):
    out.mkdir()
    data = out / 'owner'
    models, deliveries, operations = [], [], []
    code = "a = yuki_send({'text': 42})\nb = yuki_send({'text': 'continue after original refusal'})\n[a,b]"
    if mode == 'code-control':
        code = "first = yuki_send({'text': 'before original refusal'})\n" + code

    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/binding':
                deliveries.append(body)
                result = {'accepted': body['operation'], 'sequence': len(deliveries)}
            else:
                models.append(body)
                n = len(models)
                calls = []
                if n == 1:
                    calls = [('accept-original', 'task_control', {'action': 'accept', 'goal': 'ordinary refusal continuation'})]
                elif n == 2:
                    calls = ([('bad-original', 'send', {'text': 42}),
                              ('good-original', 'send', {'text': 'continue after original refusal'})]
                             if mode == 'direct' else [('code-original', 'code_a', {'code': code})])
                msg = {'role': 'assistant', 'content': None if calls else 'done'}
                if calls:
                    msg['tool_calls'] = [{'id': call_id, 'type': 'function', 'function':
                        {'name': name, 'arguments': json.dumps(arguments)}} for call_id, name, arguments in calls]
                result = {'id': mode + '-' + str(n), 'object': 'chat.completion', 'model': 'fixture',
                          'choices': [{'index': 0, 'message': msg, 'finish_reason': 'tool_calls' if calls else 'stop'}],
                          'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(('127.0.0.1', 0), HTTP)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def cli(*args, check=True):
        r = subprocess.run([str(exe), '--data', str(data), *map(str, args)], capture_output=True,
                           text=True, encoding='utf-8', timeout=20)
        if check and r.returncode:
            raise RuntimeError(str(args[:3]) + ': ' + r.stderr)
        return r

    def op(*args):
        r = json.loads(cli('operator', *args).stdout)
        operations.append({'args': args, 'result': r})
        return r

    def start():
        nonlocal process
        with (out / 'host.txt').open('ab') as log:
            process = subprocess.Popen([str(exe), '--data', str(data), 'run'], stdout=log, stderr=log)
        wait(lambda: cli('operator', 'host', 'status', check=False).returncode == 0, 'Host ready')
        return process

    def stop(proc):
        try:
            if proc.poll() is None:
                cli('operator', 'shutdown', check=False)
        finally:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

    process = None
    try:
        before = inventory(binary)
        assert before['plugin_sha256'] == binary_sha
        cli('init')
        (data / 'SOUL.md').write_text('Fixed ordinary refusal fixture.', encoding='utf-8')
        cfg = data / 'yuki.toml'
        text = cfg.read_text(encoding='utf-8').replace('mode = "hybrid"', 'mode = "lexical-only"')
        text += f'\n[main]\nendpoint="http://127.0.0.1:{server.server_port}/model"\nbinding_endpoint="http://127.0.0.1:{server.server_port}/binding"\nmodel="fixture"\nname="Yuki"\nmax_output=512\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=4000000\nmerge_ms=1\n'
        if mode != 'direct':
            text += 'code_tool="code_a"\n\n[[plugins]]\nid="code_a"\nnamespace="code_a"\nprogram=' + json.dumps(sys.executable)
            text += '\nargs=' + json.dumps([str(root / 'tests/peers/codemode_wsl.py'), str(out / 'wire.jsonl'),
                'normal', '/var/tmp/yuki-ext023/rust-plugin-01/runtime.json', binary])
            text += '\ngrants=["tool.call","composition.read","composition.execute","forget.owner"]\n'
            contract = json.loads((fixture / 'runtime-contract.json').read_bytes())
            text += '[plugins.composition]\ntool="code_a"\n' + '\n'.join(
                k + '=' + json.dumps(contract[k]) for k in ['abi', 'engine_sha256', 'codec_sha256', 'launcher_sha256']) + '\n'
            text += '[[plugins.tools]]\nname="code_a"\ndescription="Rust isolated Monty candidate"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={code={type="string"}},required=["code"],additionalProperties=false}\n'
        cfg.write_text(text, encoding='utf-8')
        (out / 'host-config.toml').write_text(text, encoding='utf-8')
        process = start()
        person = str(uuid.uuid4())
        op('person', 'create', person)
        user = op('account', 'open', 'qq', 'code-refusal', '200', 1, '--person', person, '--start', 1)
        bot = op('account', 'open', 'qq', 'code-refusal', '100', 1, '--start', 1)
        event = op('ingress', 'record', json.dumps({'source': 'code-refusal-' + mode,
            'account': user['account'], 'bot_stage': bot['assignment'], 'kind': 'message', 'reply_bot': '100',
            'occurred': 100, 'observed': 100, 'segments': [{'type': 'text', 'text': 'compare original refusals'}]}), '--accept')
        wait(lambda: len(models) >= 3, 'original tool pairing')
        paired = {m['tool_call_id']: json.loads(m['content']) for m in models[2]['messages']
                  if m.get('role') == 'tool'}
        parent = paired['good-original' if mode == 'direct' else 'code-original']
        execution = parent['namespace']
        state = wait(lambda: (s if (s := op('main', 'inspect', execution))['state'] == 'completed' else None),
                     'original Main completed')
        save(out / 'after.json', state)
        initial_counts = (len(models), len(deliveries))
        stop(process)
        process = None
        for _ in range(2):
            process = start()
            time.sleep(1)
            assert (len(models), len(deliveries)) == initial_counts, 'cold restart repurchased or redelivered'
            stop(process)
            process = None
        frames = [json.loads(line) for line in (out / 'wire.jsonl').read_text(encoding='utf-8').splitlines()] if mode != 'direct' else []
        invokes = [f['frame']['params'] for f in frames if f['direction'] == 'from_plugin'
                   and f.get('forwarded', True) and f['frame'].get('method') == 'tool.invoke']
        expected_arguments = ([{'text': 'before original refusal'}, {'text': 'continue after original refusal'}]
                              if mode == 'code-control' else [{'text': 'continue after original refusal'}])
        continued = [d['arguments'] for d in deliveries] == expected_arguments
        if mode == 'direct':
            assert paired['bad-original']['state'] == 'failed', paired
            assert paired['good-original']['state'] == 'confirmed', paired
            assert paired['bad-original']['id'] != paired['good-original']['id']
            assert continued, deliveries
        else:
            continued = continued and len(invokes) == (3 if mode == 'code-control' else 2)
        after = inventory(binary)
        assert before == after, ('native cleanup failed', before, after)
        report = {'status': 'PASS' if continued else 'BLOCKED', 'candidate_only': True, 'mode': mode,
                  'event': event, 'execution': execution, 'model_http_calls': len(models),
                  'deliveries': deliveries, 'paired': paired, 'invokes': invokes,
                  'continued_after_refusal': continued, 'cold_restarts': 2,
                  'inventory_before': before, 'inventory_after': after, 'host_sha256': sha(exe)}
        save(out / 'result.json', report)
        return report
    finally:
        if process is not None:
            stop(process)
        server.shutdown()
        server.server_close()
        save(out / 'model.json', models)
        save(out / 'binding.json', deliveries)
        save(out / 'operator.json', operations)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--linux-plugin', required=True)
    parser.add_argument('--plugin-sha256', required=True)
    parser.add_argument('--modes', nargs='+', choices=['direct', 'code', 'code-control'],
                        default=['direct', 'code'])
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('requires HJW Windows Host and prepared Arch native runtime')
    out = args.out.resolve()
    out.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    work = out / 'work'
    work.mkdir()
    status = 'FAIL'
    keepalive = None
    try:
        exe, pin, platform = materialize(root, work, 'core-015-isolation')
        keepalive = subprocess.Popen(['C:/Program Files/WSL/wsl.exe', '-d', 'Arch', '-u', 'root', '--exec', 'sleep', '3600'])
        setup = subprocess.run(['C:/Program Files/WSL/wsl.exe', '-d', 'Arch', '-u', 'root', '--exec', '/bin/sh'],
            input=(args.fixture_root / 'runtime-setup.sh').read_bytes(), capture_output=True)
        save(out / 'runtime-setup.json', {'exit_code': setup.returncode,
            'stdout': setup.stdout.decode('utf-8', 'replace'), 'stderr': setup.stderr.decode('utf-8', 'replace'),
            'script_sha256': sha(args.fixture_root / 'runtime-setup.sh'),
            'contract_sha256': sha(args.fixture_root / 'runtime-contract.json')})
        if setup.returncode:
            raise RuntimeError('prepared runtime did not start')
        cases = {mode: run_case(root, out / mode, exe, mode, args.fixture_root,
                              args.linux_plugin, args.plugin_sha256) for mode in args.modes}
        status = 'PASS' if all(c['status'] == 'PASS' for c in cases.values()) else 'BLOCKED'
        save(out / 'intake.json', {'status': status, 'formal_card_status': 'BLOCKED', 'published': False,
            'source_commit': pin['source_commit'], 'host': platform, 'sdk': pin['sdk'],
            'host_schema_sha256': pin['schema_sha256'], 'linux_plugin_sha256': args.plugin_sha256,
            'scope': 'same ordinary invalid arguments then independent valid effect; real direct and Monty',
            'cases': cases, 'remaining': ['authorization parity', 'H14 and public root reserve ledger',
                'Work/run futures', 'light frozen aliases', 'formal publication']})
    except Exception:
        (out / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        if keepalive is not None:
            keepalive.terminate()
            keepalive.wait()
        files = {p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*')
                 if p.is_file() and not p.name.startswith('._')
                 and 'work' not in p.relative_to(out).parts and 'owner' not in p.relative_to(out).parts}
        save(out / 'manifest.json', {'task': 'EXT-024', 'status': status, 'formal_card_status': 'BLOCKED',
             'phase': 'ordinary-refusal-intake', 'source_snapshot_sha256': os.environ.get('YUKI_SOURCE_SNAPSHOT_SHA256'),
             'files': files})
        print(json.dumps({'task': 'EXT-024', 'status': status}))


if __name__ == '__main__':
    main()
