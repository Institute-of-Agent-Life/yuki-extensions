"""Read the fixed legacy source and execute its Feishu boundary tests in isolated data."""
from pathlib import Path
import hashlib,json,os,sqlite3,subprocess,sys,tempfile,xml.etree.ElementTree as ET
source=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve()
baseline='329ca7c487414d2f54ddd98ff4727446ed2446cd'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()==baseline
assert not subprocess.check_output(['git','diff','HEAD','--'],cwd=source)
out.mkdir(parents=True,exist_ok=False)
files=['src/yuki/gateway/providers/feishu.py','src/yuki/gateway/providers/feishu_ws.py',
       'src/yuki/gateway/providers/feishu_ingress.py','src/yuki/gateway/providers/feishu_social.py',
       'src/yuki/identity/receipt_compat.py','src/yuki/conversation/canonical_db_models.py',
       'src/yuki/social/content.py','src/yuki/gateway/social.py',
       'tests/unit/test_feishu_client.py','tests/unit/test_feishu_ws.py',
       'tests/unit/test_feishu_social.py','tests/unit/test_feishu_configuration.py',
       'tests/integration/test_feishu_runtime.py']
bindings={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in files}
with tempfile.TemporaryDirectory(prefix='fs-original-owner-',dir='/tmp') as directory:
    env={key:value for key,value in os.environ.items() if not key.startswith('YUKI_')}
    env.update(PYTHONDONTWRITEBYTECODE='1',YUKI_DATA_DIR=directory,PYTHONPATH=str(source/'src'))
    command=[str(source/'.venv/bin/python'),'-m','pytest',*[name for name in files if name.startswith('tests/')],
             '-p','no:cacheprovider','-o','tmp_path_retention_policy=all','-o','tmp_path_retention_count=1','--basetemp',str(Path(directory)/'pytest'),'--junitxml',str(out/'junit.xml'),'-q']
    with (out/'pytest.log').open('xb') as log:
        result=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT)
    assert result.returncode==0
    originals = [p for p in Path(directory).rglob('test.db') if p.parent.name.startswith('test_native_private_') and not p.parent.is_symlink()]
    assert len(originals)==1, [(str(p.relative_to(directory))) for p in Path(directory).rglob('*.db')]
    original=originals[0]
    retained=out/'synthetic-legacy-core.db'
    with sqlite3.connect(original.as_uri()+'?mode=ro',uri=True) as prior, sqlite3.connect(retained) as copied:
        prior.backup(copied)
    with sqlite3.connect(retained.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        rows=[dict(row) for row in conn.execute('SELECT r.ingress_account_id,r.transport_namespace,r.ingress_presence_id,r.event_type,r.ingress_key,r.canonical_event_id,a.platform,a.external_account_id FROM canonical_event_receipts r JOIN accounts a ON a.id=r.ingress_account_id WHERE a.platform IN (?,?)',('feishu','lark'))]
        assert rows and all(row['external_account_id'].startswith('cli_test:') for row in rows)
        schema=[dict(row) for row in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name IN ('canonical_event_receipts','chat_events','accounts','account_assignments') ORDER BY name")]
    (out/'synthetic-receipts.json').write_text(json.dumps({'source_commit':baseline,'source_test':'tests/integration/test_feishu_runtime.py::test_native_private_uses_common_main_social_and_durable_duplicate','database_sha256':hashlib.sha256(retained.read_bytes()).hexdigest(),'rows':rows,'schema':schema,'owner':'legacy core SQLite','transfer_owner':'CORE-041','plugin_private_rows_imported':0},indent=2)+'\n')
assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==digest for name,digest in bindings.items())
assert not subprocess.check_output(['git','diff','HEAD','--'],cwd=source)
suite=ET.parse(out/'junit.xml').getroot()
cases=[{'name':case.attrib['name'],'class':case.attrib['classname'],
        'failed':case.find('failure') is not None or case.find('error') is not None,
        'skipped':case.find('skipped') is not None} for case in suite.iter('testcase')]
receipt={'source_commit':baseline,'source_files':bindings,'command':command,'exit_code':result.returncode,
         'status':'PASS' if result.returncode==0 and cases and not any(c['failed'] or c['skipped'] for c in cases) else 'FAIL',
         'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'tier':'fixed legacy boundary and durable owner oracle','isolated_data':True,'legacy_working_tree_modified':False,
         'cases':cases,'files':{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in ['junit.xml','pytest.log','synthetic-legacy-core.db','synthetic-receipts.json']}}
(out/'original-owner-oracle.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(receipt['status'],len(cases),flush=True)
assert receipt['status']=='PASS'
