import hashlib,json,pathlib,platform,sys,zipfile
source=pathlib.Path(sys.argv[1]);evidence=pathlib.Path(sys.argv[2]);old=pathlib.Path(sys.argv[3]);out=pathlib.Path(sys.argv[4]);out.mkdir()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report=json.loads((evidence/'original-uuid-entry.json').read_bytes());manifest=json.loads((evidence/'manifest.json').read_bytes())
assert report['status']==manifest['status']=='PASS'
for name,digest in manifest['files'].items():assert sha(evidence/name)==digest
bindings=json.loads((evidence/'source-bindings.json').read_bytes())
for name,digest in bindings.items():assert sha(source/name)==digest,name
pin=json.loads((source/'compat/core-033-client/source.lock.json').read_bytes())
assert pin['source_commit']=='c616cf35e4424e2b9f3c99a4481bfab1c99a34f3' and pin['published'] is False
assert sha(evidence/'work/yuki-core.exe')==pin['platforms']['windows-x86_64']['binary_sha256']
assert sha(evidence/'packages/yuki-client.exe')==report['plugin_sha256']
assert report['sdk']['sha256']==pin['rust_crate_sha256']
build=json.loads((evidence/'build.json').read_bytes())
assert build['artifacts']['yuki-client.exe']==report['plugin_sha256'] and build['version']=='0.1.0-alpha.2'
assert all(c['exit_code']==0 for c in build['commands'])
assert any(c['command'][:2]==['cargo','test'] and '2 passed' in c['stdout'] for c in build['commands'])
assert sha(evidence/'wire.jsonl')==report['wire_sha256']
names={c['name'] for c in report['cases']['H24']}
assert {'same-person-original-uuid','merged-selected-entry','invalid-and-duplicate-selection','ordered-attachment-conflict','committed-inbound-sse-and-resync','sse-capacity-preserves-ordinary-requests','revoke-device-closes-original-streams','paused-entry-is-not-device-revocation','cold-original-and-selected-receipts'}<=names
assert 'committed-social-sse-and-resync' not in names
acp=json.loads((evidence/'acp-diagnostic.json').read_bytes());assert acp['status']=='BLOCKED' and acp['actual_status']==404
oldmanifest=json.loads((old/'manifest.json').read_bytes());assert oldmanifest['status']=='FAIL'
for name,digest in oldmanifest['files'].items():assert sha(old/name)==digest
ops=json.loads((old/'operator.json').read_bytes());inspect=ops[-1]['result']
assert ops[-1]['args'][:2]==['main','inspect'] and inspect['state']=='held' and inspect['diagnostic']=='runner_failed'
assert not (old/'binding-http.json').exists()
assert sha(evidence.parent/'evidence.zip')=='d5982c42fc90dba765ede61fdb5a253fbb5d2936e246f253991e4ea7dbdc61a0'
result={'status':'DIAGNOSTIC_VERIFIED','card_status':'BLOCKED_COMPLETE_H24_SOCIAL_AND_PUBLICATION','platform':platform.platform(),'native_cases':len(names),'source_bindings':len(bindings),'source_snapshot_sha256':manifest['source_snapshot_sha256'],'evidence_zip_sha256':sha(evidence.parent/'evidence.zip'),'host':pin['platforms']['windows-x86_64'],'sdk':report['sdk'],'plugin_sha256':report['plugin_sha256'],'wire_sha256':report['wire_sha256'],'cases':sorted(names),'model_fixture_http':report['model_http_requests'],'producer_published':False,'acp_actual_status':404,'social_inspect':inspect,'social_diagnostic_snapshot_sha256':oldmanifest['source_snapshot_sha256'],'social_diagnostic_evidence_zip_sha256':sha(old.parent/'evidence.zip'),'audit_sha256':sha(pathlib.Path(__file__))}
(out/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
(out/'manifest.json').write_text(json.dumps({'task':'EXT-015','status':'PASS','phase':'native-evidence-audit','files':{'analysis.json':sha(out/'analysis.json')}},indent=2),encoding='utf-8')
with zipfile.ZipFile(out.parent/'client-analysis-01.zip','x',zipfile.ZIP_DEFLATED) as z:
 for p in out.iterdir():z.write(p,p.name)
print('ZIP_SHA256',sha(out.parent/'client-analysis-01.zip'))
