"""Drive the pinned receiving gateway, Host and PDF processor through a selected Main read."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def frames(path):
    if not path.exists():
        return []
    raw = path.read_bytes()
    return [json.loads(line) for line in raw.split(b'\n')[:-1] if line.strip()]


def wait(check, seconds=20):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise TimeoutError('timed out waiting for ' + check.__name__)


def run(args):
    sys.path.insert(0, str(args.root / 'ci'))
    from personal_preview import Owner
    case = args.domain
    tg = case == 'telegram'
    app = '101' if tg else 'cli_' + case
    tenant = 'tenant-' + case
    namespace = 'tg.bot101' if tg else 'fs.' + case
    user = '8' if tg else 'ou_user'
    reference = 'good.pdf'
    ident = {'application': app}
    if not tg:
        ident['tenant'] = tenant
    out = args.out
    out.mkdir()
    wire = out / 'gateway.jsonl'
    bundle = args.media / 'src/artifacts/EXT-031/candidate-03'
    codecs = bundle / 'work/codecs'
    pdf = (codecs / 'good.pdf').read_bytes()
    before, marker, trailer = pdf.rpartition(b'startxref')
    assert marker and b'%%EOF' in trailer
    payload = before + b'\n%' + case.encode() * 15000 + b'\n' + marker + trailer
    assert len(payload) > 2 * 24576
    binary = args.gateway
    expected = ('a07413f4b0b351eea85bb97b52f2e16d7fd59978f45414f948c4e9fd821b79e5' if tg
                else '4fc4e77480ba96709cb1172ebe8fd7a3e6f58d0f2469142cea2adc29d1ad57d0')
    assert sha(binary.read_bytes()) == expected
    trace, model, errors = [], [], []
    stop = threading.Event()
    websocket = None
    if not tg:
        spec = importlib.util.spec_from_file_location('original_ingress', args.root/'tests/cases/EXT-005.py')
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
        Frame, serve = native.fixture_imports(args.root, out)

        def socket(conn):
            try:
                conn.recv(timeout=10)
                msg = {'header': {'app_id': app, 'tenant_key': tenant, 'event_type': 'im.message.receive_v1'},
                       'event': {'sender': {'sender_type': 'user', 'sender_id': {'open_id': user}},
                                 'message': {'message_id':'om_original','chat_id':'oc_private','chat_type':'p2p',
                                             'message_type':'file','create_time':str(int(time.time()*1000)),
                                             'content':json.dumps({'file_key':reference,'file_name':'good.pdf'})}}}
                f = Frame(SeqID=17, LogID=81, service=9, method=1, payload=json.dumps(msg).encode())
                for k,v in {'type':'event','message_id':'17','sum':'1','seq':'0'}.items():
                    f.headers.add(key=k,value=v)
                conn.send(f.SerializeToString())
                while not stop.is_set():
                    ack = Frame.FromString(conn.recv(timeout=12))
                    if ack.SeqID == 17 and ack.LogID == 81:
                        assert json.loads(ack.payload) == {'code':200}
                        trace.append({'method':'socket-ack','serial':17})
                        break
                stop.wait(60)
            except Exception as error:
                if not stop.is_set():
                    errors.append(repr(error))
        websocket = serve(socket, '127.0.0.1', 0, ping_interval=None)
        threading.Thread(target=websocket.serve_forever,daemon=True).start()

    def received():
        calls = frames(wire)
        for item in calls:
            request = item['frame']
            if item['direction']=='from_plugin' and request.get('method')=='gateway.inbound':
                for other in calls:
                    reply = other['frame']
                    if other['direction']=='from_host' and reply.get('id')==request['id'] and 'result' in reply:
                        return reply['result'].get('event')

    class Endpoint(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def answer(self, value):
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_GET(self):
            path = urlsplit(self.path)
            if tg:
                assert path.path=='/file/bot101:fixture/document/good.pdf'
            else:
                assert unquote(path.path)=='/open-apis/im/v1/messages/om_original/resources/'+reference
                assert parse_qs(path.query)=={'type':['file']}
                assert self.headers['Authorization']=='Bearer fixture-'+case
            trace.append({'method':'resource','domain':case,'bytes':len(payload),'sha256':sha(payload)})
            self.answer(payload)

        def do_POST(self):
            v = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/model':
                model.append(v)
                save(out/'model-http.json', model)
                msg = {'role':'assistant','content':''}
                if len(model)==1:
                    event=wait(received)
                    msg={'role':'assistant','content':None,'tool_calls':[{'id':'selected-file','type':'function',
                         'function':{'name':'inspect_conversation_attachment','arguments':json.dumps(
                             {'event_id':event,'attachment_index':(1 if args.wrong_slot else 0),'question':'Read the selected original PDF.'})}}]}
                self.answer({'id':'local-'+str(len(model)),'choices':[{'index':0,'message':msg,
                             'finish_reason':'tool_calls' if 'tool_calls' in msg else 'stop'}],
                             'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
            elif self.path == '/callback/ws/endpoint':
                assert v=={'AppID':app,'AppSecret':'fixture-'+app}
                self.answer({'code':0,'data':{'URL':f'ws://127.0.0.1:{websocket.socket.getsockname()[1]}/socket?service_id=9',
                             'ClientConfig':{'PingInterval':30,'ReconnectInterval':1,'ReconnectCount':2,'ReconnectNonce':0}}})
            elif self.path == '/open-apis/auth/v3/tenant_access_token/internal':
                assert v=={'app_id':app,'app_secret':'fixture-'+app}
                trace.append({'method':'token','domain':case})
                self.answer({'code':0,'tenant_access_token':'fixture-'+case,'expire':3600})
            elif self.path == '/bot101:fixture/getUpdates':
                if v.get('offset',0)>41:
                    time.sleep(.1)
                    result=[]
                else:
                    result=[{'update_id':41,'message':{'message_id':9,'date':int(time.time()),'from':{'id':8},
                             'chat':{'id':8,'type':'private'},'document':{'file_id':reference,'file_name':reference}}}]
                self.answer({'ok':True,'result':result})
            elif self.path=='/bot101:fixture/getMe':
                self.answer({'ok':True,'result':{'id':101,'username':'OriginBot','is_bot':True}})
            elif self.path=='/bot101:fixture/getFile':
                assert v=={'file_id':reference}
                trace.append({'method':'getFile','domain':case})
                self.answer({'ok':True,'result':{'file_id':reference,'file_size':len(payload),'file_path':'document/good.pdf'}})
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(('127.0.0.1',0),Endpoint)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    api=f'http://127.0.0.1:{server.server_port}'
    def package(_root, unit, dest):
        assert unit=='media'
        m=json.loads((bundle/'packages/package-manifest.json').read_bytes())
        assert m['artifacts']['yuki-media.exe']==sha((bundle/'packages/yuki-media.exe').read_bytes())=='2d0e7e9b910789bf34b8d263475c71a720a2ee650628fc88a3292a64e26d454c'
        for member, expected_digest in m['artifacts'].items():
            assert sha((bundle/'packages'/member).read_bytes()) == expected_digest
        shutil.copytree(bundle/'packages', dest)
        return m

    try:
        temp=out/'private-temp'
        temp.mkdir()
        owner=Owner(args.root,out,'media',['media.process','media.open','media.publish','forget.owner'],
                    contract='core-038-main',package_builder=package,
                    environment={'YUKI_MEDIA_PYTHON':str(codecs/'Scripts/python.exe'),
                                 'YUKI_MEDIA_FFMPEG':str(codecs/'ffmpeg.exe'),'YUKI_MEDIA_TEMP':str(temp)})
        cfg=owner.data/'yuki.toml'
        core=cfg.read_text(encoding='utf8').replace('mode = "hybrid"', 'mode = "lexical-only"')
        core=core.replace('[[plugins]]','[main]\nendpoint='+json.dumps(api+'/model')+
                          '\nmodel="fixture"\nname="Yuki"\nmax_output=512\nroot_slots=8\nroot_tool_calls=8\nmerge_ms=1\nmax_input_units=1200000\nattachment_processor="media"\n\n[[plugins]]',1)
        cfg.write_text(core,encoding='utf8')
        person=str(uuid4())
        with owner.running():
            owner.cli('operator','person','create',person)
            owner.cli('operator','account','open',case,namespace,user,'1','--person',person,'--start','1')
            stage=owner.cli('operator','account','open',case,namespace,app,'1','--start','1')['assignment']
        env=({'YUKI_TELEGRAM_BOT_ID':app,'YUKI_TELEGRAM_TOKEN':'101:fixture','YUKI_TELEGRAM_STATE':str(out/'cursor'),'YUKI_TELEGRAM_API':api}
             if tg else {'YUKI_FEISHU_APP_ID':app,'YUKI_FEISHU_APP_SECRET':'fixture-'+app,'YUKI_FEISHU_TENANT':tenant,
                         'YUKI_FEISHU_DOMAIN':case,'YUKI_FEISHU_API':api,'YUKI_FEISHU_PROXY':''})
        owner.env.update(env)
        fields={'id':'gateway-'+case,'namespace':namespace,'platform':case,'bot_stage':stage,'program':sys.executable,
                'args':[str(args.root/'tests/peers/observe_stdio.py'),str(binary),str(wire)],
                'env':list(env),'grants':['gateway.inbound','gateway.media']}
        config=core+'\n[[plugins]]\n'+'\n'.join(k+'='+json.dumps(v) for k,v in fields.items())
        config+='\n[plugins.gateway_media]\n'+'\n'.join(k+'='+json.dumps(v) for k,v in ident.items())+'\n'
        cfg.write_text(config,encoding='utf8')
        (out/'installation.toml').write_text(config,encoding='utf8')
        with owner.running():
            wait(received)
            wait(lambda: len(model)>=2,45)
            stop.set()
        records=frames(wire)
        calls=[r['frame'] for r in records if r['direction']=='from_host' and r['frame'].get('method')=='gateway.media']
        receipt=json.loads(next(m['content'] for m in model[-1]['messages'] if m.get('tool_call_id')=='selected-file'))
        if args.wrong_slot:
            assert not calls and not any(r['method'] in ('resource','getFile','token') for r in trace)
            assert receipt['state']=='failed' and not any(
                r['frame'].get('method')=='media.process' for r in frames(owner.trace))
            assert not errors
            save(out/'result.json',{'status':'PASS','domain':case,'host_source':owner.pin['source_commit'],
                 'host':owner.platform,'sdk':owner.pin['rust_crate_sha256'],'gateway_binary':expected,
                 'stage':stage,'source_event':received(),'requested_slot':1,'actual_slots':[0],
                 'installation':ident,'gateway_callbacks':0,'native_gets':0,'model_http':len(model),
                 'original_receipt':receipt,'native':trace,'published':False})
            return
        original=b''
        assert calls
        for call in calls:
            param=call['params']
            assert param['offset']==len(original) and param['source_event']==received() and param['attachment_index']==0
            assert param['bot_stage']==stage and param['namespace']==namespace and param['media_identity']==ident
            assert param['platform']==case and param['reference']==reference
            reply=next(r['frame']['result'] for r in records if r['direction']=='from_plugin' and
                       r['frame'].get('id')==call['id'] and 'result' in r['frame'])
            assert reply['sha256']==sha(payload) and reply['size']==len(payload) and reply['offset']==param['offset']
            original+=base64.b64decode(reply['data'],validate=True)
        assert original==payload and sum(r['method']=='resource' for r in trace)==1
        assert receipt['state']=='confirmed' and 'Selected page one' in json.dumps(receipt)
        if not tg:assert any(r['method']=='socket-ack' for r in trace)
        assert not errors
        save(out/'result.json',{'status':'PASS','domain':case,'source_event':received(),'stage':stage,'installation':ident,
             'host_source':owner.pin['source_commit'],'host':owner.platform,'sdk':owner.pin['rust_crate_sha256'],
             'gateway_binary':expected,'processor_binary':owner.binary_sha,'offsets':[c['params']['offset'] for c in calls],
             'selected_bytes':len(original),'selected_sha256':sha(original),'operation':receipt['id'],'model_http':len(model),
             'native':trace,'published':False})
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        if websocket:websocket.shutdown()
        save(out/'native-http.json',{'calls':trace,'errors':errors})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('domain',choices=('telegram','feishu','lark'))
    parser.add_argument('--wrong-slot',action='store_true')
    for name in ('root','media','gateway','out'):
        parser.add_argument(name,type=lambda p:Path(p).resolve())
    run(parser.parse_args())
