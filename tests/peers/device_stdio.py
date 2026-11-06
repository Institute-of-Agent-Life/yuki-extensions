"""Transparent real plugin relay; authority secrets are hashed before recording."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading

binary, trace = sys.argv[1], Path(sys.argv[2])
child = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
lock = threading.Lock()
secrets = {}


def redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {'handle', 'proof', 'token', 'secret', 'code'} and isinstance(item, str):
                replacement = 'sha256:' + hashlib.sha256(item.encode()).hexdigest()
                secrets[item] = replacement
                result[key] = replacement
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        for original, replacement in secrets.items():
            value = value.replace(original, replacement)
    return value


def copy(source, sink, direction):
    try:
        for raw in source:
            frame = json.loads(raw)
            with lock, trace.open('a', encoding='utf-8') as out:
                out.write(json.dumps({'direction': direction, 'frame': redact(frame),
                    'frame_sha256': hashlib.sha256(raw).hexdigest()}) + '\n')
            sink.write(raw)
            sink.flush()
    except (OSError, ValueError):
        pass


def inbound():
    try:
        copy(sys.stdin.buffer, child.stdin, 'from_host')
    finally:
        child.stdin.close()


threading.Thread(target=inbound, daemon=True).start()
try:
    copy(child.stdout, sys.stdout.buffer, 'from_plugin')
finally:
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
