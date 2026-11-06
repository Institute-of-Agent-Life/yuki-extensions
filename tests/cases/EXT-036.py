"""Run the independent Rust maintenance plugin against the pinned actual Host."""
import json
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from personal_preview import Owner


def prepare(root, output):
    calls=[]
    class Provider(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path':self.path,'body':body})
            if body.get('model')=='fixture-unknown':
                self.close_connection=True
                return
            inputs=body['input'];inputs=inputs if isinstance(inputs,list) else [inputs]
            payload=json.dumps({'data':[{'index':i,'embedding':[0.25,0.5,0.75]} for i in range(len(inputs))],
                                'usage':{'prompt_tokens':5,'total_tokens':5}}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:return exercise(root,output,server,calls)
    finally:
        server.shutdown();server.server_close()
        (output/'embedding-http.json').write_text(json.dumps(calls,indent=2),encoding='utf-8')


def exercise(root, output, server, calls):
    jobs = output / 'operator-jobs'
    jobs.mkdir()
    owner = Owner(root, output, 'memory-maintenance',
                  ['maintenance.audit','maintenance.audit.apply','maintenance.reembed','forget.owner'],
                  contract='core-035',
                  environment={'YUKI_MEMORY_MAINTENANCE_JOBS':str(jobs)}, command_timeout=30)
    cfg=owner.data/'yuki.toml'
    cfg.write_text(cfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"'),encoding='utf-8')
    records=[]
    def op(*args):
        r=owner.command('operator',*map(str,args))
        record={'args':list(map(str,args)),'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        records.append(record)
        (output/'operator.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        if r.returncode:raise RuntimeError(r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None
    def job(name, value):
        tmp=jobs/(name+'.tmp');tmp.write_text(json.dumps(value),encoding='utf-8');tmp.rename(jobs/(name+'.job'))
        end=time.monotonic()+20
        while time.monotonic()<end:
            result=jobs/(name+'.result')
            if result.exists():
                try:return json.loads(result.read_text(encoding='utf-8'))
                except json.JSONDecodeError:pass
            time.sleep(.05)
        raise AssertionError('maintenance job timed out: '+name)
    actor=str(uuid.uuid4())
    with owner.running():
        op('person','create',actor)
        user=op('account','open','qq','quality-fixture','200',1,'--person',actor,'--start',1)
        bot=op('account','open','qq','quality-fixture','100',1,'--start',1)
        space=json.dumps(['qq','quality-fixture','702'],separators=(',',':'))
        entry=op('entry','group',space)['entry']
        text='Original EXT-036 quality source; no invented evidence.'
        frame={'source':'quality-original','account':user['account'],'bot_stage':bot['assignment'],
               'reply_bot':'100','space':space,'kind':'message','occurred':100,'observed':100,
               'segments':[{'type':'text','text':text}]}
        event=op('ingress','record',json.dumps(frame),'--accept')['event']
        execution=op('ingress','claim',event)['execution']
        edit={'action':'add','body':'Original quality fixture','fact_key':'quality-fixture',
              'subject':{'kind':'person','person':actor,'space':None,'visibility':None,'entry':None},
              'evidence':[{'kind':'event','id':event,'quote':text}]}
        fact=op('memory','edit',execution,actor,'quality-add',json.dumps(edit))
        (output/'seed-fact.json').write_text(json.dumps(fact,indent=2),encoding='utf-8')
    policy='\n[plugins.maintenance.scopes.own]\n'+f'actor={json.dumps(actor)}\nentry={json.dumps(entry)}\n'
    policy+='methods=["maintenance.audit","maintenance.audit.apply","maintenance.reembed"]\npurposes=["quality"]\n'
    policy+='write_subject={kind="person",person='+json.dumps(actor)+'}\n'
    policy+='embedding_routes=["dense-a","dense-b","dense-unknown"]\n'
    for name in ['a','b','unknown']:
        policy+=f'\n[plugins.maintenance.embedding_routes.dense-{name}]\nprovider={{openai_compatible={{}}}}\nmodel="fixture-{name}"\ndimensions=3\nbase_url="http://127.0.0.1:{server.server_port}/v1"\n'
    cfg.write_text(cfg.read_text()+policy,encoding='utf-8')
    cases={}
    with owner.running():
        cases['invalid_job']=job('invalid-job',{'action':'scan','scope':'own','purpose':'quality','actor':'override'})
        assert cases['invalid_job']['state']=='not_completed'
        scan=job('scan-1',{'action':'scan','scope':'own','purpose':'quality'})
        cases['scan']=scan
        (output/'first-scan.json').write_text(json.dumps(scan,indent=2),encoding='utf-8')
        assert scan['state']=='completed',scan
        audit=scan['result']['audit'];assert audit['paid_calls']==0 and audit['items']
        assert not calls
        cases['foreign_scope']=job('foreign-scope',{'action':'scan','scope':'not-installed','purpose':'quality'})
        assert cases['foreign_scope']['state']=='not_completed'
        selected=audit['items'][0]['fact']
        cases['apply']=job('apply-1',{'action':'apply','scope':'own','purpose':'quality','operation':'quality-selected-apply',
                                    'fingerprint':audit['fingerprint'],'approved':[selected]})
        assert cases['apply']['state']=='completed',cases['apply']
        assert cases['apply']['result']['rebuilt']==[selected] and cases['apply']['result']['paid_calls']==0
        cases['foreign_fact']=job('foreign-fact',{'action':'apply','scope':'own','purpose':'quality','operation':'quality-foreign-rejected',
                                    'fingerprint':audit['fingerprint'],'approved':[str(uuid.uuid4())]})
        assert cases['foreign_fact']['state']=='not_completed'
    with owner.running():
        cases['replay']=job('apply-replay',{'action':'apply','scope':'own','purpose':'quality','operation':'quality-selected-apply',
                                    'fingerprint':audit['fingerprint'],'approved':[selected]})
        assert cases['replay']==cases['apply']
        routes={r['route']:r['profile'] for r in audit['embedding_routes']}
        assert routes['dense-a']!=routes['dense-b']
        def embed(name, route, operation):
            return job(name,{'action':'reembed','scope':'own','purpose':'quality','operation':operation,
                             'route':route,'profile':routes[route],'fact':selected,'revision':audit['items'][0]['revision']})
        cases['embed_a']=embed('embed-a','dense-a','quality-embed-a')
        assert cases['embed_a']['state']=='completed',cases['embed_a']
        assert cases['embed_a']['result']['state']=='done' and cases['embed_a']['result']['usage']['input']==5
        assert len(calls)==1
        current=job('scan-after-a',{'action':'scan','scope':'own','purpose':'quality'})
        cases['scan_after_a']=current
        missing=current['result']['coverage'][0]['missing_profiles']
        assert 'dense-b' in [r['route'] for r in missing] and 'dense-a' not in [r['route'] for r in missing]
        cases['embed_b']=embed('embed-b','dense-b','quality-embed-b')
        assert cases['embed_b']['result']['state']=='done' and len(calls)==2
        cases['embed_unknown']=embed('embed-unknown','dense-unknown','quality-embed-unknown')
        assert cases['embed_unknown']['state']=='completed',cases['embed_unknown']
        assert cases['embed_unknown']['result']['state']=='unknown',cases['embed_unknown']
        assert len(calls)==3
    with owner.running():
        cases['unknown_replay']=embed('embed-unknown-replay','dense-unknown','quality-embed-unknown')
        assert cases['unknown_replay']==cases['embed_unknown'] and len(calls)==3
        before=job('scan-before-edit',{'action':'scan','scope':'own','purpose':'quality'})['result']['audit']
        readable=op('memory','read',execution,actor,'--fact',selected,'--evidence')['items'][0]
        corrected=op('memory','edit',execution,actor,'quality-correct',json.dumps({
            'action':'correct','fact':selected,'revision':readable['revision'],'proof':readable['proof'],
            'body':'Changed fact content, same original evidence count'}))
        after=job('scan-after-edit',{'action':'scan','scope':'own','purpose':'quality'})['result']['audit']
        assert len(before['items'])==len(after['items'])==1
        assert before['items'][0]['evidence_total']==after['items'][0]['evidence_total']
        assert before['fingerprint']!=after['fingerprint']
        cases['same_count_change']={'before':before,'after':after,'correction':corrected}
        cases['stale_fingerprint']=job('stale-fingerprint',{'action':'apply','scope':'own','purpose':'quality',
            'operation':'stale-plan','fingerprint':before['fingerprint'],'approved':[selected]})
        assert cases['stale_fingerprint']['state']=='not_completed'
        assert len(calls)==3
        erased=op('privacy','erase','quality-erase',actor,json.dumps([event]))
        end=time.monotonic()+8
        callback=None
        while time.monotonic()<end:
            frames=[json.loads(s)['frame'] for s in owner.trace.read_text(encoding='utf-8').splitlines()]
            callback=next((f for f in frames if f.get('method')=='forget.request' and f['params']['key']=='quality-erase'),None)
            if callback and not op('privacy','pending','memory-maintenance')['obligations']:break
            time.sleep(.1)
        pending=op('privacy','pending','memory-maintenance')['obligations']
        cases['erased_reembed']=job('erased-reembed',{'action':'reembed','scope':'own','purpose':'quality',
            'operation':'quality-after-erase','route':'dense-a','profile':routes['dense-a'],
            'fact':selected,'revision':after['items'][0]['revision']})
        assert cases['erased_reembed']['state']=='not_completed'
        assert len(calls)==3
        cases['erasure']={'operation':erased,'callback_observed':callback,'pending_obligations':pending,
                         'operator_acquire_calls':0,'automatic_callback_acceptance':False}
    return 'hygiene-report.json',{'status':'PASS','card_status':'BLOCKED','candidate_only':True,
        'core':owner.evidence(),'cases':cases,'embedding_http_calls':len(calls),'scan_paid_calls':0,'database_access':'public operator and SDK only',
        'remaining':['actual SQL integrity findings','producer clarification of metadata erasure obligations']}


def run(root,output):
    raise RuntimeError('CORE-035 is an unpublished candidate; use --preparation')
