"""Drive two installed Rust packages through one signed Host using loopback upstreams."""

import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib
import uuid


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wait_until(action, seconds=35):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if value := action():
            return value
        time.sleep(.08)
    raise TimeoutError('waiting for ' + action.__name__)


def exchange(frames, method, direction):
    for index, row in enumerate(frames):
        frame = row['frame']
        if row['direction'] == direction and frame.get('method') == method:
            reply = next(item['frame'] for item in frames[index+1:]
                         if item['direction'] != direction and item['frame'].get('id') == frame['id']
                         and ('result' in item['frame'] or 'error' in item['frame']))
            yield frame, reply


DENIALS = {
    'denied-send': 'gateway_send_not_granted',
    'unsupported-emoji': 'gateway_media_unsupported',
    'missing-media-reader': 'gateway_media_read_not_granted',
}
MEDIA_DENIALS = {'unsupported-emoji', 'missing-media-reader'}


def preview_host(root, archive, case, consumer, work):
    sys.path.insert(0, str(root/'compat/base'))
    from verify_dist import verify, native_target
    lock = consumer
    if case in DENIALS:
        contract = 'media-refusal' if case in MEDIA_DENIALS else 'gateway-refusal'
        lock = json.loads((root/'compat'/contract/'source.lock.json').read_bytes())
    platform = lock['platforms']['-'.join(native_target())]
    key = work/'signer.pub'
    key.write_bytes((platform['signer'] + '\n').encode('ascii'))
    assert digest(key) == platform['signer_sha256']
    candidate = verify(archive, key, lock['source_commit'], platform['sha256'],
                       lock['fixtures_sha256'], destination=work/'host')
    assert candidate['dirty'] is False and candidate['source_tree_sha256']==lock['source_tree_sha256']
    assert candidate['sdk_versions']==lock['sdk'] and candidate['members']['sdk/yuki-plugin-sdk-1.0.0-alpha.14.crate']['sha256']==lock['rust_crate_sha256']
    assert candidate['members']['sdk/handshake.ndjson']['sha256']==lock['golden_sha256']
    executable = 'yuki-core.exe' if os.name == 'nt' else 'yuki-core'
    host = work/'host/bin'/executable
    assert digest(host) == platform['binary_sha256']
    return host, lock, candidate['host_schema_sha256']


def published_host(root, archive, work):
    import zipfile
    pin = root/'compat/stable-1.0'
    lock = json.loads((pin/'source.lock.json').read_bytes())
    platform, = (p for p in lock['platforms'].values() if p['archive'] == archive.name)
    key = pin/'signer.pub'
    assert digest(key) == lock['signer_sha256']
    raw = subprocess.check_output([sys.executable, pin/'verify_base.py', archive, '--public-key', key,
                                   '--sha256', platform['sha256'], '--commit', lock['source_commit']])
    manifest = json.loads(raw)
    host = work/Path(manifest['binary']).name
    with zipfile.ZipFile(archive) as z:
        host.write_bytes(z.read(manifest['binary']))
    assert digest(host) == platform['binary_sha256']
    host.chmod(0o755)
    return host, lock, lock['schema_sha256']


