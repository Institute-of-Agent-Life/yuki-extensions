import importlib.util,json,pathlib,time,traceback,os
path=pathlib.Path('/mnt/d/yuki-extension-tests/verify_bridge_134_01.py')
s=importlib.util.spec_from_file_location('verify_bridge',path);v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
original=v.docker

def command(*args,**kw):
    if args[0]=='create':args=(*args[:1],'--attach','stderr',*args[1:])
    return original(*args,**kw)
v.docker=command
image='sha256:65fcd704d953a9ca9be9c1e70269fc21768b571635e8fa8c38bc8b30c84ceb9a'
policy=pathlib.Path('/mnt/d/yuki-extension-tests/seccomp-134-01.json')
assert policy.exists()
output=pathlib.Path('/mnt/d/yuki-extension-tests/monty-disconnect-134-01.json');assert not output.exists()
report={'image':image,'platform':os.uname().release,'runs':[]}
try:
 for i in range(60):
    delay=[0,.001,.005,.02,.1,.3][i%6]
    print('cut',i,'delay',delay,flush=True)
    with v.Codec(image,policy) as c:
        r=c.call({'op':'start','manifest':['yuki_echo'],'code':'yuki_echo({})\nwhile True:\n    pass','inputs':{}})
        assert r['outcome']['status']=='suspended'
        rows=v.docker('top',c.cid,'-eo','pid,comm').stdout.splitlines()[1:]
        native=[int(row.split()[0]) for row in rows if row.split()[1]=='monty'];assert len(native)==1
        stat=pathlib.Path(f'/proc/{native[0]}/stat');baseline=stat.read_text().split()
        c.send({'op':'answer','engine_call_id':r['outcome']['call']['engine_call_id'],'answer':{'kind':'value','value':None}})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if int(stat.read_text().split()[13])>int(baseline[13]):break
            time.sleep(.001)
        else:raise AssertionError('native CPU not observed')
        time.sleep(delay);start=time.monotonic();c.proc.stdin.close();exit_code=c.proc.wait(timeout=5)
        state=json.loads(v.docker('inspect',c.cid).stdout)[0]['State']
        result={'attempt':i,'delay':delay,'exit_code':exit_code,'state':state,'stdout':c.proc.stdout.read().decode('utf-8','replace'),'stderr':c.proc.stderr.read().decode('utf-8','replace'),'logs':v.docker('logs',c.cid,check=False).stderr,'elapsed':time.monotonic()-start,'original_native_process_gone':not stat.exists() or stat.read_text().split()[21]!=baseline[21]}
        report['runs'].append(result);print(json.dumps(result),flush=True)
        if exit_code:break
finally:
 output.write_text(json.dumps(report,indent=2))
