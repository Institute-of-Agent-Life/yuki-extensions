"""Byte-preserving observer of the native host and the executable it starts."""
import json
from pathlib import Path
import subprocess
import sys
import threading


def observe(program, trace, *args, stderr=None):
    lock=threading.Lock()
    child=subprocess.Popen([program,*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr)
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
        # This thread can still be reading when the child exits on its own.
        # Keep the blocking read off the interpreter's shared stdin buffer.
        with open(sys.stdin.fileno(), "rb", closefd=False) as source:
            copy(source,child.stdin,"from_host")
        child.stdin.close()
    threading.Thread(target=to_plugin,daemon=True).start()
    try:
        copy(child.stdout,sys.stdout.buffer,"from_plugin")
    finally:
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    return child.returncode


if __name__=="__main__":
    observe(*sys.argv[1:])
