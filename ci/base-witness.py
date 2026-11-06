"""Build the two versioned units and bind their joint observations to the signed distribution."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

from package import build

CASES = ('confirmed','lost-second','swapped','wrong-handle','revoked','missing-method','erased-readback')
REQUIRED = {'initialize','gateway.inbound','gateway.plan_send','gateway.dispatch_part','tool.call','tool.status'}


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def summarize(root, runs, output):
    lock = json.loads((root/'compat/base/source.lock.json').read_bytes())
    idl = json.loads((root/'compat/base/host-preview.json').read_bytes())
    assert sha256(root/'compat/base/host-preview.json') == lock['schema_sha256']
    assert sha256(root/'compat/base/handshake.ndjson') == lock['golden_sha256']
    cases, sources, effects, observations = {}, {}, {}, {}
    packages = None
    for case in CASES:
        folder = runs[case]
        result = json.loads((folder/'result.json').read_bytes())
        assert result['status']=='PASS' and result['case']==case and result['source']==lock['source_commit']
        assert result['sdk']==lock['rust_crate_sha256'] and result['schema']==lock['schema_sha256']
        assert result['host'] in {p['binary_sha256'] for p in lock['platforms'].values()}
        if packages is None:
            packages=result['packages']
        assert result['packages']==packages and result['post_restart_effects']==0 and result['redelivered_old_update']
        assert result['confirmed_offset_after_restart'] in result['ack_offsets_after_original_receipt']
        required_files=['model.json','native.json','host.log','installed.json','result.json','telegram.jsonl','web-fetch.jsonl','telegram.killed','web-fetch.killed']
        if case in ('revoked','erased-readback'): required_files.append('erasure.json')
        assert not (folder/'fixture-errors.json').exists()
        member_hashes={name:sha256(folder/name) for name in required_files}
        case_zip = output/(case+'.zip')
        with zipfile.ZipFile(case_zip,'x',zipfile.ZIP_DEFLATED) as archive:
            for name in required_files:
                archive.write(folder/name,name)
        for unit in packages:
            rows=[json.loads(line) for line in (folder/(unit+'.jsonl')).read_bytes().splitlines()]
            unit_observed=observations.setdefault(unit,{})
            expected_namespace = 'tg.bot101' if unit=='telegram' else 'official.web-fetch'
            for i,row in enumerate(rows):
                frame=row['frame']
                method=frame.get('method')
                if not method or row['direction']=='before_fault': continue
                direction=row['direction']
                if method=='initialize':
                    schema=sha256(root/'compat/base/handshake.schema.json')
                    grant=None
                else:
                    desc=idl['methods'][method]
                    assert direction=={'host_to_plugin':'from_host','plugin_to_host':'from_plugin'}[desc['direction']]
                    grant=desc['grant']
                    schema=lock['schema_sha256']
                response=next(x['frame'] for x in rows[i+1:] if x['direction'] not in (direction,'before_fault')
                              and x['frame'].get('id')==frame['id'] and ('error' in x['frame'] or 'result' in x['frame']))
                if method=='initialize':
                    assert response['result']['namespace']==expected_namespace
                record=unit_observed.setdefault(method,{'direction':direction,'grant':grant,'schema_sha256':schema,'cases':{}})
                record['cases'][case]=record['cases'].get(case,0)+1
            assert unit_observed['initialize']['cases'][case]>=2
        cases[case]={'zip':case_zip.name,'sha256':sha256(case_zip),'members':member_hashes,'result':result}
        sources[case]={unit:result['private_directories_after_kill'][unit] for unit in ('state-telegram','state-web-fetch','cursor')}
        effects[case]=result['native_parts']
    observed={name for table in observations.values() for name in table}
    if observed != REQUIRED:
        raise ValueError(f'base method set differs: {observed ^ REQUIRED}')
    assert [s['state'] for s in effects['confirmed']]==['confirmed']*3
    assert [s['state'] for s in effects['lost-second']]==['confirmed','unknown']
    assert all(not v for k,v in effects.items() if k not in ('confirmed','lost-second'))
    bound=['ci/base-witness.py','ci/package.py','ci/handshake_cargo.py','tests/cases/EXT-067.py',
           'tests/peers/joint_base.py','tests/peers/base_relay.py','compat/base/source.lock.json',
           'compat/base/verify_dist.py','compat/base/host-preview.json','compat/base/handshake.schema.json',
           'compat/base/host-boundaries.json','compat/base/handshake.ndjson','compat/base/yuki-plugin-sdk-1.0.0-alpha.14.crate']
    for unit in packages:
        bound += ['catalog/'+unit+'.json']
        bound += [p.relative_to(root).as_posix() for p in sorted((root/'plugins'/unit).rglob('*'))
                  if p.is_file() and not any(v.startswith('._') or v=='target' for v in p.parts)]
    return {'status':'PASS','card_status':'JOINT_CANDIDATE_WITNESSED','formal_release':False,
            'producer':'CORE-039','delivery':lock,'pinned_packages':packages,'required_method_witnesses':observations,
            'candidate_coverage':sorted(observed),'promoted_stable_methods':[],
            'privacy':{'profile':'new two-plugin installation with gateway.inbound, gateway.send and tool.call',
                       'inventory_after_kill':sources,'persistent_source_private_data':False,
                       'remaining_files':'Telegram offset and empty process lock; original admitted records owned by Host',
                       'not_witnessed':['persistent-owner forget.request','persistent-owner forget.ack','upgrades of installations with existing private data']},
            'inputs':{name:sha256(root/name) for name in bound},'cases':cases}


def run(root, output):
    archive=os.environ.get('YUKI_BASE_HOST_ARCHIVE')
    if not archive:
        return 'base-consumer-witness.json',{'status':'BLOCKED','reason':'YUKI_BASE_HOST_ARCHIVE must name the signed native archive pinned in compat/base/source.lock.json.'}
    work=output/'work'
    work.mkdir()
    for unit in ('telegram','web-fetch'):
        build(root,unit,work/unit)
    runs={}
    for case in CASES:
        runs[case]=work/case
        subprocess.run([sys.executable,root/'tests/peers/joint_base.py',root,work,archive,runs[case],'--case',case],check=True)
    return 'base-consumer-witness.json',summarize(root,runs,output)
