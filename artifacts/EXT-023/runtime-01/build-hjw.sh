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
python3 - <<'INNER'
from pathlib import Path
import tarfile,hashlib
p=Path('/mnt/d/yuki-extension-tests/ext023-monty-context-06.tar')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='75fa9dda1036fb446e58d983bd63910782be10cc5e7bd3a169211873f4afed57'
with tarfile.open(p) as t:t.extractall('.',filter='data')
INNER
DOCKER_BUILDKIT=0 docker build --network host --build-arg PYTHON_IMAGE=yuki-ext023-base-python:1148dbb01461 --build-arg RUST_IMAGE=yuki-ext023-base-rust:811d6caab4a8 --build-arg UV_IMAGE=yuki-ext023-base-uv:812f4717f000 -t yuki-ext023-monty:baseline-329ca7c -f Dockerfile . > /var/tmp/yuki-ext023/monty-build-05.log 2>&1
docker image inspect yuki-ext023-monty:baseline-329ca7c --format '{{json .}}'
