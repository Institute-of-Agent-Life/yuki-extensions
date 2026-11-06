"""Run the original dual-region ingress witness on the exact new package/Host tuple."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys


def run(root,out,package,expected_sha):
    root=root.resolve();out.mkdir()
    sys.path.insert(0,str(root/'ci'))
    spec=importlib.util.spec_from_file_location('native_ingress',Path(__file__).resolve().parents[1]/'cases/EXT-005.py')
    test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)
    lock=json.loads((package/'package-manifest.json').read_bytes())
    name='yuki-feishu.exe'
    assert hashlib.sha256((package/name).read_bytes()).hexdigest()==expected_sha==lock['artifacts'][name]
    assert all(c['exit_code']==0 for c in lock['commands'])
    def verified_package(_root,unit,destination):
        assert unit==lock['unit_id']=='feishu'
        destination.mkdir()
        shutil.copyfile(package/name,destination/name)
        return lock
    filename,r=test.prepare(root,out,contract='core-038-main',package_builder=verified_package)
    assert r['status']=='PASS'
    (out/filename).write_text(json.dumps(r,indent=2)+'\n',encoding='utf8')
    wire=[json.loads(line) for line in (out/'wire.jsonl').read_text().splitlines()]
    calls=[x['frame'] for x in wire if x['frame'].get('method')=='gateway.inbound']
    assert calls and all('media_identity' not in x['params'] for x in calls)
    return {'status':'PASS','scope':'Original ingress/ACK regression on real fixed Host, ingress-only installations',
            'host_source':r.get('source_commit'),'plugin_sha256':expected_sha,'ingress_calls':len(calls),
            'gateway_media_callbacks':sum(x['frame'].get('method')=='gateway.media' for x in wire),
            'wire_sha256':hashlib.sha256((out/'wire.jsonl').read_bytes()).hexdigest()}


if __name__=='__main__':
    root,out,package=map(Path,sys.argv[1:4])
    (out.parent/'host-result.json').write_text(json.dumps(run(root,out,package,sys.argv[4]),indent=2)+'\n')
