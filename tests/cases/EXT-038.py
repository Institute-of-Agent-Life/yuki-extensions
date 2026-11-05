"""Exercise real shared role/SOUL methods; avatar application remains pending."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import threading
import time
import tomllib
import uuid

from personal_preview import Owner


def prepare(root, output):
    pending, models, operations, cases = [], [], [], []
    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            models.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            action = pending.pop(0) if pending else None
            message = {'role': 'assistant', 'content': None if action else ''}
            if action:
                message['tool_calls'] = [{'id': 'character-' + str(len(models)), 'type': 'function',
                    'function': {'name': 'character_manage', 'arguments': json.dumps(action)}}]
            data = json.dumps({'id': 'character-' + str(len(models)), 'choices': [{'index': 0,
                'message': message, 'finish_reason': 'tool_calls' if action else 'stop'}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    owner = None
    def wait(function, label):
        until = time.monotonic() + 30
        while time.monotonic() < until:
            value = function()
            if value: return value
            time.sleep(.1)
        raise RuntimeError('timed out: ' + label)
    def frames():
        if not owner.trace.exists(): return []
        result = []
        for line in owner.trace.read_text(encoding='utf-8').splitlines():
            try: result.append(json.loads(line))
            except json.JSONDecodeError: break
        return result
    def replies():
        raw = frames()
        calls = {json.dumps(f['frame']['id']): f['frame']['params'] for f in raw
                 if f['direction'] == 'from_host' and f['frame'].get('method') == 'tool.call'}
        return [{'original_call': calls[json.dumps(f['frame']['id'])], 'result': f['frame']['result']}
                for f in raw if f['direction'] == 'from_plugin' and 'result' in f['frame']
                and json.dumps(f['frame'].get('id')) in calls]
    def op(*args):
        value = owner.cli('operator', *map(str, args))
        operations.append({'args': args, 'result': value}); save('operator.json', operations)
        return value
    def system(request):
        return json.dumps([m.get('content') for m in request['messages']
                           if m['role'] in {'system', 'developer'}], ensure_ascii=False)
    def probe(label, account, args):
        count, before = len(replies()), len(models)
        pending.append(args)
        op('ingress', 'record', json.dumps({'source': label, 'account': account['account'],
            'bot_stage': bot['assignment'], 'reply_bot': '100', 'kind': 'message',
            'occurred': len(operations) + 100, 'observed': len(operations) + 100,
            'segments': [{'type': 'text', 'text': label}]}), '--accept')
        result = wait(lambda: replies()[count:] if len(replies()) > count else None, label)[0]
        wait(lambda: len(models) >= before + 2 and not pending, 'paired original result')
        time.sleep(.25)
        cases.append({'case': label, 'model_request_range': [before, len(models)], **result})
        save('cases.json', cases)
        return result['result'], models[before:]
    def ok(label, account, action, body=None):
        args = {'action': action}
        if body is not None: args['body'] = body
        result, wire = probe(label, account, args)
        assert result.get('ok') is True, result
        return result['data'], wire
    def denied(label, account, action, body=None):
        args = {'action': action}
        if body is not None: args['body'] = body
        result, _ = probe(label, account, args)
        assert result.get('ok') is False, result
        return result
    try:
        declaration = tomllib.loads((root / 'plugins/character/plugin.toml').read_text())
        owner = Owner(root, output, 'character', declaration['grants'], contract='core-037',
                      command_timeout=30, relay='character_stdio.py')
        shutil.copy2(owner.packages / 'package-manifest.json', output / 'build.json')
        cfg = owner.data / 'yuki.toml'
        text = cfg.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"')
        text = text.replace('\n[[plugins]]', f'\n[main]\nendpoint="http://127.0.0.1:{server.server_port}/model"\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=200000\nmax_output=512\n\n[[plugins]]')
        text += '[[plugins.tools]]' + (root / 'plugins/character/plugin.toml').read_text().split('[[tools]]', 1)[1]
        cfg.write_text(text, encoding='utf-8'); (output / 'host-config.toml').write_text(text, encoding='utf-8')
        person, ordinary = str(uuid.uuid4()), str(uuid.uuid4())
        with owner.running():
            op('person', 'create', person); op('person', 'set-admin', person, 'true')
            op('person', 'create', ordinary)
            human = op('account', 'open', 'qq', 'character-intake', '200', 1, '--person', person, '--start', 1)
            other = op('account', 'open', 'qq', 'character-intake', '201', 1, '--person', ordinary, '--start', 1)
            bot = op('account', 'open', 'qq', 'character-intake', '100', 1, '--start', 1)
            public, _ = ok('ordinary-public', other, 'public')
            denied('ordinary-soul', other, 'soul')
            before, _ = ok('admin-role', human, 'read')
            assert public['id'] == before['id']
            new_name = 'EXT038_' + uuid.uuid4().hex
            update = {'request_id': str(uuid.uuid4()), 'expected_revision': before['revision'], 'display_name': new_name}
            changed, continuation = ok('rename', human, 'update', update)
            assert changed['id'] == before['id'] and changed['revision'] > before['revision']
            assert all(new_name not in system(r) for r in continuation), 'paid continuation changed original role'
            replay, next_activation = ok('rename-replay', human, 'update', update)
            assert replay['id'] == changed['id'] and replay['revision'] == changed['revision']
            assert new_name in system(next_activation[0]), 'new activation missed active role'
            identity, _ = ok('role-identity', human, 'identity')
            assert new_name in json.dumps(identity) and before['id'] in json.dumps(identity)
            denied('same-id-different-body', human, 'update', {**update, 'display_name': 'conflicting body'})
            denied('stale-revision', human, 'update', {**update, 'request_id': str(uuid.uuid4())})
            denied('ordinary-write', other, 'update', update)
            after, _ = ok('role-after-denials', human, 'read')
            assert after['revision'] == changed['revision'] and after['display_name'] == new_name
            soul, _ = ok('soul-before', human, 'soul')
            assert soul['writable'], soul
            empty_body = {'request_id': str(uuid.uuid4()), 'expected_revision': soul['revision'], 'content': ''}
            empty, _ = ok('empty-soul-save', human, 'save_soul', empty_body)
            empty_read, _ = ok('empty-soul-read', human, 'soul')
            assert empty_read['content'] == '' and empty_read['active_revision'] == empty['revision']
            marker = 'SOUL_EXT038_' + uuid.uuid4().hex
            soul_body = {'request_id': str(uuid.uuid4()), 'expected_revision': empty_read['revision'], 'content': marker}
            saved, soul_continuation = ok('soul-save', human, 'save_soul', soul_body)
            assert all(marker not in system(r) for r in soul_continuation), 'paid continuation changed original SOUL'
            active, activated = ok('soul-active', human, 'soul')
            assert marker in system(activated[0]) and active['content'] == marker
            assert active['active_revision'] == saved['revision']
            filename = active['file_name']
            assert Path(filename).name == filename and Path(filename).suffix.lower() == '.md'
            soul_path = owner.data / filename
            assert soul_path.resolve().is_relative_to(owner.data.resolve())
            original = soul_path.read_bytes()
            assert original == marker.encode(), 'fault injection must only touch this fixture-created SOUL'
            failed_reload_id = str(uuid.uuid4())
            control = owner.work / 'control'
            (control / 'reload-arm').write_text(failed_reload_id)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending_reload = pool.submit(denied, 'reload-invalid-file', human, 'reload_soul', {'request_id': failed_reload_id})
                try:
                    wait(lambda: (control / 'reload-held').exists(), 'real original reload before dispatch')
                    held = json.loads((control / 'reload-held').read_text())
                    assert held['params']['body']['request_id'] == failed_reload_id
                    soul_path.write_bytes(b'\xff')
                    (control / 'reload-release').touch()
                    wait(lambda: (control / 'reload-response').exists(), 'actual Host reload response')
                    reload_response = json.loads((control / 'reload-response').read_text())
                    assert 'error' in reload_response, reload_response
                    # Restore only this fixture's original bytes before the
                    # unchanged error reaches the plugin and Main continues.
                    soul_path.write_bytes(original)
                    (control / 'reload-reply-release').touch()
                    failed_reload = pending_reload.result(timeout=20)
                finally:
                    soul_path.write_bytes(original)
                    (control / 'reload-release').touch()
                    (control / 'reload-reply-release').touch()
            reloaded, _ = ok('explicit-soul-reload', human, 'reload_soul', {'request_id': str(uuid.uuid4())})
            assert reloaded['active_revision'] == saved['revision']
        with owner.running():
            cold, _ = ok('cold-role', human, 'read')
            cold_soul, _ = ok('cold-soul', human, 'soul')
            assert cold['id'] == before['id'] and cold['display_name'] == new_name
            assert cold_soul['content'] == marker and cold_soul['active_revision'] == saved['revision']
            op('person', 'set-admin', person, 'false')
            denied('revoked-replay', human, 'update', update)
            denied('revoked-soul', human, 'soul')
        report = {'status': 'PASS', 'card_status': 'UNPUBLISHED_SHARED_ROLE_CANDIDATE',
                  'core': owner.evidence(), 'before': before, 'after': cold, 'active_soul': cold_soul,
                  'cases': cases, 'model_http_calls': len(models), 'automatic_retries': 0,
                  'soul_operations': {'save': saved, 'failed_reload': failed_reload,
                                      'raw_reload_response': reload_response,
                                      'reload_admission': 'not inferred from the generic Host error',
                                      'recovered_reload': reloaded},
                  'pending': ['immutable avatar asset/version and per-platform application bridge',
                              'historical owner data disposition',
                              'formal producer and consumer publication']}
        return 'shared-character.json', report
    finally:
        server.shutdown(); server.server_close()
        save('model.json', models); save('operator.json', operations); save('cases.json', cases)


def run(root, output):
    raise RuntimeError('EXT-038 full acceptance needs avatar/platform and full fault cases; use --preparation for the implemented shared role/SOUL candidate')
