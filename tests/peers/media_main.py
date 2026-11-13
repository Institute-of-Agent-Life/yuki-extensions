"""Run the original Rust media binary in the selected Main path of a fixed Host."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

from personal_preview import Owner


def exercise(root, output, *, native_package=None, codec_dir=None, contract='core-038-main', ffmpeg=None):
    if native_package is None:
        native_package, codec_dir, build, source = original_inputs(root)
        rebuilt = False
    else:
        build = json.loads((native_package / 'package-manifest.json').read_bytes())
        source = {'package_manifest_sha256': hashlib.sha256((native_package / 'package-manifest.json').read_bytes()).hexdigest()}
        rebuilt = True
    if codec_dir is None:
        raise ValueError('isolated decoder directory required')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    name = 'yuki-media.exe' if os.name == 'nt' else 'yuki-media'
    assert all(c['exit_code'] == 0 for c in build['commands'])
    assert all(digest(native_package / member) == expected for member, expected in build['artifacts'].items())
    assert name in build['artifacts']
    python = codec_dir / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    codec = json.loads((native_package / 'packaging/codecs.lock').read_bytes())['ffmpeg']['platforms']
    if ffmpeg is not None:
        codec_digest = digest(ffmpeg)
        assert any(codec_digest == entry['binary_sha256'] for entry in codec.values())
    if ffmpeg is None:
        ffmpeg = codec_dir / 'ffmpeg.exe'
        codec_digest = digest(ffmpeg)
        assert codec_digest == codec['windows-x86_64']['binary_sha256']
    def save(path, value): path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    save(output / 'consumer.lock.json', {**source, 'consumer_binary_sha256': build['artifacts'][name],
        'consumer_sdk': json.loads((root / build['source']['sdk_contract']).read_bytes())['sdk'],
        'consumer_crate_sha256': digest(root / 'compat/core-038/yuki-plugin-sdk-1.0.0-alpha.4.crate'),
        'ffmpeg_sha256': codec_digest, 'python_sha256': digest(python)})
    def frozen_package(_root, unit, destination):
        assert unit == 'media'
        shutil.copytree(native_package, destination, ignore=shutil.ignore_patterns('._*'))
        return build
    return replay(root, output, codec_dir, ffmpeg, python, frozen_package, save, digest, contract, rebuilt)


def original_inputs(root):
    baseline = Path(os.environ['YUKI_MEDIA_BASELINE_DIR'])
    original = baseline / 'src/artifacts/EXT-031/candidate-03'
    source = baseline / 'src/plugins/media'
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(baseline / 'source.zip') == 'fd7fb275dae5aa500f4249a077b858bbbdfa5982643b97aaae4a5e918fc8cd90'
    binary_sha = '2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c'
    assert digest(original / 'packages/yuki-media.exe') == binary_sha
    paths = [p.relative_to(root / 'plugins/media') for p in (root / 'plugins/media').rglob('*')
             if p.is_file() and not p.name.startswith('._') and p.name != 'README.md']
    for name in paths: assert digest(source / name) == digest(root / 'plugins/media' / name), str(name)
    build = json.loads((original / 'packages/package-manifest.json').read_bytes())
    assert build['artifacts']['yuki-media.exe'] == binary_sha
    return original / 'packages', original / 'work/codecs', build, {
        'consumer_snapshot_sha256': digest(baseline / 'source.zip'),
        'build_manifest_sha256': digest(original / 'packages/package-manifest.json'),
        'source_files': {p.as_posix(): digest(source / p) for p in paths},
    }


def replay(root, output, codec_dir, ffmpeg, python, frozen_package, save, digest, contract, rebuilt):
    results = []
    default = 'pdf,video,not-selected,video-no-vision,forget,corrupt' if rebuilt else 'pdf,video'
    kinds = os.environ.get('YUKI_MEDIA_MAIN_CASES', default).split(',')
    assert set(kinds) <= {'pdf', 'video', 'not-selected', 'video-no-vision', 'forget', 'corrupt'}
    for kind in kinds:
        out = output / kind; out.mkdir()
        models, responses, operators = [], [], []
        selected = {}; accepted = threading.Event()
        class Model(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                models.append(request); save(out / 'model-http.json', models)
                assert accepted.wait(10), 'ingress commit result missing'
                message = {'role': 'assistant', 'content': ''}
                if len(models) == 1:
                    message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'original-capability',
                        'type': 'function', 'function': {'name': 'get_my_capabilities', 'arguments': '{}'}}]}
                elif len(models) == 2:
                    receipts = [json.loads(m['content']) for m in request['messages'] if m['role'] == 'tool']
                    execution = receipts[-1]['namespace']
                    for slot, filename in [(0, 'unselected.pdf'), (1, selected_file)]:
                        cached = op('media', 'cache-file', execution, person, selected['event'], slot,
                                    bot['assignment'], filename, filename)
                        assert cached['digest'] == digest(transfer / filename)
                    if kind != 'not-selected':
                        message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'selected-original',
                            'type': 'function', 'function': {'name': 'inspect_conversation_attachment',
                            'arguments': json.dumps({'event_id': selected['event'], 'attachment_index': 1,
                                                     'question': 'Read the explicitly selected original attachment.'})}}]}
                result = {'id': 'fixture-' + str(len(models)), 'choices': [{'index': 0, 'message': message,
                    'finish_reason': 'tool_calls' if 'tool_calls' in message else 'stop'}],
                    'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
                responses.append(result); save(out / 'model-responses.json', responses)
                data = json.dumps(result).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        model = ThreadingHTTPServer(('127.0.0.1', 0), Model)
        threading.Thread(target=model.serve_forever, daemon=True).start()
        temporary = out / 'temporary'; temporary.mkdir()
        owner = Owner(root, out, 'media', ['media.process', 'media.open', 'media.publish', 'forget.owner'],
            contract=contract, command_timeout=40, package_builder=frozen_package,
            relay='media_stdio.py' if kind == 'forget' else None,
            environment={'YUKI_MEDIA_PYTHON': str(python), 'YUKI_MEDIA_FFMPEG': str(ffmpeg),
                         'YUKI_MEDIA_TEMP': str(temporary)})
        def op(*args):
            response = owner.command('operator', *map(str, args))
            if response.returncode:
                operators.append({'args': args, 'exit_code': response.returncode, 'stderr': response.stderr})
                save(out / 'operator.json', operators)
                raise RuntimeError('public operator refused: ' + response.stderr[:300])
            value = json.loads(response.stdout) if response.stdout.strip() else None
            operators.append({'args': args, 'result': value}); save(out / 'operator.json', operators)
            return value
        try:
            config = owner.data / 'yuki.toml'
            transfer = out / 'gateway-transfer'; transfer.mkdir()
            for filename in ['unselected.pdf', 'good.pdf', 'video.mp4', 'corrupt.pdf']:
                shutil.copy2(codec_dir / filename, transfer / filename)
            inputs = owner.data / 'media-inputs'; inputs.mkdir(exist_ok=True)
            for filename in ['unselected.pdf', 'good.pdf', 'video.mp4', 'corrupt.pdf']:
                shutil.copy2(transfer / filename, inputs / filename)
            selected_file = 'video.mp4' if kind.startswith('video') else 'corrupt.pdf' if kind == 'corrupt' else 'good.pdf'
            text = config.read_text().replace('mode = "hybrid"', 'mode = "lexical-only"')
            text = text.replace('\n[[plugins]]', '\n[main]\nendpoint=' + json.dumps(f'http://127.0.0.1:{model.server_port}/model') +
                '\nmodel="fixture"\nname="Yuki"\nmax_output=512\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=1200000\nmerge_ms=1\nattachment_processor="media"\nvision_input=' + str(kind == 'video').lower() +
                '\n[media]\ngateway_transfer_directory=' + json.dumps(str(transfer)) + '\n\n[[plugins]]')
            config.write_text(text, encoding='utf-8'); save(out / 'host-config.json', {'toml': text})
            with owner.running():
                person = str(uuid.uuid4()); op('person', 'create', person)
                human = op('account', 'open', 'qq', 'media-main', '200', 1, '--person', person, '--start', 1)
                bot = op('account', 'open', 'qq', 'media-main', '100', 1, '--start', 1)
                frame = {'source': 'main-' + kind, 'account': human['account'], 'bot_stage': bot['assignment'],
                    'kind': 'message', 'reply_bot': '100', 'occurred': int(time.time() * 1000), 'observed': int(time.time() * 1000),
                    'segments': [{'type': 'media', 'kind': 'file', 'reference': 'unselected.pdf'},
                                 {'type': 'media', 'kind': 'video' if kind.startswith('video') else 'file', 'reference': selected_file}]}
                if kind == 'forget': (owner.work / 'control/erase-next').touch()
                selected.update(op('ingress', 'record', json.dumps(frame), '--accept')); accepted.set()
                if kind == 'forget':
                    deadline = time.monotonic() + 15
                    while not (owner.work / 'control/held').exists() and time.monotonic() < deadline: time.sleep(.02)
                    assert (owner.work / 'control/held').exists(), (kind, 'second original chunk not held')
                    try:
                        op('privacy', 'erase', 'main-selected-forget', person, json.dumps([selected['event']]))
                    finally:
                        (owner.work / 'control/release').touch()
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        raw = owner.trace.read_text()
                        if 'forget.request' in raw and not op('privacy', 'pending', 'media')['obligations']: break
                        time.sleep(.05)
                    assert not op('privacy', 'pending', 'media')['obligations']
                deadline = time.monotonic() + 30
                expected_models = 2 if kind in {'not-selected', 'forget'} else 3
                while len(models) < expected_models and time.monotonic() < deadline: time.sleep(.05)
                assert len(models) == expected_models if kind != 'forget' else len(models) in {2, 3}, (kind, len(models))
                time.sleep(.15)
            def complete_trace():
                records = []
                for line in owner.trace.read_text().splitlines():
                    try: records.append(json.loads(line))
                    except json.JSONDecodeError: break
                calls = [f['frame'] for f in records if f['frame'].get('method') == 'media.process']
                if kind in {'not-selected', 'video-no-vision', 'forget'}:
                    return records
                if len(calls) == 1 and any(f['direction'] == 'from_plugin' and
                    f['frame'].get('id') == calls[0]['id'] and 'result' in f['frame'] for f in records):
                    return records
                return None
            deadline = time.monotonic() + 10
            frames = complete_trace()
            while frames is None and time.monotonic() < deadline:
                time.sleep(.02); frames = complete_trace()
            assert frames is not None, (kind, 'original processor transcript not complete')
            process = [f['frame'] for f in frames if f['frame'].get('method') == 'media.process']
            expected_calls = 0 if kind in {'not-selected', 'video-no-vision'} else 1
            assert len(process) == expected_calls, (kind, process)
            call = process[0] if process else None
            replies = []
            if call:
                assert call['params']['arguments']['media'] == {'event': selected['event'], 'slot': 1}
                replies = [f['frame'] for f in frames if f['direction'] == 'from_plugin'
                           and f['frame'].get('id') == call['id'] and 'result' in f['frame']]
            data = replies[0]['result'].get('data') if replies else None
            if kind in {'pdf', 'video'}:
                assert len(replies) == 1 and replies[0]['result']['ok'] is True, (kind, replies)
                assert data['version'] == digest(transfer / selected_file)
                receipt = json.loads(next(m['content'] for m in models[-1]['messages'] if m.get('tool_call_id') == 'selected-original'))
                assert receipt['id'] == call['params']['operation'] and receipt['state'] == 'confirmed'
                projected = receipt['result']['data']
                if kind == 'pdf':
                    assert projected == data
                else:
                    assert {k: v for k, v in projected.items() if k != 'images'} == {k: v for k, v in data.items() if k != 'images'}
                    assert [x['artifact_id'] for x in projected['images']] == [x['artifact_id'] for x in data['images']]
            elif kind == 'corrupt':
                assert len(replies) == 1 and replies[0]['result']['ok'] is False, replies
            elif kind == 'forget':
                assert any(f['frame'].get('method') == 'forget.request' and f['frame']['params']['key'] == 'main-selected-forget' for f in frames)
                assert not list(temporary.iterdir())
                assert all('Selected page one' not in json.dumps(m) and 'Selected page two' not in json.dumps(m) for m in models)
            assert 'UNSELECTED' not in json.dumps(models[-1], ensure_ascii=False)
            image_sha = []
            for message in models[-1]['messages']:
                content = message.get('content')
                if isinstance(content, list):
                    for block in content:
                        if block.get('type') == 'image_url':
                            url = block['image_url']['url']; assert url.startswith('data:image/')
                            image_sha.append(hashlib.sha256(base64.b64decode(url.split(',', 1)[1], validate=True)).hexdigest())
            if kind == 'pdf':
                assert 'Selected page one' in json.dumps(models[-1]) and 'Selected page two' in json.dumps(models[-1])
                assert '[page 1]' in data['text'] and '[page 2]' in data['text'] and not image_sha
            elif kind == 'video':
                assert [f['seconds'] for f in data['frames']] == [0, 5]
                assert image_sha == [f['sha256'] for f in data['frames']] and len(image_sha) == 2
            else:
                assert not image_sha
            consumer = owner.evidence()
            consumer['host_sdk'] = consumer.pop('sdk')
            consumer['consumer_sdk'] = {'version': '1.0.0-alpha.4', 'sha256': digest(root / 'compat/core-038/yuki-plugin-sdk-1.0.0-alpha.4.crate')}
            results.append({'case': kind, 'status': 'PASS', **consumer, 'model_http_requests': len(models),
                'physical_processor_calls': len(process), 'source': call['params']['arguments']['media'] if call else None,
                    'operation': call['params']['operation'] if call else None, 'receipt': data, 'model_frame_sha256': image_sha,
                'trusted_cache_setup': 'public execution namespace from original capability receipt; protected operator cache-file',
                'selection_model_request_range': None if kind == 'not-selected' else [1, len(models)],
                'continuation_request_sha256': hashlib.sha256(json.dumps(models[-1], sort_keys=True).encode()).hexdigest()})
            save(out / 'result.json', results[-1])
        finally:
            accepted.set(); model.shutdown(); model.server_close()
    pending = ['gateway native inbound consumer', 'published tuple']
    if 'forget' not in kinds:
        pending.append('late forget on this tuple')
    return 'main-selected-consumer.json', {'status': 'PASS', 'card_status': 'UNPUBLISHED_MAIN_MEDIA_CANDIDATE',
        'cases': results, 'consumer_rebuilt': rebuilt, 'backend_rewritten': False,
        'unwitnessed': pending}
