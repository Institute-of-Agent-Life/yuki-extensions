"""Exercise the pinned control protocol with a native Rust Windows consumer."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import tomllib
import uuid

from handshake_cargo import vendor_sdk
from personal_preview import Owner
from package import build


def build_peer(root, unit, output):
    pin = json.loads((root / 'compat/core-037/source.lock.json').read_bytes())
    crate = root / 'compat/core-037/yuki-plugin-sdk-1.0.0-alpha.11.crate'
    assert hashlib.sha256(crate.read_bytes()).hexdigest() == pin['rust_crate_sha256']
    source = root / 'tests/peers/control-probe'
    output.mkdir()
    report = {'source': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in source.rglob('*') if p.is_file() and not p.name.startswith('._')},
              'sdk_sha256': pin['rust_crate_sha256'], 'commands': []}
    try:
        with tempfile.TemporaryDirectory(prefix='yuki-control-intake-') as td:
            project = Path(td) / 'peer'
            shutil.copytree(source, project, ignore=shutil.ignore_patterns('._*', 'target'))
            lock = project / 'Cargo.lock'
            vendor_sdk(crate, project, lock if lock.exists() else None)
            commands = [['cargo', 'build', '--locked', '--offline'], ['rustc', '--version', '--verbose']]
            if not lock.exists():
                commands.insert(0, ['cargo', 'generate-lockfile', '--offline'])
            for args in commands:
                r = subprocess.run(args, cwd=project, capture_output=True, text=True, timeout=180)
                report['commands'].append({'argv': args, 'exit_code': r.returncode,
                                           'stdout': r.stdout, 'stderr': r.stderr})
                if r.returncode:
                    raise RuntimeError(r.stderr)
            shutil.copy2(lock, output.parent / 'generated-Cargo.lock')
            name = 'control-probe' + ('.exe' if os.name == 'nt' else '')
            shutil.copy2(project / 'target/debug' / name, output / name)
            report['artifacts'] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()}
        return report
    finally:
        (output.parent / 'build.json').write_text(json.dumps(report, indent=2), encoding='utf-8')


def prepare(root, out, *, real_plugin=False):
    pending, models, operations, cases = [], [], [], []
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            models.append(body)
            action = pending.pop(0) if pending else None
            msg = {'role': 'assistant', 'content': None if action else ''}
            if action:
                name, args = action
                msg['tool_calls'] = [{'id': 'control-intake-' + str(len(models)), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]
            result = {'id': 'control-intake-' + str(len(models)), 'choices': [{'index': 0,
                'message': msg, 'finish_reason': 'tool_calls' if action else 'stop'}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
            data = json.dumps(result).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    owner = None
    def save(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    def wait(function, label):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            value = function()
            if value: return value
            time.sleep(.1)
        raise RuntimeError('timed out: ' + label)
    def frames():
        if not owner.trace.exists(): return []
        lines = owner.trace.read_text(encoding='utf-8').splitlines()
        result = []
        for line in lines:
            try: result.append(json.loads(line))
            except json.JSONDecodeError: break
        return result
    def replies():
        if real_plugin:
            raw = frames()
            calls = {json.dumps(f['frame']['id']): f['frame']['params'] for f in raw
                     if f['direction'] == 'from_host' and f['frame'].get('method') == 'tool.call'}
            results = []
            for f in raw:
                frame = f['frame']; key = json.dumps(frame.get('id'))
                if f['direction'] == 'from_plugin' and key in calls and isinstance(frame.get('result'), dict):
                    result = frame['result']
                    results.append({'original_call': calls[key], 'response': {'Ok': result['data']}
                                    if result.get('ok') else {'Err': result.get('error')}})
            return results
        return [f['frame']['result']['data'] for f in frames() if f['direction'] == 'from_plugin'
                and isinstance(f['frame'].get('result'), dict)
                and 'original_call' in f['frame']['result'].get('data', {})]
    def op(*args):
        result = owner.cli('operator', *map(str, args))
        operations.append({'args': args, 'result': result}); save('operator.json', operations)
        return result
    try:
        declaration = tomllib.loads((root / 'plugins/trace/plugin.toml').read_text()) if real_plugin else None
        owner = Owner(root, out, 'trace' if real_plugin else 'control-probe',
                      declaration['grants'] if real_plugin else ['control.invoke', 'tool.call', 'forget.owner'],
                      contract='core-037', package_builder=build if real_plugin else build_peer,
                      binary_name='yuki-trace' if real_plugin else 'control-probe',
                      command_timeout=30)
        if real_plugin:
            shutil.copy2(owner.packages / 'package-manifest.json', out / 'build.json')
        cfg = owner.data / 'yuki.toml'
        text = cfg.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"')
        text = text.replace('\n[[plugins]]', f'\n[main]\nendpoint="http://127.0.0.1:{server.server_port}/model"\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=200000\nmax_output=512\n\n[[plugins]]')
        if real_plugin:
            text += '[[plugins.tools]]' + (root / 'plugins/trace/plugin.toml').read_text().split('[[tools]]', 1)[1]
        else:
            text += '[[plugins.tools]]\nname="control_probe"\ndescription="Inspect the authorized original trace"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={method={type="string"},args={type="object"},forged_actor={type="string"}},required=["method","args"],additionalProperties=false}\n'
        cfg.write_text(text, encoding='utf-8'); (out / 'host-config.toml').write_text(text, encoding='utf-8')
        person, ordinary = str(uuid.uuid4()), str(uuid.uuid4())
        with owner.running():
            op('person', 'create', person); op('person', 'set-admin', person, 'true')
            op('person', 'create', ordinary)
            human = op('account', 'open', 'qq', 'trace-intake', '200', 1, '--person', person, '--start', 1)
            other = op('account', 'open', 'qq', 'trace-intake', '201', 1, '--person', ordinary, '--start', 1)
            bot = op('account', 'open', 'qq', 'trace-intake', '100', 1, '--start', 1)
            def ingress(source, account, content):
                n = len(operations) + 100
                return op('ingress', 'record', json.dumps({'source': source, 'account': account['account'],
                    'bot_stage': bot['assignment'], 'reply_bot': '100', 'kind': 'message',
                    'occurred': n, 'observed': n, 'segments': [{'type': 'text', 'text': content}]}), '--accept')
            canary = 'TRACE_CANARY_' + str(uuid.uuid4())
            if real_plugin:
                pending.append(('task_control', {'action': 'accept', 'goal': canary}))
            base = ingress('original-trace', human, canary)
            wait(lambda: len(models) >= (2 if real_plugin else 1) and not pending, 'original model dispatch'); time.sleep(.4)
            event = base['event']
            def probe(label, account, args):
                previous = len(replies()); before = len(models)
                pending.append(('trace_query' if real_plugin else 'control_probe', args)); ingress(label, account, label)
                result = wait(lambda: replies()[previous:] if len(replies()) > previous else None, label)[0]
                if not real_plugin:
                    assert result['status']['Ok']['state'] == 'dispatched', result
                wait(lambda: len(models) >= before + 2 and not pending, 'paired original tool result')
                time.sleep(.3)
                cases.append({'case': label, **result}); save('cases.json', cases)
                return result
            trace = {'kind': 'event', 'identity': str(event), 'after': 0, 'limit': 3, 'content': False}
            def query(args): return args if real_plugin else {'method': 'trace.read', 'args': args}
            if not real_plugin:
                public = probe('public-role', other, {'method': 'character.public', 'args': {}})
                assert public['response']['Ok']['display_name']
            metadata = probe('admin-trace-metadata', human, query(trace))['response']['Ok']
            assert metadata['items'] and all('payload' not in item for item in metadata['items'])
            full = probe('admin-trace-content', human, query({**trace, 'after': 3 if real_plugin else 0, 'content': True}))['response']['Ok']
            assert full['items'] and all('payload' in item for item in full['items'])
            if real_plugin:
                assert canary in json.dumps(full), full
            denied = probe('ordinary-trace', other, query(trace))['response']
            assert '-32003' in denied['Err'], denied
            op('person', 'set-admin', person, 'false')
            revoked = probe('revoked-trace', human, query(trace))['response']
            assert '-32003' in revoked['Err'], revoked
            erased = op('privacy', 'erase', 'trace-source-erase', person, json.dumps([event]))
            if real_plugin:
                op('person', 'set-admin', person, 'true')
                after = probe('erased-source-read', human, query({**trace, 'after': 3, 'content': True}))['response']
                assert canary not in json.dumps(after), after
            end = time.monotonic() + (1 if real_plugin else 8)
            while time.monotonic() < end:
                if any(f['frame'].get('method') == 'forget.request' for f in frames()): break
                time.sleep(.1)
            obligations = op('privacy', 'pending', 'trace' if real_plugin else 'control-probe')
            forget = [f['frame'] for f in frames() if f['frame'].get('method') == 'forget.request']
            save('erasure.json', {'erase': erased, 'pending': obligations, 'callbacks': forget})
        report = {'status': 'PASS' if real_plugin else 'METHOD_INTAKE',
                  'card_status': 'UNPUBLISHED_QUERY_CANDIDATE' if real_plugin else 'BLOCKED',
                  'diagnostic_only': not real_plugin, 'private_store': False,
                  'core': owner.evidence(), 'original_event': event, 'cases': cases,
                  'model_http_calls': len(models), 'full_card_not_executed': [
                      'private store and bounded queue', 'R18 delayed writer and real effect reconciliation',
                      'authorized versioned export', 'published producer and consumer acceptance']}
        save('intake.json', report)
        return report
    finally:
        server.shutdown(); server.server_close()
        save('model.json', models); save('operator.json', operations); save('cases.json', cases)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); args.out.mkdir(parents=True)
    status = 'FAIL'
    try:
        report = prepare(Path(__file__).resolve().parents[1], args.out.resolve())
        status = report['status']
    except Exception:
        (args.out / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise
    finally:
        files = {p.relative_to(args.out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in args.out.rglob('*') if p.is_file() and not {'work', 'packages'}.intersection(p.relative_to(args.out).parts)}
        manifest = {'task': 'EXT-037', 'status': status, 'card_status': 'BLOCKED', 'phase': 'diagnostic',
                    'source_snapshot_sha256': os.environ.get('YUKI_SOURCE_SNAPSHOT_SHA256'), 'files': files}
        (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps({'task': 'EXT-037', 'status': status}))


if __name__ == '__main__': main()
