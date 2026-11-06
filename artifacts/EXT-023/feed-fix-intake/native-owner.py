"""Own isolated Host; public operators only. A diagnostic consumer, not acceptance."""
import pathlib,subprocess,json,uuid,time,hashlib,queue,threading,sys
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=pathlib.Path('D:/yuki-extension-tests/core034-public-help');exe=root/'feed-fix-host/bin/yuki-core.exe'
assert hashlib.sha256(exe.read_bytes()).hexdigest()=='502f190d036f55c9f4348aa832642f82aa3bc5bb1ae153ac100bffc87f68052b'
work=root/'feed-fix-owner-01';work.mkdir();data=work/'owner';wires=[];deliveries=[]
keepalive=subprocess.Popen(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec','sleep','3600'])
setup=subprocess.run(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec','/bin/sh'],input=(root/'runtime-setup.sh').read_bytes(),capture_output=True)
assert setup.returncode==0,setup.stderr.decode('utf-8','replace')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
  if self.path=='/binding':
   deliveries.append(body);result={'accepted':body['operation'],'sequence':len(deliveries)}
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
text+='\n[[plugins]]\nid="code_a"\nnamespace="code_a"\nprogram='+json.dumps(sys.executable)+'\nargs='+json.dumps([str(root/'wsl-stdio.py'),str(work/'wire.jsonl')])+'\ngrants=["tool.call","composition.read","composition.execute","forget.owner"]\n'
contract=json.loads((root/'runtime-contract.json').read_bytes())
text+='[plugins.composition]\ntool="code_a"\n'+'\n'.join(k+'='+json.dumps(contract[k]) for k in ['abi','engine_sha256','codec_sha256','launcher_sha256'])+'\n'
text+='[[plugins.tools]]\nname="code_a"\ndescription="Rust isolated Monty candidate"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={code={type="string"}},required=["code"],additionalProperties=false}\n';cfg.write_text(text)
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
 for _ in range(600):
  if len(wires)>=3:break
  time.sleep(.1)
 report={'event':event,'wire_count':len(wires),'deliveries':deliveries,'host':op('host','status')};(work/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
 cmd('operator','shutdown',check=False)
 try:p.wait(timeout=10)
 except subprocess.TimeoutExpired:p.kill();p.wait()
 srv.shutdown();srv.server_close();keepalive.terminate();keepalive.wait()
 (work/'model.json').write_text(json.dumps(wires,indent=2));print('transcript saved',work)
