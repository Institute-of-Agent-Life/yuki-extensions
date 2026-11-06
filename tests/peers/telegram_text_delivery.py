"""Real Host plan/dispatch witness with the original Rust gateway and loopback Telegram API."""
import argparse
import hashlib
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def exercise(root, package, out, case):
    lost = case == 'lost-second'
    group = case in {'topic','quote'}
    chat = -15 if group else 8
    sys.path.insert(0, str(root / 'ci'))
    from personal_preview import free_address
    from host_preview import materialize

    out.mkdir()
    host_dir=out/'work'
    host_dir.mkdir()
    host,pin,platform=materialize(root,host_dir,'core-038-main')
    package_manifest=json.loads((package/'package-manifest.json').read_bytes())
    binary=package/'yuki-telegram.exe'
    binary_digest=hashlib.sha256(binary.read_bytes()).hexdigest()
    assert binary_digest==package_manifest['artifacts'][binary.name] and all(x['exit_code']==0 for x in package_manifest['commands'])
    data=host_dir/'owner'
    native,models,polls=[],[],[]
    trace=out/'gateway.jsonl'
    send_text='雪'*4095+'🌨'+'<&>'*1365+'🦊'+'final'
    assert len(send_text)==8197
    def frames():
        if not trace.exists():return []
        return [json.loads(line) for line in trace.read_bytes().split(b'\n')[:-1] if line.strip()]
    class Peer(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,v):
            b=json.dumps(v).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Length',str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            except (ConnectionError,OSError):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/model':
                models.append(body)
                write(out/'model.json',models)
                message={'role':'assistant','content':''}
                if len(models)==1:
                    args={'text':send_text}
                    if case=='quote':
                        deadline=time.monotonic()+6
                        while time.monotonic()<deadline:
                            observed=frames()
                            original=next((x['frame'] for x in observed if x['frame'].get('method')=='gateway.inbound'),None)
                            if original:
                                result=next((x['frame'].get('result') for x in observed if x['direction']=='from_host' and x['frame'].get('id')==original['id']),None)
                                if result:
                                    args={'text':'original quote','reply_to_event_id':result['event']}
                                    break
                            time.sleep(.03)
                        assert 'reply_to_event_id' in args
                    message={'role':'assistant','content':None,'tool_calls':[{'id':'send-original','type':'function',
                             'function':{'name':'send','arguments':json.dumps(args,ensure_ascii=False)}}]}
                self.reply({'id':'local-'+str(len(models)),'choices':[{'index':0,'message':message,
                            'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop'}],
                            'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            elif self.path=='/bot101:fixture/getMe':
                self.reply({'ok':True,'result':{'id':101,'is_bot':True,'username':'OriginBot'}})
            elif self.path=='/bot101:fixture/getUpdates':
                polls.append(body.get('offset',0))
                updates=[]
                if body.get('offset',0)<=51:
                    updates=[{'update_id':51,'message':{'message_id':72,'date':int(time.time()),'from':{'id':8},
                             'chat':{'id':chat,'type':'supergroup' if group else 'private'},'text':'@OriginBot send','entities':[{'type':'mention','offset':0,'length':10}],**({'message_thread_id':7} if group else {})}}]
                else:time.sleep(.08)
                self.reply({'ok':True,'result':updates})
            elif self.path=='/bot101:fixture/sendMessage':
                assert body['chat_id']==str(chat)
                assert body.get('message_thread_id')==(7 if group else None)
                native.append(body)
                write(out/'native.json',native)
                if lost and len(native)==2:
                    self.close_connection=True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                self.reply({'ok':True,'result':{'message_id':700+len(native),'chat':{'id':chat}}})
            else:self.send_error(404)

    server=ThreadingHTTPServer(('127.0.0.1',0),Peer)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    api=f'http://127.0.0.1:{server.server_port}'
    selected={'YUKI_TELEGRAM_API':api,'YUKI_TELEGRAM_BOT_ID':'101','YUKI_TELEGRAM_TOKEN':'101:fixture',
              'YUKI_TELEGRAM_STATE':str(host_dir/'cursor')}
    env={**os.environ,**selected}
    def cli(*args,check=True):
        p=subprocess.run([host,'--data',data,*args],cwd=host_dir,capture_output=True,text=True,encoding='utf8',env=env,timeout=12)
        if check and p.returncode:raise RuntimeError(p.stderr[:600])
        return json.loads(p.stdout) if not p.returncode and p.stdout.strip() else None
    @contextmanager
    def running():
        with (out/'host.txt').open('ab') as log:
            proc=subprocess.Popen([host,'--data',data,'run'],env=env,cwd=host_dir,stdout=log,stderr=log)
        try:
            until=time.monotonic()+15
            while not cli('operator','database-info',check=False):
                if proc.poll() is not None or time.monotonic()>until:raise RuntimeError('Host failed to open')
                time.sleep(.08)
            yield
        finally:
            if proc.poll() is None:
                cli('operator','shutdown',check=False)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
    try:
        cli('init')
        cfg=data/'yuki.toml'
        top=cfg.read_text(encoding='utf8').replace('"127.0.0.1:0"',json.dumps(free_address())).replace('mode = "hybrid"','mode = "lexical-only"')
        top+='\n[main]\nendpoint='+json.dumps(api+'/model')+'\nmodel="fixture"\nname="Yuki"\nmax_output=12000\nroot_slots=8\nroot_tool_calls=8\nmerge_ms=1\nmax_input_units=1200000\n'
        cfg.write_text(top,encoding='utf8')
        with running():
            person=str(uuid.uuid4())
            cli('operator','person','create',person)
            cli('operator','account','open','telegram','tg.bot101','8','1','--person',person,'--start','1')
            stage=cli('operator','account','open','telegram','tg.bot101','101','1','--start','1')['assignment']
        install={'id':'telegram','namespace':'tg.bot101','platform':'telegram','bot_stage':stage,'program':sys.executable,
                 'args':[str(root/'tests/peers/observe_stdio.py'),str(binary),str(trace)],'env':list(selected),
                 'grants':['gateway.inbound','gateway.send']}
        cfg.write_text(top+'\n[[plugins]]\n'+'\n'.join(k+'='+json.dumps(v) for k,v in install.items()),encoding='utf8')
        with running():
            until=time.monotonic()+35
            while len(models)<2 and time.monotonic()<until:time.sleep(.08)
            assert len(models)==2,'expected original Main continuation'
        pairs=[]
        for ix,r in enumerate(frames()):
            req=r['frame']
            if r['direction']=='from_host' and req.get('method') in ('gateway.plan_send','gateway.dispatch_part'):
                rep=next(x['frame'] for x in frames()[ix+1:] if x['direction']=='from_plugin' and x['frame'].get('id')==req['id'])
                pairs.append({'method':req['method'],'params':req['params'],'reply':rep})
        assert pairs[0]['method']=='gateway.plan_send'
        receipt=json.loads(next(m['content'] for m in models[-1]['messages'] if m.get('tool_call_id')=='send-original'))
        if case=='quote':
            assert len(pairs)==1 and not native
            plan=pairs[0]
            assert plan['params']['arguments']['message']['reply_to_event_id']>0 and plan['reply']['error']['code']==-32602
            write(out/'result.json',{'status':'PASS','case':case,'scope':'unsupported event reference stops before native dispatch',
                 'source':pin['source_commit'],'host':platform,'sdk':pin['rust_crate_sha256'],'gateway':binary_digest,
                 'model_operation':receipt,'native_sends':0,'plan':plan,'published':False})
            return
        planned=[p['text'] for p in pairs[0]['reply']['result']['parts']]
        assert ''.join(planned)==send_text and list(map(len,planned))==[4096,4096,5]
        dispatched=pairs[1:]
        assert all(p['method']=='gateway.dispatch_part' for p in dispatched)
        assert [r['text'] for r in native]==planned[:len(native)] and len(native)==(2 if lost else 3)
        for i,p in enumerate(dispatched):
            assert p['params']['arguments']['part_ordinal']==i
            assert p['params']['arguments']['route']==pairs[0]['params']['arguments']['route']
            expected={'state':'unknown'} if lost and i==1 else {'state':'confirmed','locator':str(chat)+':'+str(701+i)}
            assert p['reply']['result']==expected
        assert len(dispatched)==len(native)
        receipt=json.loads(next(m['content'] for m in models[-1]['messages'] if m.get('tool_call_id')=='send-original'))
        assert receipt['state']==('unknown' if lost else 'confirmed')
        assert [part['id'] for part in receipt['result']['parts']]==[p['params']['operation'] for p in dispatched]
        before=(len(models),len(native))
        previous=len(polls)
        with running():
            until=time.monotonic()+12
            while 52 not in polls[previous:] and time.monotonic()<until:time.sleep(.05)
            assert 52 in polls[previous:]
        assert before==(len(models),len(native))
        write(out/'result.json',{'status':'PASS','case':case,'source':pin['source_commit'],
             'host':platform,'sdk':pin['rust_crate_sha256'],'gateway':binary_digest,'paid_fixture_http':len(models),
             'plan':pairs[0]['params']['operation'],'part_operations':[p['params']['operation'] for p in dispatched],
             'part_receipts':[p['reply']['result'] for p in dispatched],'model_operation':receipt,'native_sends':len(native),
             'post_restart_sends':0,'published':False})
    finally:
        server.shutdown()
        server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=['confirmed','lost-second','topic','quote'],default='confirmed')
    for opt in ('root','package','out'):
        parser.add_argument(opt,type=lambda s:Path(s).resolve())
    args=parser.parse_args()
    exercise(args.root,args.package,args.out,args.case)
