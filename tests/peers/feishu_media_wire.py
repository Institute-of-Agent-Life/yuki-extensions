"""Two independent app/domain REST fixtures; a real Protobuf socket and release binary."""
import base64
from hashlib import sha256
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import os
import queue
import subprocess
import threading
import time
from urllib.parse import unquote, urlsplit, parse_qs


def one(binary, Frame, serve, domain, kind):
    app,tenant,ns='cli_'+domain,'tenant-'+domain,'fs.'+domain
    identity={'application':app,'tenant':tenant}
    native_key='res #/native'
    content=(domain.encode()*7000)[:26789]
    assert len(content)>24576
    entered,release,ack,shutdown=(threading.Event() for _ in range(4))
    requests,wire,errors=[],[],[]
    issued=[]

    def socket(conn):
        try:
            assert conn.request.path=='/socket?service_id=9'
            ping=Frame.FromString(conn.recv(timeout=8))
            assert any(h.key=='type' and h.value=='ping' for h in ping.headers)
            attachment={'image_key' if kind=='image' else 'file_key':native_key}
            body={'header':{'app_id':app,'tenant_key':tenant,'event_type':'im.message.receive_v1'},
                'event':{'sender':{'sender_type':'user','sender_id':{'open_id':'ou_user'}},
                    'message':{'message_id':'om_original','chat_id':'oc_room','chat_type':'group',
                    'thread_id':'topic','create_time':'1000','message_type':kind,'content':json.dumps(attachment)}}}
            f=Frame(SeqID=17,LogID=81,service=9,method=1,payload=json.dumps(body).encode())
            for k,v in {'type':'event','message_id':'17','sum':'1','seq':'0'}.items():f.headers.add(key=k,value=v)
            conn.send(f.SerializeToString())
            until=time.monotonic()+12
            while time.monotonic()<until:
                reply=Frame.FromString(conn.recv(timeout=8))
                if reply.SeqID==17 and reply.LogID==81:
                    assert json.loads(reply.payload)=={'code':200}
                    ack.set()
                    break
            shutdown.wait(120)
        except Exception as e:
            errors.append(type(e).__name__+':'+str(e))

    ws=serve(socket,'127.0.0.1',0,ping_interval=None)
    class HTTP(BaseHTTPRequestHandler):
        def answer(self,v,code=200):
            payload=v if isinstance(v,bytes) else json.dumps(v).encode()
            self.send_response(code);self.send_header('Content-Length',str(len(payload)));self.end_headers()
            self.wfile.write(payload)
        def do_POST(self):
            v=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/callback/ws/endpoint':
                assert v=={'AppID':app,'AppSecret':'fixture-'+app}
                self.answer({'code':0,'data':{'URL':f'ws://127.0.0.1:{ws.socket.getsockname()[1]}/socket?service_id=9',
                    'ClientConfig':{'PingInterval':30,'ReconnectInterval':1,'ReconnectCount':2,'ReconnectNonce':0}}})
            else:
                assert self.path=='/open-apis/auth/v3/tenant_access_token/internal'
                assert v=={'app_id':app,'app_secret':'fixture-'+app}
                issued.append(f'fixture-{domain}-{len(issued)}')
                requests.append({'method':'token','app':app,'tenant':tenant,'issuance':len(issued)})
                self.answer({'code':0,'tenant_access_token':issued[-1],'expire':3})
        def do_GET(self):
            path=urlsplit(self.path)
            assert unquote(path.path).startswith('/open-apis/im/v1/messages/om_original/resources/')
            # The slash in the opaque key must remain inside one URL path segment.
            assert len(path.path.split('/'))==8
            key=unquote(path.path.split('/')[-1]);ty=parse_qs(path.query).get('type')
            assert ty==['image' if kind=='image' else 'file'] and self.headers['Authorization']=='Bearer '+issued[-1]
            requests.append({'method':'resource','domain':domain,'raw_path':self.path,'key':key,'type':ty[0],'token_number':len(issued)})
            if key=='denied':
                self.answer(b'',403);return
            assert key==native_key
            if not entered.is_set():
                entered.set();release.wait(8)
            self.answer(content)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),HTTP)
    for obj in (ws,server):threading.Thread(target=obj.serve_forever,daemon=True).start()
    grants=['gateway.inbound','gateway.media']
    binding={'namespace':ns,'grants':grants,'manifest_revision':'f'*64,'declarations':[]}
    env=dict(os.environ,YUKI_PLUGIN_BINDING=json.dumps(binding),YUKI_FEISHU_DOMAIN=domain,
        YUKI_FEISHU_APP_ID=app,YUKI_FEISHU_TENANT=tenant,YUKI_FEISHU_APP_SECRET='fixture-'+app,
        YUKI_FEISHU_API=f'http://127.0.0.1:{server.server_port}',YUKI_FEISHU_PROXY='')
    proc=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    lines=queue.Queue()
    def pump():
        for line in proc.stdout:lines.put(line)
        lines.put(None)
    threading.Thread(target=pump,daemon=True).start()
    def read():
        try:line=lines.get(timeout=7)
        except queue.Empty as e:raise RuntimeError(f"peer timeout: last={[(r['from'],r['frame'].get('id'),r['frame'].get('method')) for r in wire[-5:]]}, HTTP={requests}, WS={errors}, exited={proc.poll()}") from e
        if line is None:raise RuntimeError(proc.stderr.read(400).decode(errors='replace'))
        msg=json.loads(line);wire.append({'from':'plugin','frame':msg});return msg
    def send(msg):
        wire.append({'from':'fixture','frame':msg});proc.stdin.write(json.dumps(msg).encode()+b'\n');proc.stdin.flush()
    index=90
    def call(p):
        nonlocal index
        index+=1
        send({'jsonrpc':'2.0','method':'gateway.media','id':index,'params':p})
        return index
    def reply(i,ok):
        m=read()
        assert m['id']==i and (('result' in m)==ok) and (('error' in m)!=ok)
        return m.get('result')
    try:
        init=read();assert init['method']=='initialize'
        send({'jsonrpc':'2.0','id':init['id'],'result':{'schema_revision':1,'version':{'major':1,'minor':0},
            **{k:binding[k] for k in ['namespace','grants','manifest_revision']},'features':['initialize'],
            'extension_points':[],'host_schema_revision':2,'method_revisions':[{'name':m,'revision':1} for m in ['initialize',*grants]]}})
        event=read();params=event['params']
        assert event['method']=='gateway.inbound' and params['media_identity']==identity
        assert params['segments'][0]=={'type':'media','kind':kind,'reference':native_key}
        locator={k:params.get(k) for k in ['source','space','topic','sender','native_id','native_version']}
        key={'transfer':'A','platform':domain,'namespace':ns,'bot_stage':'fixture','source_event':12,
            'attachment_index':0,'segment_index':0,'media_identity':identity,'locator':locator,
            'kind':kind,'reference':native_key,'offset':0,'length':24576}
        for change in [{'media_identity':{**identity,'tenant':'foreign'}},{'media_identity':{**identity,'application':'foreign'}},
            {'platform':'telegram'},{'namespace':'wrong'},{'offset':1},{'locator':{**locator,'source':'another-message'}}]:
            reply(call({**key,**change}),False)
        assert not requests
        i=call(key)
        assert entered.wait(6) and not release.is_set()
        send({'jsonrpc':'2.0','id':event['id'],'result':{'event':12,'accepted':True}})
        assert ack.wait(4) and not release.is_set(), 'WS admission ACK stalled behind REST'
        release.set();page0=reply(i,True)
        reply(call({**key,'offset':24576,'source_event':13}),False)
        page1=reply(call({**key,'offset':24576}),True)
        for page,at in [(page0,0),(page1,24576)]:
            assert page['offset']==at and page['transfer']=='A' and page['size']==len(content)
            assert page['sha256']==sha256(content).hexdigest()
            assert base64.b64decode(page['data'],validate=True)==content[at:at+24576]
        assert [x['method'] for x in requests]==['token','resource']
        time.sleep(3.1)
        reply(call({**key,'transfer':'B','reference':'denied'}),False)
        assert [x['method'] for x in requests]==['token','resource','token','resource']
        assert requests[-1]['token_number']==2 and not errors,errors
        return {'domain':domain,'kind':kind,'fixture_requests':requests,'wire':wire,
            'sha256':sha256(content).hexdigest(),'bytes':len(content),'ws_ack_during_rest':True,
            'wrong_identity_requests':0,'http_403_retries':0,'token_issuances':len(issued)}
    finally:
        release.set();shutdown.set();proc.stdin.close()
        try:proc.wait(timeout=4)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        ws.shutdown();server.shutdown();server.server_close()
