"""Audit sealed Windows Main/processor evidence without replaying failed effects."""
import ast
import base64
import hashlib
import json
from pathlib import Path


def exercise(root, output):
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    home = Path('D:/yuki-extension-tests')
    runs = {'pdf': ('media-main-main-consumer-05', 'pdf'),
            'video': ('media-main-video-consumer-06', 'video'),
            'not-selected': ('media-main-faults-07', 'not-selected'),
            'video-no-vision': ('media-main-faults-07', 'video-no-vision'),
            'corrupt': ('media-main-faults-07', 'corrupt')}
    pin = json.loads((root / 'compat/core-038-main/source.lock.json').read_bytes())
    rows, manifests = [], {}
    for case, (run, relative) in runs.items():
        base = home / run; evidence = base / 'evidence'; folder = evidence / relative
        if run not in manifests:
            manifest = json.loads((evidence / 'manifest.json').read_bytes())
            for name, digest in manifest['files'].items(): assert sha(evidence / name) == digest, name
            assert sha(base.with_suffix('.zip')) == manifest['source_snapshot_sha256']
            manifests[run] = {'source_snapshot_sha256': manifest['source_snapshot_sha256'],
                              'evidence_zip_sha256': sha(base / 'evidence.zip'), 'container_status': manifest['status']}
        report = json.loads((folder / 'result.json').read_bytes())
        assert report['status'] == 'PASS' and report['source_commit'] == pin['source_commit']
        assert report['plugin_sha256'] == '2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c'
        assert report['consumer_sdk']['version'] == '1.0.0-alpha.4'
        assert report['host_sdk']['version'] == '1.0.0-alpha.13'
        assert report['host_sdk']['sha256'] == pin['rust_crate_sha256']
        assert report['host']['binary_sha256'] == pin['platforms']['windows-x86_64']['binary_sha256']
        assert report['host']['binary_sha256'] == sha(folder / 'work/yuki-core.exe')
        assert sha(folder / 'wire.jsonl') == report['wire_sha256']
        wire = [json.loads(line) for line in (folder / 'wire.jsonl').read_text().splitlines()]
        calls = [f['frame'] for f in wire if f['frame'].get('method') == 'media.process']
        expected = 0 if case in {'not-selected', 'video-no-vision'} else 1
        assert report['physical_processor_calls'] == len(calls) == expected
        models = json.loads((folder / 'model-http.json').read_bytes())
        assert len(models) == report['model_http_requests'] == (2 if case == 'not-selected' else 3)
        assert 'UNSELECTED' not in json.dumps(models[-1])
        if case in {'pdf', 'video'}:
            call = calls[0]
            reply = next(f['frame'] for f in wire if f['direction'] == 'from_plugin'
                         and f['frame'].get('id') == call['id'] and 'result' in f['frame'])
            paid = json.loads(next(m['content'] for m in models[-1]['messages'] if m.get('tool_call_id') == 'selected-original'))
            assert paid['id'] == call['params']['operation'] and paid['state'] == 'confirmed'
            original = reply['result']['data']
            projection = paid['result']['data']
            assert original == report['receipt']
            if case == 'pdf':
                assert projection == original
            else:
                assert {k: v for k, v in projection.items() if k != 'images'} == {k: v for k, v in original.items() if k != 'images'}
                assert len(projection['images']) == len(original['images']) == 2
                for ordinal, (shown, immutable) in enumerate(zip(projection['images'], original['images'])):
                    assert shown == {'artifact_id': immutable['artifact_id'], 'ordinal': ordinal, 'state': 'ready'}
            assert all(f['frame']['params']['handle'] == call['params']['handle'] for f in wire if f['frame'].get('method') == 'media.open')
            frames = []
            for m in models[-1]['messages']:
                if isinstance(m.get('content'), list):
                    for b in m['content']:
                        if b.get('type') == 'image_url':
                            url = b['image_url']['url']; assert url.startswith('data:image/')
                            frames.append(hashlib.sha256(base64.b64decode(url.split(',', 1)[1], validate=True)).hexdigest())
            if case == 'pdf':
                assert not frames and '[page 1]' in report['receipt']['text'] and '[page 2]' in report['receipt']['text']
            else:
                assert [x['seconds'] for x in report['receipt']['frames']] == [0, 5]
                assert frames == report['model_frame_sha256'] == [x['sha256'] for x in report['receipt']['frames']]
                publishes = [f['frame'] for f in wire if f['frame'].get('method') == 'media.publish']
                assert len(publishes) == 2
                for call, image, digest in zip(publishes, report['receipt']['images'], frames):
                    answer = next(f['frame']['result'] for f in wire if f['direction'] == 'from_host' and f['frame'].get('id') == call['id'] and 'result' in f['frame'])
                    assert call['params']['digest'] == answer['version'] == image['version'] == digest and answer['artifact_id'] == image['artifact_id']
        rows.append({'case': case, 'evidence': str(folder), 'wire_sha256': report['wire_sha256'],
                     'physical_processor_calls': len(calls), 'model_fixture_http': len(models),
                     'result_sha256': sha(folder / 'result.json')})
    failed = home / 'media-main-faults-07/evidence'
    failure = (failed / 'failure.txt').read_text()
    assert 'FOREIGN KEY constraint failed' in failure and '787' in failure
    assert (failed / 'forget/work/control/held').exists()
    wire = [json.loads(l) for l in (failed / 'forget/wire.jsonl').read_text().splitlines()]
    assert sum(f['frame'].get('method') == 'media.process' for f in wire) == 1
    assert any(f['frame'].get('method') == 'media.open' and f['frame']['params']['offset'] > 0 for f in wire)
    for name in ['tests/cases/EXT-031.py', 'tests/peers/media_main.py', 'tests/peers/media_main_audit.py', 'tests/peers/media_stdio.py']:
        ast.parse((root / name).read_text(encoding='utf-8'))
    from units import load_catalog, validate_unit, select_units
    units = load_catalog(root)
    for unit in units.values(): validate_unit(root, unit)
    selected = select_units(root, ['catalog/media.json', 'tests/peers/media_main.py'])
    assert selected == ['media']
    return 'main-witness-audit.json', {'status': 'PASS', 'card_status': 'BLOCKED_MAIN_ERASURE_NATIVE_GATEWAY_AND_PUBLICATION',
        'phase': 'audit_sealed_native_evidence', 'native_cases': rows, 'source_containers': manifests,
        'consumer_rebuilt': False, 'consumer_binary_sha256': '2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c',
        'producer_source': pin['source_commit'], 'producer_published': False,
        'main_erasure': {'status': 'BLOCKED', 'public_method': 'operator privacy erase',
                         'error': 'SQLite 787 FOREIGN KEY constraint failed', 'successful_erase_receipt': False,
                         'original_failure_sha256': sha(failed / 'failure.txt'), 'retry_attempted': False},
        'release_boundaries': sorted(units), 'selected_units': selected,
        'test_sources': {n: sha(root / n) for n in ['tests/cases/EXT-031.py', 'tests/peers/media_main.py', 'tests/peers/media_main_audit.py', 'tests/peers/media_stdio.py']}}
