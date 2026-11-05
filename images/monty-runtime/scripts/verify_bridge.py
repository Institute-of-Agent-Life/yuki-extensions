"""Exercise real native snapshots through the private codec in disposable containers.

This verifies the engine/codec boundary, not CORE-034 identities or business effects.
Run on the authorized Linux Docker host with the original AppArmor profile loaded.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import time


def docker(*args, check=True):
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)
    if check and r.returncode:
        raise RuntimeError("docker command failed: " + r.stderr)
    return r


class Codec:
    def __init__(self, image, policy):
        self.cid = docker(
            "create", "--init", "-i", "--attach", "stdin", "--attach", "stdout",
            "--env", "PYTHONFAULTHANDLER=1",
            "--user", "10001:10001", "--cap-drop", "ALL", "--network", "none",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
            "--pids-limit", "64", "--memory", "1g",
            "--security-opt", "apparmor=yuki-bot-codemode",
            "--security-opt", "seccomp=" + str(policy), image,
        ).stdout.strip()
        self.proc = None
        try:
            self.inspection = json.loads(docker("inspect", self.cid).stdout)[0]
            assert self.inspection["Config"]["StdinOnce"] is True
            self.proc = subprocess.Popen(
                ["docker", "start", "-ai", self.cid], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
            )
            self.buffer = bytearray()
            self.ready = self.receive()
            assert self.ready["ready"] is True, self.ready
        except BaseException:
            self.close()
            raise

    def send(self, request):
        self.proc.stdin.write(json.dumps(request).encode() + b"\n")
        self.proc.stdin.flush()

    def receive(self):
        end = time.monotonic() + 45
        while b"\n" not in self.buffer:
            if time.monotonic() >= end:
                raise TimeoutError("codec reply timeout")
            if not select.select([self.proc.stdout], [], [], .1)[0]:
                continue
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("codec EOF: " + self.proc.stderr.read().decode())
            self.buffer.extend(chunk)
            assert len(self.buffer) <= 20 * 1024 * 1024
        raw, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        return json.loads(raw)

    def call(self, request):
        self.send(request)
        return self.receive()

    def exit_diagnostics(self):
        assert self.proc.poll() is not None, "collect diagnostics only after exit"
        logs = docker("logs", "--tail", "100", self.cid, check=False)
        return {
            "exit_code": self.proc.returncode,
            "container_state": json.loads(docker("inspect", self.cid).stdout)[0]["State"],
            "stdout": self.proc.stdout.read().decode("utf-8", "replace"),
            "stderr": self.proc.stderr.read().decode("utf-8", "replace"),
            "container_stdout": logs.stdout,
            "container_stderr": logs.stderr,
            "logs_exit_code": logs.returncode,
            "container_environment": self.inspection["Config"]["Env"],
        }

    def close(self):
        if self.proc:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                docker("kill", self.cid, check=False)
                self.proc.kill()
                self.proc.wait(timeout=5)
        return docker("rm", "-f", self.cid, check=False).returncode == 0

    def __enter__(self): return self
    def __exit__(self, *args):
        assert self.close(), "test container cleanup failed"


def restore_request(record, manifest):
    return {"op": "restore", "manifest": manifest, **{
        k: record[k] for k in ("snapshot", "snapshot_sha256", "saved", "counters")
    }}


def verify(image, policy):
    manifest = ["yuki_echo"]
    code = "a = yuki_echo({'x': 1})\nb = yuki_echo({'x': 1})\n[a, b]"
    report = {"image": image, "formal_card_acceptance": False, "scope": "real native codec only"}
    with Codec(image, policy) as first:
        report["contract"] = first.ready["contract"]
        before = first.call({"op": "start", "manifest": manifest, "code": code, "inputs": {}})
        assert before["outcome"]["status"] == "suspended", before
        first_call = before["outcome"]["call"]
        assert first_call["function_name"] == "yuki_echo"
        assert first_call["args"] == [{"x": 1}] and not first_call["kwargs"]
        assert hashlib.sha256(base64.b64decode(before["snapshot"])).hexdigest() == before["snapshot_sha256"]
    with Codec(image, policy) as second:
        restored = second.call(restore_request(before, manifest))
        assert restored["outcome"]["call"] == first_call, restored
        after = second.call({"op": "answer", "engine_call_id": first_call["engine_call_id"], "answer": {"kind": "value", "value": "first"}})
        assert after["outcome"]["status"] == "suspended", after
        second_call = after["outcome"]["call"]
        assert second_call["args"] == first_call["args"]
        assert second_call["engine_call_id"] != first_call["engine_call_id"]
    with Codec(image, policy) as third:
        restored_after = third.call(restore_request(after, manifest))
        assert restored_after["outcome"]["call"] == second_call, restored_after
        result = third.call({"op": "answer", "engine_call_id": second_call["engine_call_id"], "answer": {"kind": "value", "value": "second"}})
        assert result["outcome"]["status"] == "completed", result
        assert result["outcome"]["output"] == ["first", "second"], result
    report["two_equal_native_calls"] = {"first": first_call, "second": second_call, "result": result,
        "first_snapshot_sha256": before["snapshot_sha256"], "second_snapshot_sha256": after["snapshot_sha256"]}
    with Codec(image, policy) as bad:
        request = restore_request(before, manifest)
        corrupt = b"unreadable native snapshot"
        request.update(snapshot=base64.b64encode(corrupt).decode(), snapshot_sha256=hashlib.sha256(corrupt).hexdigest())
        result = bad.call(request)
        assert result.get("error") or result["outcome"]["status"] == "failed", result
        report["corrupt_snapshot"] = result
    with Codec(image, policy) as denied:
        result = denied.call({"op": "start", "manifest": manifest, "code": "not_in_manifest({'x': 1})", "inputs": {}})
        assert result["outcome"]["status"] == "failed", result
        report["frozen_projection_refusal"] = result
    # Confirm the native worker is actually consuming CPU in a blocked feed
    # before disconnecting, rather than cancelling before execution starts.
    with Codec(image, policy) as blocked:
        started = blocked.call({"op": "start", "manifest": manifest, "code": "yuki_echo({})\nwhile True:\n    pass", "inputs": {}})
        assert started["outcome"]["status"] == "suspended", started
        rows = docker("top", blocked.cid, "-eo", "pid,comm").stdout.splitlines()[1:]
        native = [int(row.split()[0]) for row in rows if row.split()[1] == "monty"]
        assert len(native) == 1, rows
        stat = Path(f"/proc/{native[0]}/stat")
        baseline = stat.read_text().split()
        blocked.send({"op": "answer", "engine_call_id": started["outcome"]["call"]["engine_call_id"], "answer": {"kind": "value", "value": None}})
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if int(stat.read_text().split()[13]) > int(baseline[13]): break
            time.sleep(.01)
        else: raise AssertionError("native infinite loop was not observed running")
        start = time.monotonic()
        blocked.proc.stdin.close()
        exit_code = blocked.proc.wait(timeout=5)
        diagnostics = blocked.exit_diagnostics()
        assert exit_code == 0, diagnostics
        elapsed = time.monotonic() - start
        assert not stat.exists() or stat.read_text().split()[21] != baseline[21]
        report["blocked_feed_disconnect"] = {"native_pid": native[0], "elapsed_seconds": elapsed,
            "original_native_process_gone": True, "container_state": json.loads(docker("inspect", blocked.cid).stdout)[0]["State"]}
    report["status"] = "PASS"
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--image", required=True); p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    assert args.image.startswith("sha256:") and len(args.image) == 71
    assert not args.out.exists(), "choose a new evidence path"
    policy = Path(__file__).resolve().parents[1] / "deploy/security/yuki-codemode-seccomp.json"
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == "57457313430e0bb513ccab8a6906c5e05ffc217459f9c5b01cc77d827dcedc81"
    result = verify(args.image, policy)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
