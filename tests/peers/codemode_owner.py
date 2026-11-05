"""HJW Windows Host + Arch real Rust/Monty candidate scenarios, public operators only."""
import os,pathlib,subprocess,json,uuid,time,hashlib,queue,threading,sys
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=pathlib.Path(os.environ.get('YUKI_CODE_FIXTURE_ROOT','D:/yuki-extension-tests/core034-public-help'));exe=root/'feed-fix-host/bin/yuki-core.exe'
assert hashlib.sha256(exe.read_bytes()).hexdigest()=='502f190d036f55c9f4348aa832642f82aa3bc5bb1ae153ac100bffc87f68052b'
mode=sys.argv[1]; work=root/sys.argv[2];work.mkdir();data=work/'owner';wires=[];deliveries=[]
assert mode in {'normal','before-feed','after-feed-twice','unknown','missing-runtime','malformed-frame'}
keepalive=subprocess.Popen(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec','sleep','3600'])
setup=subprocess.run(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec','/bin/sh'],input=(root/'runtime-setup.sh').read_bytes(),capture_output=True)
assert setup.returncode==0,setup.stderr.decode('utf-8','replace')
linux_plugin=os.environ.get('YUKI_CODE_LINUX_PLUGIN','/var/tmp/yuki-ext023/rust-plugin-01/target-linux-04/debug/yuki-codemode')
def native_inventory():
 code="import pathlib,hashlib,json,subprocess; p=pathlib.Path("+repr(linux_plugin)+"); r=subprocess.run(['docker','--host','unix:///run/yuki-ext023-docker/api.sock','ps','-aq'],check=True,capture_output=True,text=True); print(json.dumps({'plugin_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'containers':sorted(r.stdout.split())}))"
 return json.loads(subprocess.check_output(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec','python3','-c',code]))
initial_inventory=native_inventory()
assert initial_inventory['plugin_sha256']==os.environ.get('YUKI_CODE_PLUGIN_SHA256','f26e88f764a44c666cdee68b012e28d422ebd46a9ffbeae5240bee71d33d6b0d')

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  if self.path=='/binding':
   deliveries.append(body)
   if mode=='unknown':
    self.close_connection=True;return
   result={'accepted':body['operation'],'sequence':len(deliveries)}
  else:
   wires.append(body)
   if len(wires)==1:name,args='task_control',{'action':'accept','goal':'inspect frozen API via real Rust SDK'}
   elif len(wires)==2:name,args='code_a',{'code':"a = yuki_send({'text': 'same original arguments'})\nb = yuki_send({'text': 'same original arguments'})\n[a,b]"}
   else:name=None
   msg={'role':'assistant','content':'done' if name is None else None}
   if name:msg['tool_calls']=[{'id':'call-'+str(len(wires)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]
   result={'id':'fixture-'+str(len(wires)),'object':'chat.completion','model':'fixture','choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if name else 'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
  raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
srv=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=srv.serve_forever,daemon=True).start()
def cmd(*args,check=True):
 r=subprocess.run([str(exe),'--data',str(data),*map(str,args)],capture_output=True,text=True,encoding="utf-8",timeout=20)
 if check and r.returncode:raise RuntimeError(str(args[:3])+': '+r.stderr)
 return r
def op(*a):return json.loads(cmd('operator',*a).stdout)
cmd('init');(data/'SOUL.md').write_text('Fixed public fixture character.');cfg=data/'yuki.toml'
plugin='D:/yuki-extension-tests/codemode-bootstrap-01/target-catalog-03/debug/examples/catalog_probe.exe'
text=cfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"')
text+=f'\n[main]\nendpoint="http://127.0.0.1:{srv.server_port}/v1/chat/completions"\nbinding_endpoint="http://127.0.0.1:{srv.server_port}/binding"\nmodel="fixture"\nname="Yuki"\nmax_output=512\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=4000000\nmerge_ms=1\ncode_tool="code_a"\n'
text+='\n[[plugins]]\nid="code_a"\nnamespace="code_a"\nprogram='+json.dumps(sys.executable)+'\nargs='+json.dumps([str(pathlib.Path(__file__).with_name('codemode_wsl.py')),str(work/'wire.jsonl'),mode,'/var/tmp/yuki-ext023/no-such-runtime.json' if mode=='missing-runtime' else '/var/tmp/yuki-ext023/rust-plugin-01/runtime.json',os.environ.get('YUKI_CODE_LINUX_PLUGIN','/var/tmp/yuki-ext023/rust-plugin-01/target-linux-04/debug/yuki-codemode')])+'\ngrants=["tool.call","composition.read","composition.execute","forget.owner"]\n'
contract=json.loads((root/'runtime-contract.json').read_bytes())
text+='[plugins.composition]\ntool="code_a"\n'+'\n'.join(k+'='+json.dumps(contract[k]) for k in ['abi','engine_sha256','codec_sha256','launcher_sha256'])+'\n'
text+='[[plugins.tools]]\nname="code_a"\ndescription="Rust isolated Monty candidate"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={code={type="string"}},required=["code"],additionalProperties=false}\n';cfg.write_text(text);(work/'host-config.toml').write_text(text)
with (work/'host.txt').open('wb') as log:p=subprocess.Popen([str(exe),'--data',str(data),'run'],stdout=log,stderr=log)
try:
 for i in range(100):
  if cmd('operator','host','status',check=False).returncode==0:break
  time.sleep(.1)
 actor=str(uuid.uuid4());op('person','create',actor)
 user=op('account','open','qq','code-fixture','200',1,'--person',actor,'--start',1)
 bot=op('account','open','qq','code-fixture','100',1,'--start',1)
 frame={'source':'code-catalog-probe','account':user['account'],'bot_stage':bot['assignment'],'kind':'message','reply_bot':'100','occurred':100,'observed':100,'segments':[{'type':'text','text':'catalog probe'}]}
 event=op('ingress','record',json.dumps(frame),'--accept')
 restarts=2 if mode=='after-feed-twice' else 1 if mode=='before-feed' else 0
 for cut in range(1,restarts+1):
  for _ in range(600):
   if (work/f'cut-{cut}.json').exists():break
   time.sleep(.1)
  assert (work/f'cut-{cut}.json').exists(),'crash barrier not reached'
  assert len(deliveries)==1,deliveries
  execution=deliveries[0]['execution']
  (work/f'before-{cut}.json').write_text(json.dumps(op('main','inspect',execution),indent=2))
  p.kill();p.wait()
  for _ in range(150):
   if (work/f'transport-exit-{cut-1}.json').exists():break
   time.sleep(.1)
  assert (work/f'transport-exit-{cut-1}.json').exists(),'old plugin failed to stop'
  with (work/f'host-restart-{cut}.txt').open('wb') as log:p=subprocess.Popen([str(exe),'--data',str(data),'run'],stdout=log,stderr=log)
 for _ in range(600):
  if len(wires)>=3:break
  time.sleep(.1)
 if deliveries:
  (work/'after.json').write_text(json.dumps(op('main','inspect',deliveries[0]['execution']),indent=2))
 if mode=='unknown':
  # A paired partial must remain closed after two later Host restarts.
  for repeat in range(2):
   cmd('operator','shutdown');p.wait(timeout=10)
   with (work/f'closed-restart-{repeat}.txt').open('wb') as log:p=subprocess.Popen([str(exe),'--data',str(data),'run'],stdout=log,stderr=log)
   for _ in range(100):
    if cmd('operator','host','status',check=False).returncode==0:break
    time.sleep(.1)
   time.sleep(2)
 expected=0 if mode in {'missing-runtime','malformed-frame'} else 1 if mode=='unknown' else 2
 assert len(deliveries)==expected,deliveries
 assert len(wires)==3,len(wires)
 assert len({d['operation'] for d in deliveries})==expected
 if expected==2:assert deliveries[0]['execution']==deliveries[1]['execution'] and deliveries[0]['arguments']==deliveries[1]['arguments']
 frames=[json.loads(line) for line in (work/'wire.jsonl').read_text().splitlines()]
 invokes=[f['frame']['params'] for f in frames if f.get('forwarded',True) and f['direction']=='from_plugin' and f['frame'].get('method')=='tool.invoke']
 if expected==2:
  assert [x['ordinal'] for x in invokes]==[0,1]
  assert [x['feed_index'] for x in invokes]==[0,0]
  assert [x['engine_call_id'] for x in invokes]==['0','1']
 if mode=='unknown':assert len(invokes)==1
 if mode in {'missing-runtime','malformed-frame'}:assert not invokes
 resumes=[f['frame']['params'] for f in frames if f['direction']=='from_host' and f['frame'].get('method')=='code.resume']
 assert len(resumes)==restarts,(mode,resumes)

 final_inventory=native_inventory();assert initial_inventory==final_inventory,('native container not cleaned',initial_inventory,final_inventory)
 report={'host_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'plugin_sha256':initial_inventory['plugin_sha256'],'native_inventory_before':initial_inventory,'native_inventory_after':final_inventory,'fixture_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'transport_sha256':hashlib.sha256(pathlib.Path(__file__).with_name('codemode_wsl.py').read_bytes()).hexdigest(),'status':'PASS','candidate_only':True,'mode':mode,'restarts':restarts,'event':event,'wire_count':len(wires),'deliveries':deliveries,'host':op('host','status')};(work/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
 cmd('operator','shutdown',check=False)
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:p.kill();p.wait()
 srv.shutdown();srv.server_close();keepalive.terminate();keepalive.wait()
 (work/'model.json').write_text(json.dumps(wires,indent=2));print('transcript saved',work)
