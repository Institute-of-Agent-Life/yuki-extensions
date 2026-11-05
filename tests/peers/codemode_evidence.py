"""Check original native identities, snapshots and cumulative counters in real wire."""
import base64
import hashlib
import json
from pathlib import Path


def inspect_case(path):
    path = Path(path)
    rows = [json.loads(line) for line in (path / 'wire.jsonl').read_text(encoding='utf-8').splitlines()]
    blocks = {}
    snapshots = []
    calls = []
    acknowledgements = []
    parents = []
    for row in rows:
        frame = row['frame']
        if row.get('forwarded') is False:
            continue
        method = frame.get('method')
        params = frame.get('params', {})
        if row['direction'] == 'from_host' and method in {'tool.call', 'code.resume'}:
            parents.append(params['operation'])
        if row['direction'] != 'from_plugin':
            continue
        if method == 'tool.invoke':
            calls.append(params)
        elif method == 'tool.resume' and 'ack' in params:
            acknowledgements.append(params)
        elif method == 'code.snapshot.put':
            key = params['snapshot']
            chunk = base64.b64decode(params['bytes'], validate=True)
            # A restore may reproduce an earlier content-addressed snapshot.
            if params['offset'] == 0:
                blocks[key] = bytearray()
            target = blocks[key]
            assert len(target) == params['offset']
            target.extend(chunk)
            assert len(target) <= params['size']
            if len(target) == params['size']:
                assert hashlib.sha256(target).hexdigest() == params['sha256'] == key
                state = json.loads(target)
                native = state['native']
                assert state['operation'] == parents[0]
                assert native['counters']['feeds'] == 1
                assert native['counters']['suspensions'] >= min(state['next'] + 1, 2)
                if snapshots:
                    assert native['counters']['suspensions'] >= snapshots[-1]['counters']['suspensions']
                snapshots.append({'sha256': key, 'next_ordinal': state['next'],
                                  'native_call': native['outcome'].get('call'),
                                  'counters': native['counters'], 'operation': state['operation']})
    assert len(set(parents)) == 1, parents
    result = json.loads((path / 'result.json').read_bytes())
    if result['mode'] in {'normal', 'before-feed', 'after-feed-twice'}:
        assert [(c['ordinal'], c['feed_index'], c['engine_call_id']) for c in calls] == [(0, 0, '0'), (1, 0, '1')]
        assert [(c['ordinal'], c['ack']['feed_index']) for c in acknowledgements] == [(0, 0), (1, 0)]
        assert snapshots[-1]['next_ordinal'] == 2
        assert snapshots[-1]['counters']['suspensions'] >= 2
    return {'original_parent': parents[0], 'actual_effects': result['deliveries'],
            'invocations': calls, 'acknowledgements': acknowledgements, 'snapshots': snapshots,
            'model_http_count': result['wire_count'], 'native_plugin_sha256': result['plugin_sha256']}


if __name__ == '__main__':
    import sys
    print(json.dumps(inspect_case(Path(sys.argv[1])), indent=2))
