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
    entered,release,ack,shutdown,cancel_entered,cancel_closed=(threading.Event() for _ in range(6))
    requests,wire,errors=[],[],[]
    issued=[]
    upload_entered,upload_closed=threading.Event(),threading.Event()

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
            raw=self.rfile.read(int(self.headers['Content-Length']))
            if self.path=='/open-apis/im/v1/files':
                assert self.headers['Authorization']=='Bearer '+issued[-1]
                assert self.headers['Content-Type'].startswith('multipart/form-data; boundary=')
                assert b'original-upload-page'*2000 in raw
                requests.append({'method':'upload','domain':domain,'token_number':len(issued)})
                upload_entered.set()
                self.connection.settimeout(4)
                try:
                    assert self.connection.recv(1)==b'', 'cancelled upload kept its HTTP connection'
                except ConnectionResetError:
                    pass
                upload_closed.set()
                return
            v=json.loads(raw)
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
            if key=='cancelled':
                cancel_entered.set()
                self.connection.settimeout(4)
                try:
                    assert self.connection.recv(1)==b'', 'cancelled resource kept its HTTP connection'
                except ConnectionResetError:
                    # Killing curl closes its socket with RST on Windows and EOF on Unix.
                    pass
                cancel_closed.set()
                return
            assert key==native_key
            if not entered.is_set():
                entered.set();release.wait(8)
            self.answer(content)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),HTTP)
    for obj in (ws,server):threading.Thread(target=obj.serve_forever,daemon=True).start()
    grants=['gateway.inbound','gateway.media','gateway.send','media.open','forget.owner']
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
            'extension_points':[],'host_schema_revision':2,'method_revisions':[{'name':m,'revision':1} for m in ['initialize','gateway.inbound','gateway.media','gateway.plan_send','gateway.dispatch_part','gateway.read_text','gateway.read_mentions','gateway.prepare_part','media.open','forget.request']]}})
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
        cancelled = call({**key,'transfer':'C','reference':'cancelled'})
        assert cancel_entered.wait(6), 'resource was not dispatched'
        send({'jsonrpc':'2.0','method':'forget.request','id':'forget-original',
              'params':{'key':'original-forget','watermark':17,'sources':[12]}})
        reply(cancelled, False)
        forget = read()
        assert forget['id']=='forget-original' and forget['result']['key']=='original-forget'
        assert forget['result']['watermark']==17 and cancel_closed.wait(1)
        count = len(requests)
        reply(call({**key,'transfer':'C','reference':'cancelled','offset':24576}),False)
        assert len(requests)==count, 'forgotten page restarted native download'
        restored=reply(call({**key,'transfer':'D'}),True)
        assert restored['sha256']==sha256(content).hexdigest()
        assert len(issued)==3, 'forget did not clear the application token'
        count = len(requests)
        paged_text = text_pages(send, read, app)
        from feishu_mentions import annotation_pages
        paged_mentions = annotation_pages(send, read, app)
        assert len(requests) == count, 'text planning caused a native effect'
        from feishu_upload import upload_pages
        upload=upload_pages(send,read,ns,domain,app,tenant,upload_entered,upload_closed)
        assert [r['method'] for r in requests[count:]]==['token','upload']
        return {'upload':upload,'domain':domain,'kind':kind,'fixture_requests':requests,'wire':wire,
            'sha256':sha256(content).hexdigest(),'bytes':len(content),'ws_ack_during_rest':True,
            'wrong_identity_requests':0,'http_403_retries':0,'token_issuances':len(issued),'forget_cancelled_http':True,'forgotten_page_rejected':True,'paged_text':paged_text,'paged_mentions':paged_mentions}
    finally:
        release.set();shutdown.set();proc.stdin.close()
        try:proc.wait(timeout=4)
        except subprocess.TimeoutExpired:proc.kill();proc.wait()
        ws.shutdown();server.shutdown();server.server_close()


