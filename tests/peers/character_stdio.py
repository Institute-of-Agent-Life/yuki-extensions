"""Preserve real frames and briefly hold one selected reload before dispatch."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

program, trace, directory = sys.argv[1:]
control = Path(directory)
child = subprocess.Popen([program], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
log_lock = threading.Lock()
stopped = threading.Event()
state_lock = threading.Lock()
selected_id = None

def log(direction, frame):
    with log_lock, Path(trace).open('a', encoding='utf-8') as output:
        print(json.dumps({'direction': direction, 'frame': frame}), file=output)

def incoming():
    try:
        for raw in sys.stdin.buffer:
            frame = json.loads(raw)
            log('from_host', frame)
            with state_lock:
                selected = selected_id is not None and frame.get('id') == selected_id
            if selected and ('result' in frame or 'error' in frame):
                (control / 'reload-response').write_text(json.dumps(frame))
                deadline = time.monotonic() + 8
                while not (control / 'reload-reply-release').exists():
                    if stopped.is_set() or time.monotonic() >= deadline:
                        raise RuntimeError('selected reload reply was not released')
                    time.sleep(.01)
            child.stdin.write(raw); child.stdin.flush()
    except (OSError, ValueError):
        pass
    finally:
        stopped.set()
        child.stdin.close()

threading.Thread(target=incoming, daemon=True).start()
try:
    for raw in child.stdout:
        frame = json.loads(raw)
        log('from_plugin', frame)
        armed = control / 'reload-arm'
        params = frame.get('params', {})
        if (frame.get('method') == 'control.write' and params.get('method') == 'character.soul.reload'
                and armed.exists() and params.get('body', {}).get('request_id') == armed.read_text()):
            with state_lock:
                selected_id = frame['id']
            (control / 'reload-held').write_text(json.dumps(frame))
            deadline = time.monotonic() + 8
            while not (control / 'reload-release').exists():
                if stopped.is_set() or time.monotonic() >= deadline:
                    raise RuntimeError('selected reload transport was not released')
                time.sleep(.01)
        sys.stdout.buffer.write(raw); sys.stdout.buffer.flush()
finally:
    stopped.set()
    if child.poll() is None: child.kill()
    child.wait(timeout=5)
