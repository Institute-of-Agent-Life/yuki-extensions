"""Native app/tenant resource preparation; full Host installation remains a separate gate."""
import hashlib
import importlib.util
import json
import os
import sys
from package import build


def prepare(root,output):
    work=output/'work';work.mkdir()
    spec=importlib.util.spec_from_file_location('original_feishu_case',root/'tests/cases/EXT-005.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    Frame,serve=fixture.fixture_imports(root,work)
    from feishu_media_wire import one,cleanup_without_credentials
    package=build(root,'feishu',output/'packages')
    name='yuki-feishu'+('.exe' if os.name=='nt' else '')
    cleanup=cleanup_without_credentials(output/'packages'/name)
    rows=[one(output/'packages'/name,Frame,serve,domain,kind) for domain,kind in [('feishu','image'),('lark','file')]]
    assert rows[0]['sha256']!=rows[1]['sha256']
    for row in rows:(output/(row['domain']+'-wire.json')).write_text(json.dumps(row.pop('wire'),indent=2)+'\n',encoding='utf8')
    (output/'build-receipt.json').write_text(json.dumps(package,indent=2)+'\n',encoding='utf8')
    pin=json.loads((root/package['source']['sdk_contract']).read_bytes())
    paths=[root/'catalog/feishu.json',root/package['source']['sdk_contract'],root/'ci/package.py',
        root/'ci/handshake_cargo.py',root/'ci/check.py',root/'tests/cases/EXT-006.py',root/'tests/cases/EXT-005.py',
        *(root/'tests/peers'/n for n in ['feishu_media_wire.py','lark_frames.py','lark-fixture.lock.json']),
        *(root/'plugins/feishu').glob('*'),*(root/'plugins/feishu/src').glob('*.rs')]
    return 'lark-rest.json',{'status':'PASS','card_status':'PLATFORM_RESOURCE_VERIFIED_HOST_AND_SOCIAL_PENDING',
        'actual_host_consumption':False,'models':0,'domains':rows,'erasure_only':cleanup,'binary_sha256':package['artifacts'][name],
        'sdk_source':pin['source_commit'],'sdk_sha256':pin['rust_crate_sha256'],'sdk_version':pin['sdk']['rust'],
        'source_bindings':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and not p.name.startswith('._')}}


def run(root,output):
    return 'lark-rest.json',{'status':'BLOCKED','card_status':'AWAITING_REAL_HOST_SELECTION_SOCIAL_AND_MIGRATION'}
