"""Relay the real worker, with one test-only cut after Host commit."""

import json
from pathlib import Path
import subprocess
import sys
import threading


def main():
    executable, trace, control = map(Path, sys.argv[1:4])
    mode = sys.argv[4] if len(sys.argv) == 5 else "--rebuild-only"
    child = subprocess.Popen([executable, mode], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    (control / "relay-process.json").write_text(json.dumps({"child": child.pid}), encoding="utf-8")
    requests = {}
    lock = threading.Lock()

    def record(direction, frame):
        with trace.open("a", encoding="utf-8") as f:
            print(json.dumps({"direction": direction, "frame": frame}), file=f)

    def receive_host():
        for line in sys.stdin.buffer:
            frame = json.loads(line)
            with lock:
                record("from_host", frame)
                request = requests.get(frame.get("id")) if "method" not in frame else None
                operation = request[1] if request and request[0] == "maintenance.extract.apply" else None
                model_cut = control / "kill-model-call"
                if request and request[0] == "llm.complete" and frame.get("result") and model_cut.is_file() and model_cut.read_text() == request[1]:
                    model_cut.unlink()
                    child.kill()
                    (control / "model-paid-before-kill.json").write_bytes(line)
                    return
                cut = control / "kill-operation"
                if operation and frame.get("result") and cut.is_file() and cut.read_text() == operation:
                    cut.unlink()
                    child.kill()
                    (control / "committed-before-kill.json").write_bytes(line)
                    return
                mismatch = control / "mismatch-operation"
                if operation and frame.get("result") and mismatch.is_file() and mismatch.read_text() == operation:
                    mismatch.unlink()
                    frame["result"]["applied"] = []
                    line = json.dumps(frame).encode() + b"\n"
            try:
                child.stdin.write(line)
                child.stdin.flush()
            except BrokenPipeError:
                return
        child.stdin.close()

    threading.Thread(target=receive_host, daemon=True).start()
    for line in child.stdout:
        frame = json.loads(line)
        with lock:
            record("from_plugin", frame)
            method = frame.get("method")
            if method == "maintenance.extract.apply":
                requests[frame["id"]] = (method, frame["params"]["operation"])
            elif method == "llm.complete":
                requests[frame["id"]] = (method, frame["params"]["call_id"])
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    child.wait(timeout=5)


if __name__ == "__main__":
    main()
