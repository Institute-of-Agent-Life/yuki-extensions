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

apparmor_parser -r /mnt/d/yuki-extension-tests/monty-profile.apparmor
cd /var/tmp/yuki-ext023
python - <<'RUN'
import importlib.util,json,pathlib,time
p=pathlib.Path('/mnt/d/yuki-extension-tests/verify_bridge_diagnostic.py')
s=importlib.util.spec_from_file_location('verify_bridge',p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v)
image='sha256:65fcd704d953a9ca9be9c1e70269fc21768b571635e8fa8c38bc8b30c84ceb9a'
policy=pathlib.Path('/var/tmp/yuki-ext023/rust-plugin-01/seccomp.json')
if not policy.exists():
 policy=next(pathlib.Path('/var/tmp/yuki-ext023').rglob('yuki-codemode-seccomp.json'))
for i in range(5):
 print('attempt',i,flush=True)
 r=v.verify(image,policy)
 pathlib.Path(f'/var/tmp/yuki-ext023/bridge-repeat-{i}.json').write_text(json.dumps(r,indent=2))
 print(r['blocked_feed_disconnect'],flush=True)
RUN
