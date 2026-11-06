import base64,json,platform,shutil,subprocess,sys,hashlib
from pathlib import Path
report={'task':'EXT-023','status':'BLOCKED_EXECUTION_ENVIRONMENT','host':'hjw','platform':platform.platform(),'python':sys.version,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'commands':[],'native_worker_supported':False,'baseline_worker_platforms':['Darwin arm64','Linux x86_64','Linux aarch64'],'baseline':'329ca7c487414d2f54ddd98ff4727446ed2446cd'}
for name in ('docker','wsl'):
 exe=shutil.which(name);item={'program':name,'executable':exe}
 if exe:
  args=[exe,*(['version','--format','{{json .Server}}'] if name=='docker' else ['--list','--quiet'])]
  try:
   p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
   def readable(b):
    return b.decode('utf-16-le' if b'\x00' in b else 'utf-8',errors='replace')
   item.update(command=args,exit_code=p.returncode,stdout=readable(p.stdout),stderr=readable(p.stderr),stdout_base64=base64.b64encode(p.stdout).decode(),stderr_base64=base64.b64encode(p.stderr).decode())
  except subprocess.TimeoutExpired:item.update(command=args,timeout_seconds=10)
 report['commands'].append(item)
report['required']='Linux worker runtime with enforced AppArmor and seccomp, no network, zero capabilities, fixed worker/launcher/CPython codec digests; current Windows has no executable backend.'
Path(sys.argv[1]).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
