"""Byte-preserving observer of the native host and the executable it starts."""
import json
from pathlib import Path
import subprocess
import sys
import threading


def observe(program, trace, *args, stderr=None, cut_file=None):
    lock=threading.Lock()
    child=subprocess.Popen([program,*args],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=stderr)
    proposals = set()
    def copy(stream, sink, direction):
        try:
            for line in stream:
                frame = json.loads(line)
                with lock, Path(trace).open("a",encoding="utf-8") as log:
                    row = {"direction": direction, "frame": frame}
                    if cut_file is not None:
                        if direction == "from_plugin" and frame.get("method") == "participation.self_propose":
                            proposals.add(frame["id"])
                        elif (direction == "from_host" and frame.get("id") in proposals
                              and "result" in frame and cut_file.is_file()):
                            row["forwarded"] = False
                            print(json.dumps(row), file=log)
                            child.kill()
                            cut_file.unlink()
                            return
                    print(json.dumps(row),file=log)
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
    program, trace, *arguments = sys.argv[1:]
    cut_file = None
    if arguments[:1] == ["--cut-self-reply"]:
        _, name, *arguments = arguments
        cut_file = Path(name)
    observe(program, trace, *arguments, cut_file=cut_file)
