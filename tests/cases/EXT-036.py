"""Run the independent Rust maintenance plugin against the pinned actual Host."""
from contextlib import closing, contextmanager
import json
import os
import sqlite3
import subprocess
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from personal_preview import Owner
from package import build


def prepare(root, output, *, integrity=False, retain=False, released_host=None,
            package_builder=build):
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
    try:
        return exercise(root, output, server, calls, integrity=integrity, retain=retain,
                        released_host=released_host, package_builder=package_builder)
    finally:
        server.shutdown();server.server_close()
        (output/'embedding-http.json').write_text(json.dumps(calls,indent=2),encoding='utf-8')


def fixture_rows(database):
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        return {
            'lexical': db.execute('SELECT rowid,content,memory_key,category FROM memory_retrieval_fts ORDER BY rowid').fetchall(),
            'evidence': db.execute('SELECT fact,source_version,quote FROM memory_evidence ORDER BY id').fetchall(),
            'attempts': db.execute('SELECT logical,state FROM embedding_items ORDER BY logical,ordinal').fetchall(),
            'apply': db.execute('SELECT operation,digest FROM maintenance_audit_apply ORDER BY operation').fetchall(),
        }


def wait_for_worker_exit(jobs):
    lock=jobs/'.worker.lock'
    if not lock.is_file():
        return
    if os.name=='nt':
        import msvcrt
        def try_lock(file):
            msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
    else:
        import fcntl
        def try_lock(file):
            fcntl.flock(file,fcntl.LOCK_EX|fcntl.LOCK_NB)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        with lock.open('r+b') as file:
            try:
                try_lock(file)
                return
            except BlockingIOError:
                pass
            except OSError as error:
                if os.name!='nt' or error.errno!=13:
                    raise
        time.sleep(.05)
    raise RuntimeError('previous maintenance worker still owns its private job directory')


