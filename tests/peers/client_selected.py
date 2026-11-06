"""Actual Rust Client/Host with a controlled model; public HTTP/operators only."""
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
import shutil
import threading
import time
from urllib.parse import urlencode
import uuid

from personal_preview import Owner, http
from client_sse import Stream


def exercise(root, output):
    probe_social = os.environ.get('YUKI_CLIENT_SOCIAL_PROBE') == '1'
    transcript, cases, models, operators, secrets, streams, responses, deliveries = [], [], [], [], [], [], [], []
    marker, reply = 'client-stream-' + uuid.uuid4().hex, 'committed-social-' + uuid.uuid4().hex
    model_entered, release_model = threading.Event(), threading.Event()
    stage = 0
    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    def mark(name, **evidence):
        cases.append({'name': name, **evidence}); save('cases.json', cases)
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            nonlocal stage
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/binding':
                deliveries.append(body); save('binding-http.json', deliveries)
                data = json.dumps({'accepted': body['operation'], 'sequence': len(deliveries)}).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
                return
            models.append(body); save('model-http.json', models)
            use_send = probe_social and stage < 2 and marker in json.dumps(body, ensure_ascii=False)
            message = {'role': 'assistant', 'content': ''}
            if use_send:
                name, arguments = ('task_control', {'action': 'accept', 'goal': 'publish one original local Social reply'}) if stage == 0 else ('send', {'text': reply})
                stage += 1; model_entered.set()
                message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'original-social-' + str(len(models)),
                    'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
            answer = {'id': 'fixture-' + str(len(models)), 'choices': [{'index': 0,
                'message': message, 'finish_reason': 'tool_calls' if use_send else 'stop'}],
                'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
            responses.append(answer); save('model-responses.json', responses)
            data = json.dumps(answer).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    model = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threading.Thread(target=model.serve_forever, daemon=True).start()
    source_paths = [p for p in (root / 'plugins/client').rglob('*') if p.is_file() and not p.name.startswith('._')]
    source_paths += [p for p in (root / 'compat/core-033-client').iterdir() if p.is_file() and not p.name.startswith('._')]
    source_paths += [root / p for p in ['catalog/client.json', 'tests/cases/EXT-015.py',
        'tests/peers/client_selected.py', 'tests/peers/client_sse.py', 'ci/personal_preview.py',
        'ci/package.py', 'ci/host_preview.py', 'ci/handshake_cargo.py', 'ci/check.py', 'ci/units.py', 'ci/windows.py']]
    save('source-bindings.json', {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths})
    from units import load_catalog, validate_unit, select_units
    units = load_catalog(root)
    for unit in units.values(): validate_unit(root, unit)
    selected_units = select_units(root, ['ci/windows.py'])
    assert set(selected_units) == set(units)
    save('release-boundaries.json', {'status': 'PASS', 'validated': sorted(units), 'selected': selected_units})
    owner = Owner(root, output, 'client', [], contract='core-033-client', command_timeout=30)
    shutil.copy2(owner.packages / 'package-manifest.json', output / 'build.json')
    config = owner.data / 'yuki.toml'
    text = config.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"')
    text = text.replace('\n[[plugins]]', '\n[main]\nendpoint=' + json.dumps(f'http://127.0.0.1:{model.server_port}/model') +
        '\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=4000000\nmax_output=512\n\n[[plugins]]')
    config.write_text(text, encoding='utf-8'); save('host-config.json', {'toml': text})
    def op(*args):
        result = owner.cli('operator', *map(str, args))
        operators.append({'args': args, 'result': result}); save('operator.json', operators)
        return result
    def call(method, path, expected, body=None, token=None, headers=None):
        status, result = http(owner.edge, method, path, body, token, headers)
        record = {'method': method, 'path': path, 'headers': headers or {}, 'status': status}
        if path != '/client/v1/pair': record.update(body=body, response=result)
        transcript.append(record); save('http.json', transcript)
        assert status in (expected if isinstance(expected, tuple) else (expected,)), (record, expected)
        return result.get('data', result)
    def pair(person, label):
        code = owner.issue(person, 'chat'); secrets.append(code)
        result = call('POST', '/client/v1/pair', 200, {'code': code, 'device_label': label})
        secrets.append(result['token'])
        call('POST', '/client/v1/pair', 401, {'code': code, 'device_label': label})
        return result
    def send(device, request, content, headers=None, **fields):
        return call('POST', '/client/v1/messages', 200,
                    {'request_id': request, 'text': content, **fields}, device['token'], headers)
    def receipt(device, request, headers=None):
        return call('GET', '/client/v1/requests/' + request, 200, token=device['token'], headers=headers)
    def page(device, conversation, headers=None, after=None):
        path = '/client/v1/conversations/' + conversation + '/events'
        if after is not None: path += '?' + urlencode({'after': after})
        return call('GET', path, 200, token=device['token'], headers=headers)
    def upload(device, data, request, filename):
        query = {'request_id': request, 'sha256': hashlib.sha256(data).hexdigest(),
                 'size': len(data), 'filename': filename, 'kind': 'file'}
        conn = HTTPConnection(owner.edge, timeout=20)
        try:
            conn.request('POST', '/client/v1/uploads?' + urlencode(query), data,
                {'Authorization': 'Bearer ' + device['token'], 'Content-Type': 'application/octet-stream'})
            response = conn.getresponse(); value = json.loads(response.read())
            transcript.append({'method': 'POST', 'path': '/client/v1/uploads', 'query': query,
                               'status': response.status, 'response': value}); save('http.json', transcript)
            assert response.status == 200, value
            return value['data']
        finally: conn.close()
    def wait(predicate, label):
        until = time.monotonic() + 20
        while time.monotonic() < until:
            value = predicate()
            if value: return value
            time.sleep(.05)
        raise AssertionError(label)
    try:
        with owner.running():
            people = [str(uuid.uuid4()) for _ in range(3)]
            for person in people: op('person', 'create', person)
            phone, desktop, other, outsider = [pair(p, label) for p, label in
                [(people[0], 'phone'), (people[0], 'desktop'), (people[1], 'B'), (people[2], 'C')]]
            a, a2, b, c = [call('GET', '/client/v1/me', 200, token=d['token']) for d in [phone, desktop, other, outsider]]
            assert a['binding_id'] == a2['binding_id'] != b['binding_id']
            assert a['request_scope'] == people[0] and a['request_conversation_id'] is None
            key = str(uuid.uuid4()); first = send(phone, key, 'original A')
            replay = send(desktop, key, 'original A')
            assert first['event_id'] == replay['event_id'] and replay['replay'] is True
            saved_receipt = receipt(desktop, key)
            conflict = call('POST', '/client/v1/messages', 409,
                {'request_id': key, 'text': 'different A'}, desktop['token'])
            assert not receipt(other, key)['found']
            assert sum(e['event_id'] == first['event_id'] for e in page(phone, a['conversation_id'])['items']) == 1
            mark('same-person-original-uuid', request_id=key, first=first, replay=replay, conflict=conflict)
            selected_b = {'X-Yuki-Entry': b['binding_id']}
            call('GET', '/client/v1/me', 401, token=phone['token'], headers=selected_b)
            rejected = str(uuid.uuid4())
            call('POST', '/client/v1/messages', 401, {'request_id': rejected, 'text': 'foreign'}, phone['token'], selected_b)
            assert not receipt(phone, rejected)['found'] and not receipt(other, rejected)['found']
            foreign = send(other, key, 'original B')
            merged = op('person', 'merge', people[0], people[1])
            assert merged['original'] == people[0] and merged['root'] == people[1]
            default = call('GET', '/client/v1/me', 200, token=phone['token'])
            selected = call('GET', '/client/v1/me', 200, token=phone['token'], headers=selected_b)
            assert default['source_person_id'] == default['request_person_id'] == people[0]
            assert selected['source_person_id'] == people[0] and selected['person_id'] == selected['request_person_id'] == people[1]
            assert selected['request_conversation_id'] is None and selected['request_scope'] == people[1]
            assert receipt(phone, key)['event_id'] == first['event_id']
            assert receipt(phone, key, selected_b)['event_id'] == foreign['event_id']
            selected_replay = send(phone, key, 'original B', selected_b)
            assert selected_replay['replay'] and selected_replay['event_id'] == foreign['event_id']
            mark('merged-selected-entry', original=default, selected=selected, original_receipt=saved_receipt,
                 selected_receipt=receipt(phone, key, selected_b), replay=selected_replay)
            for headers, expected in [({'X-Yuki-Entry': c['binding_id']}, 401),
                                      ({'X-Yuki-Conversation': a['conversation_id']}, 404),
                                      ({'X-Yuki-Entry': b['binding_id'], 'X-Yuki-Conversation': a['conversation_id']}, 404)]:
                call('GET', '/client/v1/me', expected, token=phone['token'], headers=headers)
            conn = HTTPConnection(owner.edge, timeout=12)
            conn.putrequest('GET', '/client/v1/me'); conn.putheader('Authorization', 'Bearer ' + phone['token'])
            conn.putheader('X-Yuki-Entry', a['binding_id']); conn.putheader('X-Yuki-Entry', b['binding_id'])
            conn.endheaders(); response = conn.getresponse(); assert response.status == 400; response.read(); conn.close()
            mark('invalid-and-duplicate-selection', duplicate_status=400)
            actor = op('account', 'open', 'acp', 'selected-client', 'actor', 1, '--person', people[1], '--start', 1)
            bot = op('account', 'open', 'acp', 'selected-client', 'bot', 1, '--start', 1)
            acp_views = []
            for topic in ['original-thread-one', 'original-thread-two']:
                prior = call('GET', '/client/v1/home', 200, token=phone['token'])
                op('entry', 'private', actor['assignment'], bot['assignment'], '--topic', topic)
                op('ingress', 'record', json.dumps({'source': topic, 'account': actor['account'],
                    'bot_stage': bot['assignment'], 'reply_bot': 'bot', 'kind': 'message', 'topic': topic,
                    'occurred': 100, 'observed': 100, 'segments': [{'type': 'text', 'text': topic}]}))
                home = call('GET', '/client/v1/home', 200, token=phone['token'])
                previous = {e['conversation_id'] for e in prior['entries']}
                new = [e for e in home['entries'] if e['binding_id'] == actor['assignment'] and e['conversation_id'] not in previous]
                assert len(new) == 1, (prior, home)
                entry = new[0]['conversation_id']
                headers = {'X-Yuki-Entry': actor['assignment'], 'X-Yuki-Conversation': entry}
                try:
                    view = call('GET', '/client/v1/me', 200, token=phone['token'], headers=headers)
                except AssertionError:
                    if transcript[-1]['status'] != 404: raise
                    save('acp-diagnostic.json', {'status': 'BLOCKED', 'required_status': 200,
                        'actual_status': 404, 'home': home, 'original_headers': headers,
                        'public_setup': operators[-4:], 'consumer_accepted': False,
                        'need': 'public ACP session/presence creation sequence; no DB fixture'})
                    break
                assert view['platform'] == 'acp' and view['request_scope'] == view['request_conversation_id'] == entry
                assert view['source_person_id'] == people[0] and view['request_person_id'] == people[1]
                assert not receipt(phone, key, headers)['found']
                acp_views.append(view)
            if len(acp_views) == 2:
                assert acp_views[0]['request_scope'] != acp_views[1]['request_scope']
                mark('existing-acp-conversation-selection', original_scopes=acp_views, app_receipt_invisible=True)
            files = [upload(phone, data, str(uuid.uuid4()), name) for data, name in
                     [(b'first immutable bytes', 'first.txt'), (b'second immutable bytes', 'second.txt')]]
            attachment_key = str(uuid.uuid4()); ordered = [f['media_id'] for f in files]
            attached = send(phone, attachment_key, 'ordered attachments', attachments=ordered)
            attached_replay = send(desktop, attachment_key, 'ordered attachments', attachments=ordered)
            assert attached['event_id'] == attached_replay['event_id'] and attached_replay['replay']
            call('POST', '/client/v1/messages', 409, {'request_id': attachment_key,
                 'text': 'ordered attachments', 'attachments': ordered[::-1]}, desktop['token'])
            mark('ordered-attachment-conflict', uploads=files, first=attached, replay=attached_replay)
            stream = Stream(owner.edge, phone['token']); streams.append(stream)
            initial = stream.wait(lambda f: f.get('event') == 'sync', 'initial sync')
            save('sse.json', stream.frames)
            before = page(phone, a['conversation_id'])
            assert not any(e.get('text') == reply for e in before['items'])
            incoming = send(phone, str(uuid.uuid4()), marker)
            if probe_social:
                assert model_entered.wait(12), 'real Main HTTP not reached'
                try:
                    committed = wait(lambda: next((e for e in page(phone, a['conversation_id'])['items'] if e.get('text') == reply), None), 'Social event not committed')
                except AssertionError:
                    accepted = [json.loads(m['content']) for r in models for m in r['messages']
                                if m['role'] == 'tool' and 'work_id' in m.get('content', '')]
                    if accepted:
                        execution = accepted[-1].get('namespace')
                        if execution: op('main', 'inspect', execution)
                    raise
            else:
                committed = next(e for e in page(phone, a['conversation_id'])['items'] if e['event_id'] == incoming['event_id'])
                assert committed['direction'] == 'inbound' and committed['text'] == marker
            def has_cursor(value):
                if isinstance(value, dict):
                    if value.get('conversation_id') == a['conversation_id'] and value.get('latest_event_id') == committed['event_id']:
                        return True
                    return any(has_cursor(v) for v in value.values())
                return isinstance(value, list) and any(has_cursor(v) for v in value)
            hint = stream.wait(lambda f: has_cursor(f['data']), 'committed cursor')
            if probe_social: assert committed['event_id'] > incoming['event_id']
            reconnect = Stream(owner.edge, phone['token'], {'Last-Event-ID': hint.get('id', '')}); streams.append(reconnect)
            fresh = reconnect.wait(lambda f: f.get('event') == 'sync', 'reconnect sync')
            assert fresh.get('id') == initial.get('id'), 'SSE sequence is per connection'
            resumed = page(phone, a['conversation_id'], after=incoming['event_id'] - 1)
            assert any(e['event_id'] == committed['event_id'] for e in resumed['items'])
            mark('committed-social-sse-and-resync' if probe_social else 'committed-inbound-sse-and-resync', initial=initial, committed=committed, hint=hint,
                 reconnect=fresh, resumed=resumed, human_read_evidence=False)
            for _ in range(2):
                extra = Stream(owner.edge, phone['token']); streams.append(extra)
                extra.wait(lambda f: f.get('event') == 'sync', 'independent bounded stream')
            call('GET', '/client/v1/stream', 503, token=phone['token'])
            call('GET', '/client/v1/me', 200, token=phone['token'])
            mark('sse-capacity-preserves-ordinary-requests', active_streams=4, overflow=503, me=200)
            save('sse.json', [s.frames for s in streams])
            op('personal', 'revoke', phone['device_id'])
            assert all(s.ended.wait(12) for s in streams), 'revoked stream remained open'
            call('GET', '/client/v1/me', 401, token=phone['token'])
            call('GET', '/client/v1/me', 200, token=desktop['token'])
            mark('revoke-device-closes-original-streams', streams_ended=True)
            binding = op('control', 'read', 'binding.get', json.dumps({'id': a['binding_id']}))
            disabled = op('control', 'write', 'binding.disable', json.dumps({'id': a['binding_id'],
                'request_id': str(uuid.uuid4()), 'expected_revision': binding['revision']}))
            paused = call('GET', '/client/v1/me', 200, token=desktop['token'])
            call('GET', '/client/v1/me', 200, token=desktop['token'], headers=selected_b)
            new_key = str(uuid.uuid4())
            denied = call('POST', '/client/v1/messages', (401, 403, 409, 503),
                          {'request_id': new_key, 'text': 'paused original entry'}, desktop['token'])
            assert not receipt(desktop, new_key)['found']
            assert receipt(desktop, key)['event_id'] == first['event_id']
            binding = op('control', 'read', 'binding.get', json.dumps({'id': a['binding_id']}))
            enabled = op('control', 'write', 'binding.enable', json.dumps({'id': a['binding_id'],
                'request_id': str(uuid.uuid4()), 'expected_revision': binding['revision']}))
            reopened = call('GET', '/client/v1/me', 200, token=desktop['token'])
            assert reopened['binding_id'] == a['binding_id'] and reopened['request_person_id'] == people[0]
            mark('paused-entry-is-not-device-revocation', disabled=disabled, enabled=enabled,
                 readable=paused, new_write_denied=denied, original_receipt_retained=True)
        with owner.running():
            assert receipt(desktop, key) == saved_receipt
            assert receipt(desktop, key, selected_b)['event_id'] == foreign['event_id']
            mark('cold-original-and-selected-receipts', original=saved_receipt, selected=foreign)
        for path in [owner.trace, output / 'host.txt', output / 'http.json', output / 'operator.json']:
            data = path.read_text(encoding='utf-8')
            assert all(secret not in data for secret in secrets), 'credential leaked to evidence'
        result = {'status': 'PASS', 'card_status': 'UNPUBLISHED_SELECTED_CLIENT_CANDIDATE', **owner.evidence(),
                  'cases': {'H24': cases}, 'model_http_requests': len(models),
                  'unwitnessed': ['ACP conversation and legacy NULL',
                                  'agent_target and operation conflict', 'local Social outbound', 'H27 final overflow',
                                  'H28 download/forget race', 'published tuple']}
        save('personal-entries.json', result)
        return 'original-uuid-entry.json', result
    finally:
        release_model.set()
        for stream in streams: stream.close()
        save('sse.json', [s.frames for s in streams])
        model.shutdown(); model.server_close()
