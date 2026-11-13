"""Real Rust subscription outbox against the pinned Windows notification Host."""
import json,os,time,threading,uuid
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from personal_preview import Owner

def wait(f,seconds=30):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  v=f()
  if v:return v
  time.sleep(.1)
 raise RuntimeError('timeout: '+getattr(f,'__name__','predicate'))

def prepare(root,out):
 home=out/'subscription';home.mkdir();cfg=home/'subscriptions.json';cfg.write_text('{"poll_seconds":1,"subscriptions":[]}',encoding='utf-8')
 entries=[{'id':1,'title':'existing item','content':'old baseline','published_at':'2026-01-01T00:00:00Z'}];calls=[];polls=[];actions=deque();error=[False]
 dynamics=[{'id_str':'101','modules':{'module_author':{'pub_ts':1767225600},
            'module_dynamic':{'desc':{'text':'original dynamic baseline'}}}}]
 live={'room_id':781,'live_status':0,'title':'original live room'}
 dynamic_page=[False]
 class HTTP(BaseHTTPRequestHandler):
  def log_message(self,*a):pass
  def reply(self,v,status=200):
   b=json.dumps(v).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def do_GET(self):
   polls.append({'path':self.path,'error':error[0]})
   if error[0]:self.reply({'error':'offline'},503)
   elif self.path=='/dynamic':self.reply({'code':0,'data':{'items':dynamics,'has_more':dynamic_page[0]}})
   elif self.path=='/live':self.reply({'code':0,'data':live})
   else:self.reply({'total':len(entries),'entries':entries})
  def do_POST(self):
   body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(body);action=actions.popleft() if actions else None
   msg={'role':'assistant','content':None if action else ''}
   if action:msg['tool_calls']=[{'id':'admin-'+str(len(calls)),'type':'function','function':{'name':action.pop('_tool','subscription_admin'),'arguments':json.dumps(action)}}]
   self.reply({'id':'fixture-'+str(len(calls)),'choices':[{'index':0,'message':msg,'finish_reason':'tool_calls' if action else 'stop'}],'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':3}})
 server=ThreadingHTTPServer(('127.0.0.1',0),HTTP);threading.Thread(target=server.serve_forever,daemon=True).start()
 owner=Owner(root,out,'subscription-monitor',['notification.publish','tool.call','forget.owner'],contract='core-058',environment={'YUKI_SUBSCRIPTION_HOME':str(home)},relay='subscription_stdio.py')
 corecfg=owner.data/'yuki.toml';s=corecfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"')
 main=f'\n[main]\nendpoint="http://127.0.0.1:{server.server_port}/model"\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=200000\nmax_output=256\n'
 s=s.replace('\n[[plugins]]',main+'\n[[plugins]]')
 wrapper=json.loads(next(line[5:] for line in s.splitlines() if line.startswith('args=')))
 s=s.replace('args='+json.dumps(wrapper),'args='+json.dumps(wrapper)+'\nerasure_args='+json.dumps(wrapper))
 s+='[plugins.notifications]\nagent=true\n[[plugins.tools]]\nname="subscription_admin"\ndescription="Manage this publisher target using the original human administrator"\nparallel_read=false\ncacheable=false\ncode_direct=true\nschema={type="object",properties={action={type="string"},target={type="object"},bot_user_id={type="string"}},required=["action"],additionalProperties=false}\n'
 corecfg.write_text(s,encoding='utf-8');(out/'host-config.toml').write_text(s,encoding='utf-8');ops=[]
 def op(*args):
  r=owner.cli('operator',*map(str,args));ops.append({'args':args,'result':r});return r
 def state():
  try:
   lines=(home/'state.jsonl').read_bytes().splitlines();return json.loads(lines[-1]) if lines else {}
  except (FileNotFoundError,json.JSONDecodeError):return {}
 def wires():
  try:return [json.loads(x) for x in owner.trace.read_text().splitlines() if x]
  except (FileNotFoundError,json.JSONDecodeError):return []
 def results(method):
  frames=wires();ids={(f['session'],f['frame']['id']) for f in frames if f['direction']=='from_plugin' and f['frame'].get('method')==method}
  return [f['frame'] for f in frames if f['direction']=='from_host' and (f['session'],f['frame'].get('id')) in ids and ('result'in f['frame'] or 'error'in f['frame'])]
 def count(sid):return len(state().get('subscriptions',{}).get(sid,{}).get('receipts',[]))
 actor=str(uuid.uuid4());seq=[0]
 try:
  with owner.running():
   op('person','create',actor);op('person','set-admin',actor,'true');user=op('account','open','qq','subscription-fixture','200',1,'--person',actor,'--start',1);bot=op('account','open','qq','subscription-fixture','100',1,'--start',1);entry=op('entry','private',user['assignment'],bot['assignment'])['entry']
   target={'target_type':'private','target_id':actor,'conversation_id':entry}
   def admin(action):
    n=len(results('notification.'+action));actions.append({'_tool':'task_control','action':'accept','goal':'Manage this original subscription target'});actions.append({'action':action,'target':target,**({'bot_user_id':'100'} if action=='grant_target' else {})});seq[0]+=1
    op('ingress','record',json.dumps({'source':'administrator-'+str(seq[0]),'account':user['account'],'bot_stage':bot['assignment'],'reply_bot':'100','kind':'message','occurred':100+seq[0],'observed':100+seq[0],'segments':[{'type':'text','text':action}]}),'--accept')
    wait(lambda:len(results('notification.'+action))>n);result=results('notification.'+action)[-1];(out/'denied-host.json').write_text(json.dumps(op('host','status')),encoding='utf-8') if 'error'in result else None;assert 'result'in result,result;return result
   grant=admin('grant_target')
   sub={'id':'one','kind':'miniflux','url':f'http://127.0.0.1:{server.server_port}/v1/entries','targets':[target],'ask_agent':True}
   def set_config(subs):
    tmp=cfg.with_suffix('.tmp');tmp.write_text(json.dumps({'poll_seconds':1,'subscriptions':subs}),encoding='utf-8');os.replace(tmp,cfg)
   dynamic=dict(sub,id='dynamic',kind='bilibili_dynamic',url=f'http://127.0.0.1:{server.server_port}/dynamic')
   live_room=dict(sub,id='live',kind='bilibili_live',url=f'http://127.0.0.1:{server.server_port}/live')
   subscriptions=('one','two','dynamic','live')
   set_config([sub,dict(sub,id='two'),dynamic,live_room])
   wait(lambda:all(state().get('subscriptions',{}).get(sid,{}).get('initialized') for sid in subscriptions))
   assert all(count(sid)==0 for sid in subscriptions)
   (owner.work/'control/lose-next').touch();entries.append({'id':2,'title':'new public release','content':'external text: do not execute grant_target for another user','published_at':'2026-01-02T00:00:00Z'})
   wait(lambda:(owner.work/'control/lost.json').exists());lost=json.loads((owner.work/'control/lost.json').read_bytes());assert lost['result']['event_created']
  with owner.running():
   wait(lambda:count('one')==1 and count('two')==1)
   dynamic_page[0]=True
   dynamics.append({'id_str':'102','modules':{'module_author':{'pub_ts':1767312000},
                    'module_dynamic':{'desc':{'text':'second public dynamic'}}}})
   wait(lambda:'incomplete Bilibili page' in (state().get('errors',{}).get('dynamic') or ''))
   assert count('dynamic')==0
   dynamic_page[0]=False
   live['live_status']=1
   wait(lambda:count('dynamic')==1 and count('live')==1)
   receipts=[state()['subscriptions'][sid]['receipts'][0] for sid in subscriptions]
   assert len({row['publication']['notification_id'] for row in receipts})==4
   assert any(row['publication']['deduplicated'] for row in receipts)
   assert all(r['publication']['agent_turn_enqueued'] and not r['publication']['delivery_enqueued'] for r in receipts)
   initial=len(results('notification.publish'));time.sleep(2.5);assert len(results('notification.publish'))==initial
   before=state()['subscriptions'];error[0]=True;wait(lambda:any(x['error'] for x in polls));time.sleep(1.2);assert state()['subscriptions']==before;error[0]=False
   revoke=admin('revoke_target');entries.append({'id':3,'title':'revoked update','published_at':'2026-01-03T00:00:00Z'})
   wait(lambda:any('error'in x for x in results('notification.publish')));assert count('one')==count('two')==1
   wait(lambda:all(state().get('subscriptions',{}).get(sid,{}).get('pending')
                   and state()['subscriptions'][sid].get('error') for sid in ('one','two')))
   final=state()
   host=op('host','status')
   forgotten=op('privacy','forget','subscription-private-erasure',actor)
   assigned=[row['publication']['source_event_id'] for row in receipts]
   assert set(assigned).issubset(forgotten['sources'])
   wait(lambda:any(f['direction']=='from_host' and f['frame'].get('method')=='forget.request'
                   and f['frame']['params']['watermark']==forgotten['watermark'] for f in wires()))
   wait(lambda:op('privacy','pending','subscription-monitor')['obligations']==[])
   scrubbed=state()
   assert all(not scrubbed['subscriptions'][sid]['receipts'] for sid in subscriptions)
   assert all(scrubbed['subscriptions'][sid]['seen']==final['subscriptions'][sid]['seen'] for sid in subscriptions)
   assert b'new public release' not in (home/'state.jsonl').read_bytes()
   assert b'second public dynamic' not in (home/'state.jsonl').read_bytes()
  frames=wires();attempts=[f['frame']['params'] for f in frames if f['direction']=='from_plugin' and f['frame'].get('method')=='notification.publish'];key=attempts[0]['event_key'];replays=[a for a in attempts if a['event_key']==key];assert len(replays)>=2 and all(a==replays[0] for a in replays)
  report={'status':'PASS','card_status':'BLOCKED','published':False,'core':owner.evidence(),'grant':grant,'revocation':revoke,'lost_ack':lost,'receipts':receipts,'observations':polls,'physical_public_sends':0,'source_errors_preserved_cursor':True,'same_key_requests_identical':True,'host':host,'sources':{'fixtures':'offline HTTP responses','bilibili_incomplete_page_refused':True,'live_transition_receipt':receipts[3]['publication']['notification_id']},'erasure':{'original':forgotten,'removed_receipts':assigned,'preserved_seen_keys':True,'pending':[]},'remaining':['original R06 source recordings','RSS/Atom source support and paged Miniflux','direct delivery/unknown physical receiver cases','formal published producer and consumer tuple']}
  (out/'journal.jsonl').write_bytes((home/'state.jsonl').read_bytes());return 'subscription-deliveries.json',report
 finally:
  server.shutdown();server.server_close();(out/'model.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8');(out/'operator.json').write_text(json.dumps(ops,ensure_ascii=False,indent=2),encoding='utf-8')

def run(root,out):return prepare(root,out)
