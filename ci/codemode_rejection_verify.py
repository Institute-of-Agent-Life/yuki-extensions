"""Verify a refusal diagnosis against raw native transcripts, not a full-card pass."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def verify_transfer(path):
    manifest = read(path / 'manifest.json')
    for name, sha in manifest['files'].items():
        assert digest(path / name) == sha, name
    archive = path.parent / 'evidence.zip'
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert len(names) == len(set(names)) and bundle.testzip() is None
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts
                   and '\\' not in n for n in names)
        assert set(names) == set(manifest['files']) | {'manifest.json'}
        for name, sha in manifest['files'].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == sha
    return {'manifest_sha256': digest(path / 'manifest.json'),
            'source_snapshot_sha256': manifest['source_snapshot_sha256'],
            'evidence_zip_sha256': digest(archive)}


def exchanges(path):
    frames = [read_line(line) for line in (path / 'wire.jsonl').read_text(encoding='utf-8').splitlines()]
    result = []
    for index, item in enumerate(frames):
        frame = item['frame']
        if item['direction'] != 'from_plugin' or frame.get('method') not in {'tool.invoke', 'tool.resume'}:
            continue
        replies = [f['frame'] for f in frames[index + 1:] if f['direction'] == 'from_host'
                   and f['frame'].get('id') == frame['id'] and 'method' not in f['frame']]
        assert len(replies) == 1, (frame['method'], frame['id'])
        result.append({'request': frame, 'reply': replies[0]})
    return result


def read_line(line):
    return json.loads(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('run this evidence check on HJW Windows')
    first, control = read(args.first / 'intake.json'), read(args.control / 'intake.json')
    transfers = [verify_transfer(args.first), verify_transfer(args.control)]
    pin = read(Path(__file__).resolve().parents[1] / 'compat/core-015-isolation/source.lock.json')
    direct = first['cases']['direct']
    code = first['cases']['code']
    positive = control['cases']['code-control']
    assert first['status'] == control['status'] == 'BLOCKED'
    assert first['source_commit'] == control['source_commit'] == pin['source_commit']
    assert direct['status'] == 'PASS' and code['status'] == positive['status'] == 'BLOCKED'
    for report in [direct, code, positive]:
        assert report['model_http_calls'] == 3 and report['cold_restarts'] == 2
        assert report['inventory_before'] == report['inventory_after']
        assert report['inventory_before']['plugin_sha256'] == '23f888dc639f01754f4122dd606bfeebddf9e77f84757bee8db8fc318e05bb47'
        assert report['host_sha256'] == pin['platforms']['windows-x86_64']['binary_sha256']
    bad, good = direct['paired']['bad-original'], direct['paired']['good-original']
    assert bad['state'] == 'failed' and bad['result'] == {
        'dispatched': False, 'error': 'invalid_tool_arguments', 'executed': False}
    assert good['state'] == 'confirmed' and bad['id'] != good['id']
    assert len(direct['deliveries']) == 1 and direct['deliveries'][0]['operation'] == good['id']
    assert direct['deliveries'][0]['arguments'] == {'text': 'continue after original refusal'}
    assert len(code['deliveries']) == 0 and len(code['invokes']) == 1
    assert code['invokes'][0]['arguments'] == {'text': 42}
    assert code['paired']['code-original']['result']['composition']['child_count'] == 0
    rejected = exchanges(args.first / 'code')
    assert len(rejected) == 1 and rejected[0]['request']['method'] == 'tool.invoke'
    assert rejected[0]['reply']['error'] == {'code': -32003, 'message': 'method, grant or original scope denied'}
    assert len(positive['deliveries']) == 1
    assert positive['deliveries'][0]['arguments'] == {'text': 'before original refusal'}
    assert [x['ordinal'] for x in positive['invokes']] == [0, 1]
    assert [x['feed_index'] for x in positive['invokes']] == [0, 0]
    assert [x['engine_call_id'] for x in positive['invokes']] == ['0', '1']
    assert [x['arguments'] for x in positive['invokes']] == [{'text': 'before original refusal'}, {'text': 42}]
    child = positive['paired']['code-original']['result']['composition']['children']
    assert len(child) == 1 and child[0]['fed'] and child[0]['state'] == 'confirmed'
    assert child[0]['operation'] == positive['deliveries'][0]['operation']
    positive_wire = exchanges(args.control / 'code-control')
    invokes = [x for x in positive_wire if x['request']['method'] == 'tool.invoke']
    acks = [x for x in positive_wire if x['request']['method'] == 'tool.resume']
    assert len(invokes) == 2 and len(acks) == 1
    assert invokes[0]['reply']['result']['can_feed'] is True
    assert invokes[0]['reply']['result']['receipt']['id'] == child[0]['operation']
    assert acks[0]['request']['params']['ordinal'] == 0 and 'ack' in acks[0]['request']['params']
    assert invokes[1]['reply']['error'] == rejected[0]['reply']['error']
    assert positive['paired']['code-original']['state'] == 'failed'
    for folder, mode in [(args.first, 'direct'), (args.first, 'code'), (args.control, 'code-control')]:
        models = read(folder / mode / 'model.json')
        assert len(models) == 3
        calls = models[2]['messages']
        ids = {m['tool_call_id'] for m in calls if m.get('role') == 'tool'}
        assert ({'accept-original', 'bad-original', 'good-original'} if mode == 'direct'
                else {'accept-original', 'code-original'}) <= ids
    result = {'status': 'DIAGNOSTIC_VERIFIED', 'formal_card_status': 'BLOCKED',
              'source_commit': pin['source_commit'], 'host_sha256': direct['host_sha256'],
              'host_archive_sha256': pin['platforms']['windows-x86_64']['sha256'],
              'linux_plugin_sha256': code['inventory_before']['plugin_sha256'],
              'model_http_calls': 9, 'binding_deliveries': {'direct': 1, 'code': 0, 'code-control': 1},
              'direct_refusal': bad['result'], 'nested_rpc_error': rejected[0]['reply']['error'],
              'cold_restarts': 6, 'container_sets_restored': True,
              'original_success_preserved': child[0]['operation'], 'transfers': transfers,
              'methods': {'bad-first': rejected, 'positive-control': positive_wire},
              'limits': ['generic RPC error does not classify admission or failed child identity',
                         'no public root reserve ledger or budget claim', 'no authorization-revocation parity claim',
                         'no full H14, Work/run future, frozen-alias or publication acceptance']}
    args.out.mkdir(parents=True)
    (args.out / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'model_http_calls': 9, 'cold_restarts': 6}))


if __name__ == '__main__':
    main()
