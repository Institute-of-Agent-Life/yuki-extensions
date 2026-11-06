"""Record notification target authorization using only the pinned public package."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse,hashlib,json,os,shutil,subprocess,tempfile,threading,time,uuid
from pathlib import Path
from personal_preview import Owner
from handshake_cargo import vendor_sdk

def build_peer(root,unit,output):
    pin=json.loads((root/'compat/core-058/source.lock.json').read_bytes())
    crate=root/'compat/core-058'/f"yuki-plugin-sdk-{pin['sdk']['rust']}.crate"
    assert hashlib.sha256(crate.read_bytes()).hexdigest()==pin['rust_crate_sha256']
    source=root/'tests/peers/notification-grant-probe';output.mkdir()
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
        name='notification-grant-probe'+('.exe' if os.name=='nt' else '')
        shutil.copy2(project/'target/debug'/name,output/name)
    report={'source':hashes,'sdk_sha256':pin['rust_crate_sha256'],'commands':commands,'artifacts':{name:hashlib.sha256((output/name).read_bytes()).hexdigest()}}
    (output.parent/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');return report

def prepare(root,out):
    pending=[];models=[];ops=[]
    class Model(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));models.append(body)
            action=pending.pop(0) if pending else None
            msg={'role':'assistant','content':None if action else ''}
            if action:
                name,args=action;msg['tool_calls']=[{'id':'intake-'+str(len(models)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]
            result={'id':'intake-'+str(len(models)),'choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if action else 'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}}
            b=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    server=ThreadingHTTPServer(('127.0.0.1',0),Model);threading.Thread(target=server.serve_forever,daemon=True).start()
    owner=Owner(root,out,'notification-probe',['notification.publish','tool.call'],contract='core-058',package_builder=build_peer,binary_name='notification-grant-probe')
    cfg=owner.data/'yuki.toml';text=cfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"')
    text=text.replace('\n[[plugins]]',f'\n[main]\nendpoint="http://127.0.0.1:{server.server_port}/model"\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=200000\nmax_output=512\n\n[[plugins]]')
    text+='[[plugins.tools]]\nname="grant_probe"\ndescription="Diagnose original administrator target grant"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={target={type="object"},bot_user_id={type="string"}},required=["target"],additionalProperties=false}\n'
    cfg.write_text(text,encoding='utf-8');(out/'host-config.toml').write_text(text,encoding='utf-8')
    def op(*args):
        r=owner.cli('operator',*map(str,args));ops.append({'args':args,'result':r});return r
    def wait(f):
        end=time.monotonic()+30
        while time.monotonic()<end:
            r=f()
            if r:return r
            time.sleep(.1)
        raise RuntimeError('no original notification grant receipt')
    def wire():
        try:return [json.loads(l) for l in owner.trace.read_text(encoding='utf-8').splitlines()]
        except (FileNotFoundError,json.JSONDecodeError):return []
    def probe_replies():return [f['frame']['result']['data'] for f in wire() if f['direction']=='from_plugin' and isinstance(f['frame'].get('result'),dict) and 'original_call' in f['frame']['result'].get('data',{})]
    person=str(uuid.uuid4());results=[]
    try:
        with owner.running():
            op('person','create',person);op('person','set-admin',person,'true')
            human=op('account','open','qq','notification-intake','200',1,'--person',person,'--start',1)
            bot=op('account','open','qq','notification-intake','100',1,'--start',1)
            entry=op('entry','private',human['assignment'],bot['assignment'])['entry']
            for i,(label,work,explicit) in enumerate([('foreground',False,True),('accepted-work',True,True),('current-entry',True,False)]):
                target={'target_type':'private','target_id':person}
                if explicit:target['conversation_id']=entry
                args={'target':target}
                if explicit:args['bot_user_id']='100'
                if work:pending.append(('task_control',{'action':'accept','goal':'Authorize the original target'}))
                pending.append(('grant_probe',args))
                op('ingress','record',json.dumps({'source':label,'account':human['account'],'bot_stage':bot['assignment'],'reply_bot':'100','kind':'message','occurred':100+i,'observed':100+i,'segments':[{'type':'text','text':label}]}),'--accept')
                wait(lambda:len(probe_replies())>i)
                result=probe_replies()[i];assert result['status']['Ok']['state']=='dispatched',result
                assert '-32003' in result['response'].get('Err',''),result
                results.append({'mode':label,**result});wait(lambda:not pending);time.sleep(.5)
            assert not [f for f in wire() if f['frame'].get('method')=='notification.publish']
        result={'status':'BLOCKED','observations_verified':True,'diagnostic_only':True,'card_status':'BLOCKED','core':owner.evidence(),'person':person,'entry':entry,'grants':results,'notification_publish_calls':0,'remaining':['producer-approved original administrator/receiving-bot grant recipe','publication and R06 consumer acceptance']}
        (out/'intake.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result
    finally:
        server.shutdown();server.server_close();(out/'model.json').write_text(json.dumps(models,ensure_ascii=False,indent=2),encoding='utf-8');(out/'operator.json').write_text(json.dumps(ops,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True)
    r=prepare(Path(__file__).resolve().parents[1],a.out.resolve())
    files={p.relative_to(a.out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out.rglob('*') if p.is_file() and not {'work','packages'}.intersection(p.relative_to(a.out).parts)}
    manifest={'task':'EXT-027','status':'BLOCKED','phase':'diagnostic','observations_verified':True,'source_snapshot_sha256':os.environ.get('YUKI_SOURCE_SNAPSHOT_SHA256'),'files':files}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps(manifest))
if __name__=='__main__':main()
