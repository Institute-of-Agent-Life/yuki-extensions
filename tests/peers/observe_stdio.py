"""Byte-preserving observer of the native host and the executable it starts."""
import json
from pathlib import Path
import subprocess
import sys
import threading


def main():
    program, trace=sys.argv[1:]
    lock=threading.Lock()
    child=subprocess.Popen([program],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def copy(stream, sink, direction):
        try:
            for line in stream:
                with lock, Path(trace).open("a",encoding="utf-8") as log:
                    print(json.dumps({"direction":direction,"frame":json.loads(line)}),file=log)
                sink.write(line)
                sink.flush()
        except (OSError,ValueError):
            pass
    def to_plugin():
        copy(sys.stdin.buffer,child.stdin,"from_host")
        child.stdin.close()
    threading.Thread(target=to_plugin,daemon=True).start()
    try:
        copy(child.stdout,sys.stdout.buffer,"from_plugin")
    finally:
        child.kill()
        child.wait()


if __name__=="__main__":
    main()
