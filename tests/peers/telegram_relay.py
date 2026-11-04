"""Test-only transparent relay. Break one real stdio connection before dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading


def main():
    exe, directory = sys.argv[1:]
    root = Path(directory)
    log = root / "wire.jsonl"
    lock = threading.Lock()

    def observe(direction, line):
        with lock, log.open("a", encoding="utf-8") as trace:
            trace.write(json.dumps({"direction": direction, "frame": json.loads(line)}) + "\n")

    with (root / "plugin.err").open("ab") as stderr:
        proc = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr)

        def host_input():
            try:
                for line in sys.stdin.buffer:
                    observe("from_host", line)
                    msg = json.loads(line)
                    if msg.get("id") == 12 and "result" in msg:
                        try:
                            (root / "lose-reply").rename(root / "reply-lost")
                        except FileNotFoundError:
                            pass
                        else:
                            proc.kill()
                            break
                    proc.stdin.write(line)
                    proc.stdin.flush()
            except (OSError, ValueError):
                pass
            finally:
                proc.stdin.close()

        threading.Thread(target=host_input, daemon=True).start()
        try:
            for line in proc.stdout:
                observe("from_plugin", line)
                msg = json.loads(line)
                if msg.get("method") == "gateway.inbound" and msg["params"]["source"] == "-80:2":
                    try:
                        (root / "disconnect").rename(root / "disconnected")
                    except FileNotFoundError:
                        pass
                    else:
                        break
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
        finally:
            proc.kill()
            proc.wait()
    os._exit(0)


if __name__ == "__main__":
    main()
