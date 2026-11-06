#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$HERE/start-docker.sh"
cd "$HERE"
apparmor_parser -r ./yuki-bot-codemode.apparmor
printf 'task-owned canary' >/var/tmp/yuki-ext023/host-only-canary
docker run --rm --init -i --user 10001:10001 --cap-drop ALL --network none --read-only --tmpfs /tmp:rw,nosuid,nodev,size=32m --pids-limit 64 --memory 256m --security-opt no-new-privileges=true --security-opt apparmor=yuki-bot-codemode --security-opt seccomp="$HERE/yuki-codemode-seccomp.json" sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b python - <container-probe.py
