import hashlib,importlib.util,json,os,pathlib,sys,time
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir()
policy=root/'images/monty-runtime/deploy/security/yuki-codemode-seccomp.json'
assert hashlib.sha256(policy.read_bytes()).hexdigest()=='57457313430e0bb513ccab8a6906c5e05ffc217459f9c5b01cc77d827dcedc81'
image='sha256:65fcd704d953a9ca9be9c1e70269fc21768b571635e8fa8c38bc8b30c84ceb9a'
paths={'before':pathlib.Path('/mnt/d/yuki-extension-tests/verify_bridge_134_01.py'),'after':root/'images/monty-runtime/scripts/verify_bridge.py'}
probe="import json,sys,os;print(json.dumps({'ready':True}),flush=True);sys.stdin.buffer.readline();sys.stderr.write('yuki-native-stderr-fault-01\\n');sys.stderr.flush();os.abort()"
modules={}
for key,p in paths.items():
 s=importlib.util.spec_from_file_location('codec_'+key,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);modules[key]=v
before_set=set(modules['after'].docker('ps','-aq').stdout.splitlines());report={'image':image,'kernel':os.uname().release,'sources':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},'controlled_abort':{}}
try:
 for key,v in modules.items():
  original=v.docker
  def docker(*args,**kw):
   if args[0]=='create':args=(*args[:-1],'--ulimit','core=0','--entrypoint','python',args[-1],'-c',probe)
   return original(*args,**kw)
  v.docker=docker
  try:
   with v.Codec(image,policy) as c:
    c.send({'diagnostic':'abort'});code=c.proc.wait(timeout=5)
    if key=='after':d=c.exit_diagnostics()
    else:
     logs=v.docker('logs','--tail','100',c.cid,check=False)
     d={'exit_code':code,'stdout':c.proc.stdout.read().decode('utf-8','replace'),'stderr':c.proc.stderr.read().decode('utf-8','replace'),'container_stdout':logs.stdout,'container_stderr':logs.stderr}
    d['attach_stderr']=c.inspection['Config']['AttachStderr'];assert code==134,d
    assert 'yuki-native-stderr-fault-01' in d['container_stderr'],d
    assert ('Fatal Python error: Aborted' in d['stderr'])==(key=='after'),d
    report['controlled_abort'][key]=d
  finally:v.docker=original
 report['native_codec']=modules['after'].verify(image,policy)
 assert report['native_codec']['status']=='PASS'
 report['containers_restored']=set(modules['after'].docker('ps','-aq').stdout.splitlines())==before_set
 assert report['containers_restored']
 report['status']='DIAGNOSTICS_VERIFIED';report['original_ci_exit134_fixed']=False
finally:
 (out/'native-diagnostics.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report.get('status'),'original_ci_exit134_fixed':False,'containers_restored':report.get('containers_restored')}))
