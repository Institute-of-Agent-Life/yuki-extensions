"""Transparent real-plugin relay with a controlled second-chunk delay for erasure."""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time

program, trace, control = sys.argv[1:]
control = Path(control)
child = subprocess.Popen([program], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
write_lock = threading.Lock()
log_lock = threading.Lock()
state_lock = threading.Lock()
race_handle = None
held_ids = set()


def log(direction, frame):
    with log_lock, Path(trace).open("a", encoding="utf-8") as f:
        print(json.dumps({"direction": direction, "frame": frame}), file=f)


def forward(frame):
    with write_lock:
        child.stdin.write((json.dumps(frame) + "\n").encode())
        child.stdin.flush()


def release(frame):
    deadline = time.monotonic() + 20
    while not (control / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        forward(frame)
    except (BrokenPipeError, ValueError):
        pass


def incoming():
    global race_handle
    try:
        for raw in sys.stdin.buffer:
            frame = json.loads(raw)
            log("from_host", frame)
            if (
                frame.get("method") == "media.process"
                and (frame["params"]["operation"] == "erase-race" or (control / "erase-next").exists())
            ):
                with state_lock:
                    race_handle = frame["params"]["handle"]
            with state_lock:
                held = frame.get("id") in held_ids and "result" in frame
            if held:
                (control / "held").touch()
                threading.Thread(target=release, args=(frame,), daemon=True).start()
            else:
                forward(frame)
    except (BrokenPipeError, ValueError):
        pass
    finally:
        child.stdin.close()


threading.Thread(target=incoming, daemon=True).start()
try:
    for raw in child.stdout:
        frame = json.loads(raw)
        log("from_plugin", frame)
        if frame.get("method") == "media.open":
            p = frame["params"]
            with state_lock:
                if p["handle"] == race_handle and p["offset"] > 0:
                    held_ids.add(frame["id"])
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
finally:
    child.kill()
    child.wait()