def run(root, assets, archive, out, case, *, rollback=None):
    sys.path.insert(0, str(root/'ci'))
    from personal_preview import free_address

    out.mkdir()
    work = out/'work'
    work.mkdir()
    consumer = json.loads((root/'compat/base/source.lock.json').read_bytes())
    host, lock, schema = (published_host(root, archive, work) if rollback is not None
                          else preview_host(root, archive, case, consumer, work))
    package_hash = {}
    for unit in ['telegram', 'web-fetch']:
        package = assets/unit
        manifest = json.loads((package/'package-manifest.json').read_bytes())
        assert manifest['unit_id'] == unit and all(cmd['exit_code'] == 0 for cmd in manifest['commands'])
        assert all(digest(package/name) == h for name,h in manifest['artifacts'].items())
        dependencies = tomllib.loads((package/'Cargo.lock').read_text(encoding='utf-8'))['package']
        sdk, = [dep for dep in dependencies if dep['name'] == 'yuki-plugin-sdk']
        package_pin = lock if rollback is not None and unit == 'telegram' else consumer
        assert sdk['checksum'] == package_pin['rust_crate_sha256'] and sdk['version'] == package_pin['sdk']['rust']
        package_hash[unit] = {'version': manifest['version'], 'artifacts': manifest['artifacts'],
                              'manifest_sha256': digest(package/'package-manifest.json')}

    data, source = work/'data', 'http://93.184.216.34:8100/document'
    page = ('original-' + uuid.uuid4().hex + '\n' + '取件 ' * 220).encode()
    models, native, requests, offsets, reads, failures = [], [], [], [], [], []
    checked_offsets = set()
    cursor = 0
    original = bytearray()
    result_ref = {}
    denial = {}
    second_entry = threading.Event()
    replay = threading.Event()
    replayed = threading.Event()
    done = threading.Event()
    fetch_started = threading.Event()
    allow_response = threading.Event()
    text = None

    class Peer(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def respond(self, payload, mime='application/json'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except ConnectionError:
                pass

        def handle(self):
            try:
                super().handle()
            except ConnectionResetError:
                if getattr(self,'command',None) and self.command not in ('POST','GET','CONNECT'):
                    raise

        def do_CONNECT(self):
            if self.path != '93.184.216.34:8100':
                return self.send_error(403)
            requests.append(['CONNECT', self.path])
            self.send_response(200)
            self.end_headers()
            self.close_connection = False

        def do_GET(self):
            if self.path != '/document' or self.headers.get('Host') != '93.184.216.34:8100':
                return self.send_error(404)
            requests.append(['GET', self.path])
            fetch_started.set()
            if case == 'revoked' and not allow_response.wait(20):
                return self.send_error(503)
            self.respond(page, 'text/plain; charset=utf-8')

        def model(self, body):
            nonlocal cursor, text
            messages = body['messages']
            models.append(body)
            write(out/'model.json', models)
            n = len(models)
            tool = None
            if case in ('swapped','erased-readback') and n == 3:
                assert any('second private source' in str(m.get('content','')) for m in messages)
                tool=('read_tool_artifact',{'handle':result_ref['handle'], 'operation':'get','path':['data','original_hex'],'offset':0,'limit':100})
            elif n == 1:
                tool = ('web_fetch', {'url':source})
            else:
                prev = next(m for m in reversed(messages) if m.get('tool_call_id') == 'joint-'+str(n-1))
                receipt = json.loads(prev['content'])
                result = receipt.get('result', receipt)
                if case in ('swapped','erased-readback'):
                    if n==2:
                        result_ref.update(result['artifact'])
                        second_entry.set()
                    else:
                        assert n==4 and receipt['state']=='failed' and result.get('error')!='invalid_tool_arguments', receipt
                        done.set()
                elif case in DENIALS and text is not None:
                    assert receipt['state'] == 'failed' and result == {'error': DENIALS[case]}, receipt
                    denial['original'] = receipt
                    done.set()
                elif case=='missing-method' and text is not None:
                    assert receipt['state']=='unknown' and result['plan']['state']=='unknown' and result['plan']['result']=={'unavailable':True},receipt
                    done.set()
                elif case == 'revoked':
                    assert receipt.get('state') in ('failed','cancelled','unknown') or result.get('error'), receipt
                    done.set()
                elif n == 2:
                    result_ref.update(result['artifact'])
                elif text is None:
                    if case == 'wrong-handle':
                        assert receipt.get('state') == 'failed' and result.get('error')!='invalid_tool_arguments', receipt
                        done.set()
                    else:
                        section = result
                        if 'value' not in section and isinstance(section.get('data'),dict):
                            section = section['data']
                        fragment = section['value']
                        assert isinstance(fragment,str) and len(fragment)>0
                        reads.append({'offset':cursor, 'value':fragment,'next_offset':section['next_offset']})
                        original.extend(bytes.fromhex(fragment))
                        cursor += len(fragment)
                        if section['next_offset'] is None:
                            assert bytes(original) == page
                            marker = original.decode().splitlines()[0]
                            text = marker + '雪' * (8197-len(marker))
                            arguments = {'text':text}
                            if case == 'unsupported-emoji':
                                arguments['emoji'] = {'goal':'source found'}
                            elif case == 'missing-media-reader':
                                arguments = {'artifact_id':'unread-version','attachment_kind':'file'}
                            tool = ('send', arguments)
                        else:
                            assert section['next_offset'] == cursor
                else:
                    expected = 'unknown' if case=='lost-second' else 'confirmed'
                    assert receipt['state'] == expected, receipt
                    done.set()
                if tool is None and text is None and not done.is_set() and case not in ('swapped','erased-readback'):
                    handle = result_ref['handle']
                    if case=='wrong-handle':
                        handle = str(uuid.uuid4())
                    tool = ('read_tool_artifact', {'handle':handle, 'operation':'get',
                            'path':['data','original_hex'],'offset':cursor,'limit':1000})
            msg = {'role':'assistant','content':'done'}
            if tool:
                assert n < 18
                msg.update(content=None,tool_calls=[{'id':'joint-'+str(n),'type':'function',
                           'function':{'name':tool[0],'arguments':json.dumps(tool[1],ensure_ascii=False)}}])
            return {'id':'joint-result','choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if tool else 'stop'}],
                    'usage':{'prompt_tokens':2,'completion_tokens':2,'total_tokens':4}}

        def do_POST(self):
            try:
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/model':
                    self.respond(self.model(body))
                elif self.path == '/bot101:fixture/getMe':
                    self.respond({'ok':True,'result':{'id':101,'is_bot':True,'username':'OriginBot'}})
                elif self.path == '/bot101:fixture/getUpdates':
                    offset=body.get('offset',0)
                    offsets.append(offset)
                    if offset>=52 and offset not in checked_offsets:
                        frames=[json.loads(line) for line in (out/'telegram.jsonl').read_bytes().splitlines()]
                        pairs=list(exchange(frames,'gateway.inbound','from_plugin'))
                        assert any(req['id']==offset-1 and rep['result']['accepted'] for req,rep in pairs)
                        checked_offsets.add(offset)
                    update={'update_id':51,'message':{'message_id':72,'date':int(time.time()),'from':{'id':8},
                            'chat':{'id':8,'type':'private'},'text':'read original page and reply'}}
                    if offset>51:
                        time.sleep(.08)
                    updates=[update] if offset<=51 else []
                    if offset==52 and second_entry.is_set() and (case=='swapped' or case=='erased-readback' and replay.is_set() and replayed.is_set()):
                        sender=9 if case=='swapped' else 8
                        updates=[{'update_id':52,'message':{'message_id':73,'date':update['message']['date'],
                                 'from':{'id':sender},'chat':{'id':sender,'type':'private'},'text':'second private source'}}]
                    if replay.is_set() and not replayed.is_set():
                        updates=[update]
                        replayed.set()
                    try:
                        self.respond({'ok':True,'result':updates})
                    except ConnectionError:
                        if offset<=51: raise
                elif self.path == '/bot101:fixture/sendMessage':
                    gateway_rows=[json.loads(line) for line in (out/'telegram.jsonl').read_bytes().splitlines()]
                    plan,=exchange(gateway_rows,'gateway.plan_send','from_host')
                    assert plan[1]['result']['parts'][len(native)]['text']==body['text']
                    dispatch=[r['frame'] for r in gateway_rows if r['direction']=='from_host' and r['frame'].get('method')=='gateway.dispatch_part']
                    assert len(dispatch)==len(native)+1 and dispatch[-1]['params']['arguments']['part_ordinal']==len(native)
                    native.append(body)
                    if case=='lost-second' and len(native)==2:
                        self.close_connection=True
                        self.connection.shutdown(socket.SHUT_RDWR)
                        return
                    self.respond({'ok':True,'result':{'message_id':700+len(native),'chat':{'id':8}}})
                else:
                    self.send_error(404)
            except Exception as exc:
                failures.append(repr(exc))
                write(out/'fixture-errors.json',failures)
                done.set()
                self.send_error(500)

    http = ThreadingHTTPServer(('127.0.0.1',0),Peer)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    api='http://127.0.0.1:'+str(http.server_port)
    tg={'YUKI_TELEGRAM_API':api,'YUKI_TELEGRAM_BOT_ID':'101','YUKI_TELEGRAM_TOKEN':'101:fixture',
        'YUKI_TELEGRAM_STATE':str(work/'cursor')}
    web={'YUKI_WEB_FETCH_HTTP_PROXY':api,'YUKI_WEB_FETCH_NO_PROXY':''}
    env={**os.environ,**tg,**web,'NO_PROXY':'127.0.0.1,localhost','no_proxy':'127.0.0.1,localhost'}

    def cli(*args, check=True):
        proc=subprocess.run([host,'--data',data,*args],cwd=work,env=env,capture_output=True,timeout=20)
        if proc.returncode:
            if check: raise RuntimeError(proc.stderr.decode(errors='replace')[:800])
            return None
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    @contextmanager
    def running():
        with (out/'host.log').open('ab') as log:
            proc=subprocess.Popen([host,'--data',data,'run'],cwd=work,env=env,stdout=log,stderr=log)
        try:
            def available():
                if proc.poll() is not None:
                    raise RuntimeError((out/'host.log').read_text(encoding='utf8')[-900:])
                return cli('operator','database-info',check=False)
            wait_until(available,15)
            yield
        finally:
            if proc.poll() is None:
                cli('operator','shutdown',check=False)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()

    try:
        cli('init')
        cfg=data/'yuki.toml'
        top=cfg.read_text(encoding='utf-8').replace('"127.0.0.1:0"',json.dumps(free_address())).replace('mode = "hybrid"','mode = "lexical-only"')
        top += '\n[main]\nendpoint='+json.dumps(api+'/model')+'\nmodel="fixture"\nname="Yuki"\nmax_output=12000\nroot_slots=24\nroot_tool_calls=24\nmerge_ms=1\nmax_input_units=1200000\nresult_page_budget=2000\nresult_storage_bytes=262144\n'
        cfg.write_text(top,encoding='utf-8')
        with running():
            person=str(uuid.uuid4())
            cli('operator','person','create',person)
            cli('operator','account','open','telegram','tg.bot101','8','1','--person',person,'--start','1')
            if case=='swapped':
                second_person=str(uuid.uuid4())
                cli('operator','person','create',second_person)
                cli('operator','account','open','telegram','tg.bot101','9','1','--person',second_person,'--start','1')
            bot=cli('operator','account','open','telegram','tg.bot101','101','1','--start','1')['assignment']
        installed=[]
        for unit,namespace,environment in [('web-fetch','official.web-fetch',web),('telegram','tg.bot101',tg)]:
            package=assets/unit
            config=tomllib.loads((package/'plugin.toml').read_text(encoding='utf-8'))
            binary=package/(config['program']+('.exe' if os.name=='nt' else ''))
            if rollback is not None and unit == 'telegram':
                installed_binary = work/'installed'/binary.name
                installed_binary.parent.mkdir()
                shutil.copy2(binary, installed_binary)
                assert digest(installed_binary) == digest(binary)
                binary = installed_binary
            state_dir=work/('state-'+unit)
            state_dir.mkdir()
            entry={'id':unit,'namespace':namespace,'program':sys.executable,'args':[str(root/'tests/peers/base_relay.py'),
                   str(binary),str(out/(unit+'.jsonl')),str(state_dir),case if unit=='telegram' else 'none'],'env':list(environment),'grants':config['grants']}
            if unit=='telegram':
                entry.update(platform='telegram',bot_stage=bot,grants=['gateway.inbound'])
                if case != 'denied-send':
                    entry['grants'].append('gateway.send')
                if case in MEDIA_DENIALS:
                    entry['grants'].append('gateway.media')
            installed.append({'unit':unit,'namespace':namespace,'grants':entry['grants'],'environment_names':list(environment),'program_digest':digest(binary)})
            top += '\n[[plugins]]\n'+'\n'.join(k+'='+json.dumps(v) for k,v in entry.items())+'\n'
            if unit=='telegram' and case in MEDIA_DENIALS:
                top += '[plugins.gateway_media]\napplication="101"\n'
            if unit=='web-fetch':
                tools=(package/'plugin.toml').read_text(encoding='utf-8').split('[[tools]]',1)[1]
                top += '[[plugins.tools]]'+tools
        cfg.write_text(top,encoding='utf-8')
        write(out/'installed.json',installed)
        def inventory(*, live=False):
            files={}
            for folder in ('state-telegram','state-web-fetch','cursor'):
                files[folder]={}
                for f in (work/folder).rglob('*'):
                    if not f.is_file():
                        continue
                    name=f.relative_to(work/folder).as_posix()
                    if live and folder=='cursor' and name=='101.lock':
                        assert f.stat().st_size==0
                        files[folder][name]={'bytes':0,'access':'process lock held'}
                    else:
                        files[folder][name]=digest(f)
            return files
        with running():
            if case in ('revoked','erased-readback'):
                assert (fetch_started if case=='revoked' else second_entry).wait(20)
                gateway_frames = [json.loads(line) for line in (out/'telegram.jsonl').read_bytes().splitlines()]
                inbound, = exchange(gateway_frames,'gateway.inbound','from_plugin')
                event = inbound[1]['result']['event']
                erasure = cli('operator','privacy','erase','joint-page-source',person,json.dumps([event]))
                write(out/'erasure.json',erasure)
                allow_response.set()
                def disposition():
                    frames=[json.loads(line) for line in (out/'web-fetch.jsonl').read_bytes().splitlines()]
                    return any(item['direction']=='from_plugin' and item['frame'].get('result',{}).get('error')=='scope_unavailable' for item in frames)
                if case=='revoked': wait_until(disposition,20)
            elif not done.wait(45):
                raise TimeoutError('Main did not finish')
            assert not failures
            assert case in ('revoked','erased-readback') or done.is_set(), 'Main did not finish; inspect the last original wire and operation'
            assert not failures,failures
            ack_offset = 53 if case=='swapped' else 52
            wait_until(lambda: ack_offset in offsets)
            live_inventory=inventory(live=True)
            for unit in package_hash:
                (out/(unit+'.kill')).touch()
            wait_until(lambda: all((out/(u+'.killed')).is_file() for u in package_hash))
        after_kill = inventory()
        assert live_inventory['state-telegram']==after_kill['state-telegram'] and live_inventory['state-web-fetch']==after_kill['state-web-fetch']
        assert set(live_inventory['cursor'])==set(after_kill['cursor'])
        assert all(after_kill['cursor'][k]==v for k,v in live_inventory['cursor'].items() if k!='101.lock')
        assert after_kill['cursor']['101.lock']==hashlib.sha256(b'').hexdigest()
        if rollback is not None:
            previous = rollback/'telegram'/('yuki-telegram.exe' if os.name=='nt' else 'yuki-telegram')
            upgraded = assets/'telegram'/previous.name
            assert digest(installed_binary) == digest(upgraded)
            shutil.copy2(previous, installed_binary)
            assert digest(installed_binary) == digest(previous)
            write(out/'rollback.json', {'from':digest(upgraded),'to':digest(previous),
                  'web_fetch':installed[0]['program_digest'],'before_restart':after_kill})
        replay.set()
        before=(len(models),len(native),len(requests))
        offset_count=len(offsets)
        with running():
            if case in DENIALS:
                original_receipt = denial['original']
                recovered = cli('operator','effect','read',original_receipt['namespace'],original_receipt['id'],person)
                assert recovered['id'] == original_receipt['id'] and recovered['result'] == original_receipt['result']
                assert recovered['state'] == original_receipt['state']
                denial['after_restart'] = recovered
            if case=='erased-readback':
                assert done.wait(25) and not failures,failures
                ack_offset=53
            wait_until(lambda:replayed.is_set() and offsets[offset_count:].count(ack_offset)>=2)
        after_reopen=inventory()
        assert all(after_reopen[k]==v for k,v in after_kill.items() if case!='erased-readback' or k!='cursor')
        assert not after_kill['state-telegram'] and not after_kill['state-web-fetch']
        cursor_file = work/'cursor/101.offset'
        assert int(cursor_file.read_text())==ack_offset
        assert all(f in ('101.offset','101.lock') for f in after_kill['cursor']), after_kill
        assert all((work/'cursor'/f).stat().st_size==0 for f in after_kill['cursor'] if f!='101.offset')
        assert before==(len(models)-(2 if case=='erased-readback' else 0),len(native),len(requests))
        assert not failures, failures
        assert requests==[['CONNECT','93.184.216.34:8100'],['GET','/document']]
        traces={unit:[json.loads(v) for v in (out/(unit+'.jsonl')).read_bytes().splitlines()] for unit in package_hash}
        calls=list(exchange(traces['web-fetch'],'tool.call','from_host'))
        checks=list(exchange(traces['web-fetch'],'tool.status','from_plugin'))
        assert len(calls)==1 and len(checks)==2 and all(c[0]['params']['handle']==calls[0][0]['params']['handle'] for c in checks)
        ingress=list(exchange(traces['telegram'],'gateway.inbound','from_plugin'));assert len(ingress)==(2 if case in ('swapped','erased-readback') else 1) and all(pair[1]['result']['accepted'] for pair in ingress)
        parts=list(exchange(traces['telegram'],'gateway.dispatch_part','from_host'))
        assert len(parts)==len(native)=={'confirmed':3,'lost-second':2,'wrong-handle':0,'revoked':0,'swapped':0,'missing-method':0,'erased-readback':0,**dict.fromkeys(DENIALS,0)}[case]
        assert all(n['chat_id']=='8' for n in native)
        states=[r['result'] for _,r in parts]
        if case=='missing-method':
            original_negotiation=[x for x in traces['telegram'] if x['direction']=='before_fault']
            assert original_negotiation and all(any(m['name']=='gateway.dispatch_part' for m in x['frame']['result']['method_revisions']) for x in original_negotiation)
            plan,=exchange(traces['telegram'],'gateway.plan_send','from_host')
            assert plan[1]['error']['code']==-32601 and not parts
        if case in DENIALS:
            assert not list(exchange(traces['telegram'],'gateway.plan_send','from_host')) and not parts
            assert len(reads)>=2 and bytes(original)==page and denial['after_restart']
            write(out/'denial.json',denial)
        if case in ('confirmed','lost-second'):
            assert len(reads)>=2 and bytes(original)==page
            assert [p['text'] for p in native]==[text[i:i+4096] for i in range(0,len(text),4096)][:len(parts)]
            assert states==[{'state':'unknown'} if case=='lost-second' and i==1 else {'state':'confirmed','locator':'8:'+str(701+i)} for i in range(len(parts))]
        write(out/'result.json',{'case':case,'status':'PASS','published':lock['published'],'source':lock['source_commit'],
              'host':digest(host),'sdk':lock['rust_crate_sha256'],'schema':schema,
              'consumer_sdk':consumer['rust_crate_sha256'], 'sdk_by_package':{u:(lock if rollback is not None and u=='telegram' else consumer)['rust_crate_sha256'] for u in package_hash},'packages':package_hash,'event':ingress[0][1]['result']['event'],'web_status_checks':len(checks),
              'ack_offsets_after_original_receipt':sorted(checked_offsets),'original_pages':len(reads),'page_bytes':len(page),'page_sha256':hashlib.sha256(page).hexdigest(),
              'native_parts':states,'confirmed_offset_after_restart':ack_offset,'redelivered_old_update':replayed.is_set(),'post_restart_effects':0,
              'live_private_directories':live_inventory,'private_directories_after_kill':after_kill,'private_directories_after_restart':after_reopen,'killed_children':{u:int((out/(u+'.killed')).read_text()) for u in package_hash}})
    finally:
        allow_response.set()
        write(out/'native.json',{'native_telegram':native,'original_http':requests,'offsets':sorted(set(offsets)),'artifact_pages':reads})
        http.shutdown()
        http.server_close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ['root','assets','archive','out']:
        parser.add_argument(name,type=lambda value:Path(value).resolve())
    parser.add_argument('--case',choices=['confirmed','lost-second','wrong-handle','revoked','swapped','missing-method','erased-readback',*DENIALS],required=True)
    args=parser.parse_args()
    run(args.root,args.assets,args.archive,args.out,args.case)
