"""Observe real pipes; optionally break one submission before it reaches the writer."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def main():
    binary, directory = sys.argv[1:]
    root = Path(directory)
    proc = subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    lock = threading.Lock()

    def capture(stream, sink, direction):
        for line in stream:
            frame = json.loads(line)
            with lock, (root / "wire.jsonl").open("a", encoding="utf-8") as log:
                print(json.dumps({"direction": direction, "frame": frame}), file=log)
            if direction == "from_plugin" and frame.get("method") == "gateway.inbound":
                try:
                    (root / "break-before-writer").rename(root / "broken")
                except FileNotFoundError:
                    pass
                else:
                    break
            sink.write(line)
            sink.flush()

    def inputs():
        try:
            capture(sys.stdin.buffer, proc.stdin, "from_host")
        except (OSError, ValueError):
            pass
        finally:
            proc.stdin.close()

    threading.Thread(target=inputs, daemon=True).start()
    try:
        capture(proc.stdout, sys.stdout.buffer, "from_plugin")
    finally:
        proc.kill()
        proc.wait()
    os._exit(0)


if __name__ == "__main__":
    main()
