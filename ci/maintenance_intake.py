"""Record maintenance route authorization using only the pinned public package."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse,hashlib,json,os,shutil,subprocess,tempfile,threading,time,uuid
from pathlib import Path
from personal_preview import Owner
from handshake_cargo import vendor_sdk

def build_peer(root,unit,output):
    pin=json.loads((root/'compat/core-035/source.lock.json').read_bytes())
    crate=root/'compat/core-035'/f"yuki-plugin-sdk-{pin['sdk']['rust']}.crate"
    assert hashlib.sha256(crate.read_bytes()).hexdigest()==pin['rust_crate_sha256']
    source=root/'tests/peers/maintenance-route-probe';output.mkdir()
    hashes={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file() and not p.name.startswith('._')}
    commands=[]
    with tempfile.TemporaryDirectory(prefix='yuki-maintenance-intake-') as td:
        project=Path(td)/'peer';shutil.copytree(source,project,ignore=shutil.ignore_patterns('._*','target'))
        lock=project/'Cargo.lock';vendor_sdk(crate,project,lock if lock.exists() else None)
        actions=[['cargo','build','--locked','--offline'],['rustc','--version','--verbose']]
        if not lock.exists():actions.insert(0,['cargo','generate-lockfile','--offline'])
        for args in actions:
            r=subprocess.run(args,cwd=project,capture_output=True,text=True,timeout=120)
            commands.append({'argv':args,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
            if r.returncode:raise RuntimeError(r.stderr)
        shutil.copy2(lock,output.parent/'generated-Cargo.lock')
        name='maintenance-route-probe'+('.exe' if os.name=='nt' else '')
        shutil.copy2(project/'target/debug'/name,output/name)
    report={'source':hashes,'sdk_sha256':pin['rust_crate_sha256'],'commands':commands,'artifacts':{name:hashlib.sha256((output/name).read_bytes()).hexdigest()}}
    (output.parent/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

def prepare(root,out):
    calls=[]
    class Peer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            calls.append({'path':self.path,'body':json.loads(self.rfile.read(int(self.headers['Content-Length'])))})
            self.send_response(503);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Peer);threading.Thread(target=server.serve_forever,daemon=True).start()
    probe=out/'probe';probe.mkdir()
    methods=['maintenance.history.page','maintenance.model.open','maintenance.extract.preview','maintenance.extract.apply']
    owner=Owner(root,out,'memory-maintenance',methods+['llm.complete','llm.result','forget.owner'],contract='core-035',environment={'YUKI_MAINTENANCE_PROBE':str(probe)},package_builder=build_peer,binary_name='maintenance-route-probe')
    cfg=owner.data/'yuki.toml';cfg.write_text(cfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"'),encoding='utf-8')
    records=[]
    def op(*args):
        r=owner.cli('operator',*map(str,args));records.append({'args':list(args),'result':r});return r
    actor=str(uuid.uuid4())
    try:
        with owner.running():
            op('person','create',actor)
            user=op('account','open','qq','rebuild-intake','200',1,'--person',actor,'--start',1)
            bot=op('account','open','qq','rebuild-intake','100',1,'--start',1)
            space=json.dumps(['qq','rebuild-intake','702'],separators=(',',':'));entry=op('entry','group',space)['entry'];events=[]
            for name,text in [('primary','我每天喝烏龍茶。'),('context','上下文原句，不當成主要來源。')]:
                frame={'source':name,'account':user['account'],'bot_stage':bot['assignment'],'reply_bot':'100','space':space,'kind':'message','occurred':100,'observed':100,'segments':[{'type':'text','text':text}]}
                events.append(op('ingress','record',json.dumps(frame),'--accept')['event'])
        policy='\n[plugins.maintenance.scopes.own]\n'+f'actor={json.dumps(actor)}\nentry={json.dumps(entry)}\n'
        policy+='methods='+json.dumps(methods)+'\npurposes=["rebuild"]\nroutes=["extract"]\n'
        policy+='write_subject={kind="person",person='+json.dumps(actor)+'}\n'
        policy+='\n[plugins.aux_routes.extract]\npurposes=["rebuild"]\norigins=["maintenance"]\n'+f'entries={json.dumps([entry])}\n'
        policy+='[plugins.aux_routes.extract.profile]\nprotocol="chat"\nname="rebuild-fixture"\nmodel="fixture-extraction"\nmerge_ms=1\nroot_tool_calls=8\nroot_slots=4\nmax_output=2048\nmax_input_units=32000\n'
        policy+=f'endpoint="http://127.0.0.1:{server.server_port}/v1/chat/completions"\n'
        cfg.write_text(cfg.read_text()+policy,encoding='utf-8');(out/'maintenance-policy.toml').write_text(policy,encoding='utf-8')
        with owner.running():
            (probe/'request.json').write_text(json.dumps({'events':events}),encoding='utf-8')
            end=time.monotonic()+25
            while time.monotonic()<end and not (probe/'result.json').exists() and not (probe/'error.txt').exists():time.sleep(.1)
            assert not (probe/'error.txt').exists(),(probe/'error.txt').read_text()
            result=json.loads((probe/'result.json').read_bytes())
            assert [p['items'][0]['event'] for p in result['pages']]==events
            assert all(p['items'][0]['actor']==actor and p['items'][0]['entry']==entry for p in result['pages'])
            assert '-32003' in result['model_open']['Err'] and '-32003' in result['extract_preview']['Err']
            assert not calls
        report={'status':'BLOCKED','observations_verified':True,'card_status':'BLOCKED','diagnostic_only':True,'core':owner.evidence(),'actual':result,'http_calls':0,'remaining':['producer-approved public maintenance extraction route configuration','original paid preview, subset writes, crash recovery and erasure consumer acceptance']}
        (out/'intake.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        server.shutdown();server.server_close()
        (out/'provider.json').write_text(json.dumps(calls),encoding='utf-8');(out/'operator.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True)
    r=prepare(Path(__file__).resolve().parents[1],a.out.resolve())
    files={p.relative_to(a.out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out.rglob('*') if p.is_file() and not {'work','packages'}.intersection(p.relative_to(a.out).parts)}
    m={'task':'EXT-034','status':r['status'],'phase':'diagnostic','observations_verified':r['observations_verified'],'source_snapshot_sha256':os.environ.get('YUKI_SOURCE_SNAPSHOT_SHA256'),'files':files}
    (a.out/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(m))
if __name__=='__main__':main()
