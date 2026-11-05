set -eu
mountpoint -q /sys/kernel/security || mount -t securityfs securityfs /sys/kernel/security
install -d -m 700 /var/lib/yuki-ext023-docker /run/yuki-ext023-docker /var/tmp/yuki-ext023
install -d -m 700 /var/tmp/yuki-ext023/tmp
export TMPDIR=/var/tmp/yuki-ext023/tmp
export XDG_RUNTIME_DIR=/run/yuki-ext023-docker
export DOCKER_HOST=unix:///run/yuki-ext023-docker/api.sock
if ! docker info >/dev/null 2>&1; then
 if test -f /run/yuki-ext023-docker/daemon.pid; then
  pid=$(cat /run/yuki-ext023-docker/daemon.pid)
  if kill -0 "$pid" 2>/dev/null; then echo 'Existing daemon is still starting; inspect it.' >&2; exit 1; fi
  rm /run/yuki-ext023-docker/daemon.pid
 fi
 nohup /usr/bin/dockerd --host="$DOCKER_HOST" --data-root=/var/lib/yuki-ext023-docker --exec-root=/run/yuki-ext023-docker/exec --pidfile=/run/yuki-ext023-docker/daemon.pid --bridge=none --iptables=false --ip-forward=false --ip-masq=false --exec-opt native.cgroupdriver=cgroupfs >/var/tmp/yuki-ext023/dockerd.log 2>&1 </dev/null &
 for attempt in $(seq 1 40); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi
docker info >/dev/null

cd /var/tmp/yuki-ext023/monty-build
apparmor_parser -r deploy/security/yuki-bot-codemode.apparmor
python3 - <<'INNER'
import subprocess,json,pathlib,time,hashlib
base=['docker']; image='yuki-ext023-monty:baseline-329ca7c'
def call(args):
 r=subprocess.run(base+args,capture_output=True,text=True);return {'command':base+args,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
inspect=call(['image','inspect',image]);assert inspect['exit_code']==0,inspect
ident=json.loads(inspect['stdout'])[0]['Id']
cmd=['create','--init','--user','10001:10001','--cap-drop','ALL','--network','none','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--pids-limit','64','--memory','1g','--security-opt','apparmor=yuki-bot-codemode','--security-opt','seccomp='+str(pathlib.Path('deploy/security/yuki-codemode-seccomp.json').resolve()),'--entrypoint','python',ident,'-c',"import runpy,asyncio,json;from pathlib import Path;ns=runpy.run_path('/opt/yuki-monty/verify_monty_isolation.py');print(json.dumps(asyncio.run(ns['verify'](Path('/opt/yuki-monty/monty'),Path('/opt/yuki-monty/monty-isolated')))))"]
created=call(cmd);assert created['exit_code']==0,created
cid=created['stdout'].strip(); report={'image_id':ident,'create':created}
try:
 report['execute']=call(['start','-a',cid]);report['container']=call(['inspect',cid]);
 if report['execute']['exit_code']==0:
  report['native_evidence']=json.loads(report['execute']['stdout'])
  status=report['native_evidence']['worker']['status'];assert 'Seccomp:\t2' in status
  assert report['native_evidence']['worker']['apparmor_profile']=='yuki-bot-codemode//launcher//&yuki-bot-codemode//launcher//worker (enforce)'
finally:report['cleanup']=call(['rm','-f',cid])
report['kernel_audit']='\n'.join(line for line in subprocess.run(['dmesg'],capture_output=True,text=True).stdout.splitlines() if 'yuki-bot-codemode' in line)[-24000:]
print(json.dumps(report,indent=2))
assert report['execute']['exit_code']==0, 'native isolation failed; see recorded evidence'
INNER
