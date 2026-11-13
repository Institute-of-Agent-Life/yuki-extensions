"""Observe real Rust traffic; cut precisely between Host publication and its ACK."""
import json,subprocess,sys,threading,uuid
from pathlib import Path
program,trace,control=sys.argv[1:];trace=Path(trace);control=Path(control)
child=subprocess.Popen([program],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
lock=threading.Lock();publishes=set();session=str(uuid.uuid4())
def record(direction,raw,forwarded=True):
 frame=json.loads(raw)
 with lock,trace.open('a',encoding='utf-8') as f:f.write(json.dumps({'session':session,'direction':direction,'frame':frame,'forwarded':forwarded})+'\n')
 return frame

def input_loop():
 try:
  with open(sys.stdin.fileno(),'rb',closefd=False) as source:
   for line in source:
    frame=json.loads(line)
    if frame.get('id') in publishes and 'result' in frame and (control/'lose-next').exists():
     record('from_host',line,False);(control/'lose-next').unlink();(control/'lost.json').write_text(json.dumps(frame),encoding='utf-8');child.kill();return
    record('from_host',line);child.stdin.write(line);child.stdin.flush()
 finally:
  try:child.stdin.close()
  except OSError:pass
threading.Thread(target=input_loop,daemon=True).start()
try:
 for line in child.stdout:
  frame=record('from_plugin',line)
  if frame.get('method')=='notification.publish':publishes.add(frame['id'])
  sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
finally:
 try:child.wait(timeout=2)
 except subprocess.TimeoutExpired:
  child.kill()
  child.wait()