def cleanup_without_credentials(binary):
    binding = {'namespace':'fs.cleanup','grants':['forget.owner'],
               'manifest_revision':'f'*64,'declarations':[]}
    env = {k:v for k,v in os.environ.items() if not k.startswith('YUKI_FEISHU_')}
    env.update(YUKI_PLUGIN_BINDING=json.dumps(binding),YUKI_PLUGIN_START_MODE='erasure_only')
    initialization = {'jsonrpc':'2.0','id':1,'result':{'schema_revision':1,
        'version':{'major':1,'minor':0},
        **{k:binding[k] for k in ['namespace','grants','manifest_revision']},
        'features':['initialize'],'extension_points':[],'host_schema_revision':2,
        'method_revisions':[{'name':m,'revision':1} for m in ['initialize','forget.request']]}}
    forget = {'jsonrpc':'2.0','id':'cleanup','method':'forget.request',
              'params':{'key':'original-cleanup','watermark':17,'sources':[12]}}
    result = subprocess.run([binary],input='\n'.join(json.dumps(v) for v in [initialization,forget])+'\n',
                            capture_output=True,text=True,encoding='utf8',env=env,timeout=4)
    assert result.returncode==0,result.stderr
    frames=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(frames)==2 and frames[0]['method']=='initialize'
    assert frames[1]['id']=='cleanup' and frames[1]['result']['key']=='original-cleanup'
    assert frames[1]['result']['watermark']==17
    return {'status':'PASS','credentials_supplied':False,'native_network_requests':0,'wire':frames}


def text_pages(send, read, app):
    """A forgotten page cannot advance a later plan, even if its response arrives late."""
    content = ("雪🌨original text" * 400000).encode()
    digest = sha256(content).hexdigest()

    def plan(ident):
        send(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "gateway.plan_send",
                "params": {
                    "handle": "plan-" + ident,
                    "arguments": {
                        "route": {
                            "bot": app,
                            "scope": "group",
                            "chat": "oc_original",
                            "topic": None,
                        },
                        "message": {},
                        "text_source": {"bytes": len(content), "sha256": digest},
                    },
                },
            }
        )

    def page(request, *, wrong_done=False):
        assert request["method"] == "gateway.read_text"
        params = request["params"]
        assert params["length"] == 12288
        offset = params["offset"]
        data = content[offset : offset + params["length"]]
        send(
            {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {
                    "offset": offset,
                    "total": len(content),
                    "sha256": digest,
                    "bytes": base64.b64encode(data).decode(),
                    "done": wrong_done or offset + len(data) == len(content),
                },
            }
        )

    plan("cancelled-plan")
    page(read())
    old = read()
    assert old["params"]["offset"] == 12288
    send(
        {
            "jsonrpc": "2.0",
            "id": "erase-text",
            "method": "forget.request",
            "params": {"key": "text-erasure", "watermark": 18, "sources": [12]},
        }
    )
    cancelled = read()
    ack = read()
    assert cancelled["id"] == "cancelled-plan" and "error" in cancelled
    assert ack["id"] == "erase-text" and ack["result"]["key"] == "text-erasure"
    assert ack["result"]["watermark"] == 18
    started = time.monotonic()
    plan("fresh-plan")
    fresh = read()
    assert fresh["params"]["offset"] == 0
    page(old)
    page(fresh)
    pages = 1
    while True:
        frame = read()
        if frame.get("method") == "gateway.read_text":
            assert frame["params"]["handle"] == "plan-fresh-plan"
            assert frame["params"]["offset"] == pages * 12288
            page(frame)
            pages += 1
        else:
            assert frame["id"] == "fresh-plan" and "result" in frame
            parts = frame["result"]["parts"]
            break
    offset = 0
    for part in parts:
        selected = part["text_range"]
        assert "text" not in part
        assert selected["start"] == offset
        piece = content[offset : offset + selected["length"]]
        piece.decode("utf8")
        assert sha256(piece).hexdigest() == selected["sha256"]
        offset += len(piece)
    assert offset == len(content)
    elapsed = time.monotonic() - started
    assert elapsed < 10, {"paged_plan_seconds": elapsed}
    plan("invalid-page")
    page(read(), wrong_done=True)
    rejected = read()
    assert rejected["id"] == "invalid-page" and "error" in rejected
    return {
        "status": "PASS",
        "bytes": len(content),
        "pages": pages,
        "elapsed_seconds": elapsed,
        "sha256": digest,
        "forgotten_plan_cancelled": True,
        "late_page_did_not_advance_fresh_plan": True,
        "malformed_page_rejected": True,
        "native_effects": 0,
    }
