"""Probe only documented original installation fields on the actual fixed Host."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def exercise(root, output, binary, expected_sha):
    sys.path.insert(0,str(root/'ci'))
    from host_preview import materialize
    from personal_preview import free_address
    work = output/'work'
    work.mkdir()
    host, pin, platform = materialize(root,work,'core-038-main')
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==expected_sha
    logs, phases = [], []
    settings = {}
    class Native(BaseHTTPRequestHandler):
        def do_POST(self):
            params=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            method=self.path.rsplit('/',1)[-1]
            assert self.path.startswith('/bot101:fixture/')
            logs.append({'method':method,'phase':settings['phase']})
            if method=='getMe':
                data={'id':101,'username':'OriginBot','is_bot':True}
            elif method=='getUpdates':
                seq=settings['seq']
                if params.get('offset',0)>seq:
                    time.sleep(.2)
                    data=[]
                else:
                    # Edited event: original message provenance without a new Main activation.
                    data=[{'update_id':seq,'edited_message':{'message_id':seq,'date':1,'edit_date':2,
                        'from':{'id':8},'chat':{'id':8,'type':'private'},'document':{'file_id':'origin-file'}}}]
            else:
                self.send_error(404)
                return
            body=json.dumps({'ok':True,'result':data}).encode()
            try:
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                pass
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Native)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    owner=work/'owner';cursor=work/'cursor';address=free_address()
    env=dict(os.environ,YUKI_TELEGRAM_BOT_ID='101',YUKI_TELEGRAM_TOKEN='101:fixture',
        YUKI_TELEGRAM_STATE=str(cursor),YUKI_TELEGRAM_API=f'http://127.0.0.1:{server.server_port}')
    def cli(*args):
        return subprocess.run([host,'--data',owner,*map(str,args)],cwd=work,env=env,
            capture_output=True,text=True,encoding='utf8',timeout=8)
    def op(*args):
        r=cli('operator',*args)
        if r.returncode:raise RuntimeError(str(args[:2])+': '+r.stderr[:300])
        return json.loads(r.stdout) if r.stdout.strip() else None
    @contextmanager
    def running():
        with (output/'host.txt').open('ab') as log:
            proc=subprocess.Popen([host,'--data',owner,'run'],cwd=work,env=env,stdout=log,stderr=log)
        try:yield proc
        finally:
            if proc.poll() is None:
                cli('operator','shutdown')
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
    try:
        cli('init').check_returncode()
        config=owner/'yuki.toml'
        base=config.read_text(encoding='utf8').replace('"127.0.0.1:0"',json.dumps(address))
        base=base.replace('mode = "hybrid"','mode = "lexical-only"')
        config.write_text(base,encoding='utf8')
        with running() as proc:
            until=time.monotonic()+15
            while cli('operator','database-info').returncode:
                if proc.poll() is not None or time.monotonic()>until:raise RuntimeError('owner failed to start')
                time.sleep(.05)
            person='34000000-0000-4000-8000-000000000008'
            op('person','create',person)
            op('account','open','telegram','tg.bot101','8',1,'--person',person,'--start',1)
            stage=op('account','open','telegram','tg.bot101','101',1,'--start',1)['assignment']
        for num,label,grants in [(50,'ingress-only',['gateway.inbound']),(51,'documented-grants',['gateway.inbound','gateway.media'])]:
            settings.update(seq=num,phase=label)
            trace=output/(label+'.jsonl')
            fields={'id':'telegram','namespace':'tg.bot101','program':sys.executable,
                'args':[str(root/'tests/peers/observe_stdio.py'),str(binary),str(trace)],
                'platform':'telegram','bot_stage':stage,'grants':grants,
                'env':['YUKI_TELEGRAM_BOT_ID','YUKI_TELEGRAM_TOKEN','YUKI_TELEGRAM_STATE','YUKI_TELEGRAM_API']}
            config.write_text(base+'\n[[plugins]]\n'+'\n'.join(k+'='+json.dumps(v) for k,v in fields.items())+'\n',encoding='utf8')
            with running() as proc:
                until=time.monotonic()+15
                while proc.poll() is None and time.monotonic()<until:
                    if trace.exists() and any(json.loads(l)['frame'].get('id')==num and
                            json.loads(l)['direction']=='from_host' for l in trace.read_text().splitlines() if l.endswith('}')):
                        break
                    time.sleep(.1)
                exit_before_shutdown=proc.poll()
            frames=[json.loads(l) for l in trace.read_text().splitlines()] if trace.exists() else []
            incoming=next((x['frame'] for x in frames if x['direction']=='from_plugin' and x['frame'].get('method')=='gateway.inbound'),None)
            receipt=next((x['frame'] for x in frames if x['direction']=='from_host' and x['frame'].get('id')==num),None)
            if label=='ingress-only':
                assert receipt and receipt.get('result',{}).get('event') and incoming
                assert 'media_identity' not in incoming['params']
            phases.append({'case':label,'installation':fields,'wire_frames':len(frames),
                'inbound':incoming,'receipt':receipt,'exit_before_shutdown':exit_before_shutdown})
        return {'status':'DIAGNOSTIC_OBSERVED','source':pin['source_commit'],'host':platform,'plugin':expected_sha,
                'sdk':pin['rust_crate_sha256'],'phases':phases,'native_requests':logs,
                'media_callbacks':sum(json.loads(l)['frame'].get('method')=='gateway.media'
                for f in output.glob('*.jsonl') for l in f.read_text().splitlines()),'model_endpoint_configured':False}
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':
    root,output,binary,sha=sys.argv[1:]
    out=Path(output);out.mkdir()
    report=exercise(Path(root),out,Path(binary),sha)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
