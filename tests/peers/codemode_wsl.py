"""Byte-preserving real plugin transport with one pre-dispatch crash barrier."""
import os,subprocess,threading,sys,json,pathlib,time
trace=pathlib.Path(sys.argv[1]);mode=sys.argv[2]; target=2 if mode=='after-feed-twice' else 1; prior=len(list(trace.parent.glob('cut-*.json'))); cut=trace.parent/f'cut-{prior+1}.json';stop=threading.Event();lock=threading.Lock()
env=dict(os.environ);env['WSLENV']='YUKI_PLUGIN_BINDING:YUKI_CODE_RUNTIME_CONFIG';env['YUKI_CODE_RUNTIME_CONFIG']=sys.argv[3]
child=subprocess.Popen(['C:/Program Files/WSL/wsl.exe','-d','Arch','-u','root','--exec',sys.argv[4]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=env)
def copy(src,sink,direction):
 try:
  for line in src:
   frame=json.loads(line)
   malformed=mode=='malformed-frame' and direction=='from_plugin' and frame.get('method')=='tool.invoke'
   pause=prior<target and ((mode=='after-feed-twice' and direction=='from_plugin' and frame.get('method')=='tool.invoke' and frame.get('params',{}).get('ordinal')==1) or (mode=='before-feed' and direction=='from_host' and frame.get('result',{}).get('can_feed') is True and frame.get('result',{}).get('ordinal')==0 and 'receipt' in frame.get('result',{})))
   with lock,trace.open('a',encoding='utf-8') as out:out.write(json.dumps({'direction':direction,'frame':frame,'forwarded':not (pause or malformed)})+'\n')
   if malformed:
    child.stdin.write(b'{malformed\n');child.stdin.flush();continue
   if pause:
    cut.write_text(json.dumps({'frame':frame,'transport_pid':os.getpid(),'forwarded':False}))
    if direction=='from_host':
     # Keep observing Host EOF while withholding this one durable reply.
     for _ in src:pass
    else:stop.wait(30)
    return
   sink.write(line);sink.flush()
 except (OSError,ValueError):pass
def inbound():
 try:copy(sys.stdin.buffer,child.stdin,'from_host')
 finally:child.stdin.close();stop.set()
threading.Thread(target=inbound,daemon=True).start()
try:copy(child.stdout,sys.stdout.buffer,'from_plugin')
finally:
 try:child.wait(timeout=30)
 except subprocess.TimeoutExpired:child.kill();child.wait()
 (trace.parent/f'transport-exit-{prior}.json').write_text(json.dumps({'pid':os.getpid(),'child_exit':child.returncode}))