def approve_changed_install(owner, op):
    plugin = {"plugin_id": owner.unit}
    with (owner.out / "route-approval.log").open("wb") as log:
        daemon = subprocess.Popen([owner.exe, "--data", owner.data, "run"], cwd=owner.work,
                                  env=owner.env, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if daemon.poll() is not None:
                raise RuntimeError("Host exited before installation approval")
            result = owner.command("operator", "control", "read", "plugin.get", json.dumps(plugin))
            if result.returncode == 0:
                state = json.loads(result.stdout)
                break
            time.sleep(.05)
        else:
            raise RuntimeError("changed installation approval status unavailable")
        assert state["status"] == "discovered"
        op("control", "write", "plugin.approve", json.dumps({
            **plugin, "request_id": str(uuid.uuid4()), "expected_revision": state["revision"],
        }))
        approved = op("control", "read", "plugin.get", json.dumps(plugin))
        assert approved["status"] == "disabled"
        assert set(approved["approved_permissions"]) == set(state["requested_permissions"])
        op("host", "enable", owner.unit, "true")
    finally:
        if daemon.poll() is None:
            owner.command("operator", "shutdown")
            try:
                daemon.wait(timeout=8)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()


def exercise(root, output, server, calls, *, integrity, retain, released_host,
             package_builder):
    jobs = output / 'operator-jobs'
    jobs.mkdir()
    owner = Owner(root, output, 'memory-maintenance',
                  ['maintenance.audit','maintenance.audit.apply','maintenance.reembed','forget.owner'],
                  contract='core-035-retention' if retain else 'core-035-integrity' if integrity else 'core-035',
                  environment={'YUKI_MEMORY_MAINTENANCE_JOBS':str(jobs)}, command_timeout=30,
                  released_host=released_host, package_builder=package_builder)
    cfg=owner.data/'yuki.toml'
    cfg.write_text(cfg.read_text().replace('mode = "hybrid"','mode = "lexical-only"'),encoding='utf-8')
    if retain:
        import tomllib
        manifest = owner.packages / 'plugin-retained.toml'
        if not manifest.is_file():
            manifest = owner.packages / 'plugin.toml'
        retained=tomllib.loads(manifest.read_text(encoding='utf-8'))
        configuration=tomllib.loads(cfg.read_text(encoding='utf-8'))
        args=configuration['plugins'][0]['args'] + retained['args']
        old_line='args='+json.dumps(configuration['plugins'][0]['args'])
        new_line='args='+json.dumps(args)+'\nerasure_args='+json.dumps(args)
        cfg.write_text(cfg.read_text().replace(old_line,new_line),encoding='utf-8')
    @contextmanager
    def running():
        if retain:
            wait_for_worker_exit(jobs)
        with owner.running():
            yield
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
    with running():
        op('person','create',actor)
        user=op('account','open','qq','quality-fixture','200',1,'--person',actor,'--start',1)
        bot=op('account','open','qq','quality-fixture','100',1,'--start',1)
        space=json.dumps(['qq','quality-fixture','702'],separators=(',',':'))
        entry=op('entry','group',space)['entry']
        def seed(label, person=actor, account=user['account'], group=space):
            text=f'原始證據 {label} is visible in its own conversation.'
            frame={'source':f'quality-{label}','account':account,'bot_stage':bot['assignment'],
                   'reply_bot':'100','space':group,'kind':'message','occurred':100,'observed':100,
                   'segments':[{'type':'text','text':text}]}
            event=op('ingress','record',json.dumps(frame),'--accept')['event']
            execution=op('ingress','claim',event)['execution']
            edit={'action':'add','body':text,'fact_key':f'quality-{label}',
                  'subject':{'kind':'person','person':person},
                  'evidence':[{'kind':'event','id':event,'quote':text}]}
            return event,execution,op('memory','edit',execution,person,'quality-add',json.dumps(edit))
        event,execution,fact=seed('selected')
        (output/'seed-fact.json').write_text(json.dumps(fact,indent=2),encoding='utf-8')
        if integrity:
            missing_event,_,missing=seed('missing-evidence')
            _,_,invalid=seed('invalid-evidence')
            foreign_actor=str(uuid.uuid4())
            op('person','create',foreign_actor)
            foreign_account=op('account','open','qq','quality-fixture','201',1,'--person',foreign_actor,'--start',1)
            foreign_group=json.dumps(['qq','quality-fixture','703'],separators=(',',':'))
            op('entry','group',foreign_group)
            _,_,foreign=seed('foreign',foreign_actor,foreign_account['account'],foreign_group)
    database=owner.data/'core.sqlite'
    if integrity:
        with closing(sqlite3.connect(database)) as fixture, fixture:
            for corrupt in (fact,missing,foreign):
                fixture.execute('UPDATE memory_retrieval_fts SET content=? WHERE rowid=(SELECT number FROM memory_facts WHERE id=?)',
                                ('corrupted fixture index',corrupt['fact']))
            fixture.execute('DELETE FROM memory_evidence WHERE fact=?',(missing['fact'],))
            fixture.execute('UPDATE memory_evidence SET source_version=? WHERE fact=?',('0'*64,invalid['fact']))
        before_scan=fixture_rows(database)
    policy='\n[plugins.maintenance.scopes.own]\n'+f'actor={json.dumps(actor)}\nentry={json.dumps(entry)}\n'
    policy+='methods=["maintenance.audit","maintenance.audit.apply","maintenance.reembed"]\npurposes=["quality"]\n'
    policy+='write_subject={kind="person",person='+json.dumps(actor)+'}\n'
    policy+='embedding_routes=["dense-a","dense-b","dense-unknown"]\n'
    provider='"openai_compatible"' if integrity else '{openai_compatible={}}'
    for name in ['a','b','unknown']:
        policy+=f'\n[plugins.maintenance.embedding_routes.dense-{name}]\nprovider={provider}\nmodel="fixture-{name}"\ndimensions=3\nbase_url="http://127.0.0.1:{server.server_port}/v1"\n'
    cfg.write_text(cfg.read_text()+policy,encoding='utf-8')
    if integrity:
        approve_changed_install(owner,op)
    scope={'scope':'own','purpose':'quality'}
    scan_params={**scope,**({'integrity':True} if integrity else {})}
    selected=fact['fact']
    selected_scan={**scan_params,'fact':selected}
    cases={}
    with running():
        cases['invalid_job']=job('invalid-job',{'action':'scan','scope':'own','purpose':'quality','actor':'override'})
        assert cases['invalid_job']['state']=='not_completed'
        scan=job('scan-1',{'action':'scan',**scan_params})
        cases['scan']=scan
        (output/'first-scan.json').write_text(json.dumps(scan,indent=2),encoding='utf-8')
        assert scan['state']=='completed',scan
        audit=scan['result']['audit'];assert audit['paid_calls']==0 and audit['items']
        assert not calls
        if integrity:
            findings={row['fact']:row for row in scan['result']['quality_findings']}
            assert set(findings)=={selected,missing['fact'],invalid['fact']}
            assert findings[selected]['lexical']=='mismatch'
            assert findings[missing['fact']]['evidence_missing'] and findings[missing['fact']]['lexical']=='mismatch'
            assert findings[invalid['fact']]['invalid_event_evidence']==1
            assert findings[invalid['fact']]['event_evidence_checked']==1
            cases['stats']=job('stats-1',{'action':'stats',**scope})
            assert cases['stats']['result']['stats']=={
                'facts':3,'lexical_repairs':2,'facts_missing_evidence':1,
                'event_evidence_checked':2,'invalid_event_evidence':1,
            }
            cases['audit']=job('audit-1',{'action':'audit',**scope})
            assert cases['audit']==scan
            cases['legacy_scan']=job('legacy-1',{'action':'scan',**scope})
            assert cases['legacy_scan']['result']['quality_findings']=='not_exposed_by_candidate'
            assert fixture_rows(database)==before_scan and not calls
            cases['scan_side_effects']={'fixture_rows_unchanged':True,'embedding_http_calls':0}
        cases['foreign_scope']=job('foreign-scope',{'action':'scan','scope':'not-installed','purpose':'quality'})
        assert cases['foreign_scope']['state']=='not_completed'
        revision=next(item['revision'] for item in audit['items'] if item['fact']==selected)
        apply={'action':'apply',**scan_params,'operation':'quality-selected-apply',
               'fingerprint':audit['fingerprint'],'approved':[selected]}
        cases['foreign_fact']=job('foreign-fact',{**apply,'operation':'quality-foreign-rejected',
                                    'approved':[foreign['fact'] if integrity else str(uuid.uuid4())]})
        assert cases['foreign_fact']['state']=='not_completed'
        cases['apply']=job('apply-1',apply)
        assert cases['apply']['state']=='completed',cases['apply']
        assert cases['apply']['result']['rebuilt']==[selected] and cases['apply']['result']['paid_calls']==0
        if integrity:
            after_apply=fixture_rows(database)
            assert len(after_apply['lexical'])==len(before_scan['lexical'])
            changed=[after for before,after in zip(before_scan['lexical'],after_apply['lexical']) if before!=after]
            assert len(changed)==1 and changed[0][1]=='原始證據 selected is visible in its own conversation.'
            assert after_apply['evidence']==before_scan['evidence']
            assert after_apply['attempts']==before_scan['attempts']
            cases['after_apply']=job('after-apply',{'action':'audit',**scope})
            after_findings={row['fact']:row for row in cases['after_apply']['result']['quality_findings']}
            assert after_findings[selected]['lexical']=='current'
            assert after_findings[missing['fact']]['lexical']=='mismatch'
    with running():
        cases['replay']=job('apply-replay',apply)
        assert cases['replay']==cases['apply']
        routes={r['route']:r['profile'] for r in audit['embedding_routes']}
        assert routes['dense-a']!=routes['dense-b']
        def embed(name, route, operation):
            return job(name,{'action':'reembed','scope':'own','purpose':'quality','operation':operation,
                             'route':route,'profile':routes[route],'fact':selected,'revision':revision})
        cases['embed_a']=embed('embed-a','dense-a','quality-embed-a')
        assert cases['embed_a']['state']=='completed',cases['embed_a']
        assert cases['embed_a']['result']['state']=='done' and cases['embed_a']['result']['usage']['input']==5
        assert len(calls)==1
        current=job('scan-after-a',{'action':'scan',**selected_scan})
        cases['scan_after_a']=current
        if integrity:
            profiles={row['route']:row for row in current['result']['coverage'][0]['profiles']}
            assert profiles['dense-a']['coverage']=='current'
            assert profiles['dense-b']['coverage']=='missing' and profiles['dense-b']['attempt'] is None
        else:
            missing_profiles=[r['route'] for r in current['result']['coverage'][0]['missing_profiles']]
            assert 'dense-b' in missing_profiles and 'dense-a' not in missing_profiles
        cases['embed_b']=embed('embed-b','dense-b','quality-embed-b')
        assert cases['embed_b']['result']['state']=='done' and len(calls)==2
        cases['embed_unknown']=embed('embed-unknown','dense-unknown','quality-embed-unknown')
        assert cases['embed_unknown']['state']=='completed',cases['embed_unknown']
        assert cases['embed_unknown']['result']['state']=='unknown',cases['embed_unknown']
        assert len(calls)==3
    with running():
        cases['unknown_replay']=embed('embed-unknown-replay','dense-unknown','quality-embed-unknown')
        assert cases['unknown_replay']==cases['embed_unknown'] and len(calls)==3
        before_result=job('scan-before-edit',{'action':'scan',**selected_scan})['result']
        before=before_result['audit']
        if integrity:
            profiles={row['route']:row for row in before_result['coverage'][0]['profiles']}
            assert profiles['dense-unknown']['coverage']=='missing' and profiles['dense-unknown']['attempt']=='unknown'
            cases['unknown_scan']=before_result
        readable=op('memory','read',execution,actor,'--fact',selected,'--evidence')['items'][0]
        corrected=op('memory','edit',execution,actor,'quality-correct',json.dumps({
            'action':'correct','fact':selected,'revision':readable['revision'],'proof':readable['proof'],
            'body':'Changed fact content, same original evidence count'}))
        after=job('scan-after-edit',{'action':'scan',**selected_scan})['result']['audit']
        assert len(before['items'])==len(after['items'])==1
        assert before['items'][0]['evidence_total']==after['items'][0]['evidence_total']
        assert before['fingerprint']!=after['fingerprint']
        cases['same_count_change']={'before':before,'after':after,'correction':corrected}
        cases['stale_fingerprint']=job('stale-fingerprint',{'action':'apply',**selected_scan,
            'operation':'stale-plan','fingerprint':before['fingerprint'],'approved':[selected]})
        assert cases['stale_fingerprint']['state']=='not_completed'
        assert len(calls)==3
        if retain:
            cases['retained_unrelated']=job('retained-unrelated',{'action':'audit',**scope,'fact':missing['fact']})
            cases['retained_before_erase']=job('retained-selected',{'action':'audit',**scope,'fact':selected})
            assert len(cases['retained_unrelated']['erasure_refs'])==1
            assert len(cases['retained_before_erase']['erasure_refs'])>=1
            assert missing_event != event
            for name, report in [('temporary-affected', cases['retained_before_erase']),
                                 ('temporary-unrelated', cases['retained_unrelated'])]:
                (jobs/(name+'.started')).write_text('fixture fence\n',encoding='utf-8')
                (jobs/(name+'.job')).write_text('{}',encoding='utf-8')
                (jobs/(name+'.result.tmp')).write_text(json.dumps(report),encoding='utf-8')
            (jobs/'unclassified.result').write_text('{incomplete',encoding='utf-8')
        erased=op('privacy','erase','quality-erase',actor,json.dumps([event]))
        end=time.monotonic()+12
        callback=failed_reply=None
        while time.monotonic()<end:
            frames=[json.loads(line)['frame'] for line in owner.trace.read_bytes().splitlines(keepends=True)
                    if line.endswith(b'\n')]
            callbacks=[f for f in frames if f.get('method')=='forget.request' and f['params']['key']=='quality-erase']
            callback=callbacks[0] if callbacks else None
            if callback:
                if retain:
                    failed_reply=next((f for f in frames if f.get('id')==callback['id']
                        and f.get('error',{}).get('message')=='quality_erasure_incomplete'),None)
                    if failed_reply:break
                elif not op('privacy','pending','memory-maintenance')['obligations']:
                    break
            time.sleep(.1)
        pending=op('privacy','pending','memory-maintenance')['obligations']
        if retain:
            assert callback and failed_reply and pending, (callback,failed_reply,pending)
            assert set(callback['params']['erasure_refs']) & set(cases['retained_before_erase']['erasure_refs'])
            assert callback['params']['sources']==[]
            assert not set(callback['params']['erasure_refs']) & set(cases['retained_unrelated']['erasure_refs'])
            assert (jobs/'retained-unrelated.result').exists()
        else:
            cases['erased_reembed']=job('erased-reembed',{'action':'reembed','scope':'own','purpose':'quality',
                'operation':'quality-after-erase','route':'dense-a','profile':routes['dense-a'],
                'fact':selected,'revision':after['items'][0]['revision']})
            assert cases['erased_reembed']['state']=='not_completed'
        assert len(calls)==3
        cases['erasure']={'operation':erased,'callback_observed':callback,'pending_obligations':pending,
                         'operator_acquire_calls':0,'automatic_callback_acceptance':False}
    if retain:
        cases['erasure']['initial_failure']=failed_reply
        (jobs/'unclassified.result').rename(output/'unclassified-before-recovery.json')
        with running():
            deadline=time.monotonic()+12
            pending=op('privacy','pending','memory-maintenance')['obligations']
            while pending and time.monotonic()<deadline:
                time.sleep(.1)
                pending=op('privacy','pending','memory-maintenance')['obligations']
            assert pending==[]
            assert not (jobs/'retained-selected.result').exists()
            assert not (jobs/'retained-selected.job').exists()
            assert (jobs/'retained-selected.started').is_file()
            assert json.loads((jobs/'retained-unrelated.result').read_bytes())==cases['retained_unrelated']
            assert not (jobs/'temporary-affected.result.tmp').exists()
            assert not (jobs/'temporary-affected.job').exists()
            assert (jobs/'temporary-affected.started').is_file()
            assert (jobs/'temporary-unrelated.job').is_file()
            assert json.loads((jobs/'temporary-unrelated.result.tmp').read_bytes())==cases['retained_unrelated']
            cases['erasure']['temporary_results']={'affected_removed':True,'unrelated_preserved':True}
            cases['erased_reembed']=job('erased-reembed',{'action':'reembed',**scope,
                'operation':'quality-after-erase','route':'dense-a','profile':routes['dense-a'],
                'fact':selected,'revision':after['items'][0]['revision']})
            assert cases['erased_reembed']['state']=='not_completed' and len(calls)==3
            cases['erasure']['automatic_callback_acceptance']=True
            cases['erasure']['pending_after_cold_cleanup']=[]
            frames=[json.loads(line) for line in owner.trace.read_bytes().splitlines(keepends=True)
                    if line.endswith(b'\n')]
            acknowledgement=next((row['frame']['result'] for row in frames
                if row['direction']=='from_plugin' and isinstance(row['frame'].get('result'),dict)
                and row['frame']['result'].get('key')=='quality-erase'
                and row['frame']['result'].get('watermark')==callback['params']['watermark']),None)
            assert acknowledgement and acknowledgement['proof']=='selected quality reports removed'
            cases['erasure']['acknowledgement']=acknowledgement
    package=json.loads((owner.packages/'package-manifest.json').read_bytes())
    sdk_pin=json.loads((root/package['source']['sdk_contract']).read_bytes())
    remaining = (['published plugin installation tuple'] if owner.published_host else
                 ['published Host and plugin tuple'] if integrity else ['actual SQL integrity findings'])
    return 'hygiene-report.json',{'status':'PASS','card_status':'BLOCKED','candidate_only':True,
        'core':owner.evidence(),'plugin':{'version':package['version'],'sdk':sdk_pin['sdk']['rust'],
        'sdk_crate_sha256':sdk_pin['rust_crate_sha256'],'binary_sha256':owner.binary_sha},
        'cases':cases,'embedding_http_calls':len(calls),'scan_paid_calls':0,
        'database_access':'public operator and SDK; fault injection confined to the isolated fixture' if integrity else 'public operator and SDK only',
        'remaining': remaining + ([] if retain else ['producer clarification of metadata erasure obligations'])}


def run(root,output):
    if bundle := os.environ.get('YUKI_STABLE_1_2_BUNDLE'):
        from maintenance_release_check import replay

        return replay(root, output, bundle, prepare,
                      qualify=os.environ.get('YUKI_MAINTENANCE_RELEASE_CANDIDATE')=='1')
    return prepare(root,output,integrity=True,retain=os.environ.get('YUKI_QUALITY_RETENTION')=='1')
