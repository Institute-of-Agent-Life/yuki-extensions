"""Run the original native isolation verifier against a pinned, fully built image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def verify(image, policy):
    assert image.startswith("sha256:") and len(image) == 71
    assert hashlib.sha256(policy.read_bytes()).hexdigest() == "57457313430e0bb513ccab8a6906c5e05ffc217459f9c5b01cc77d827dcedc81"
    def call(*args):
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)
    created = call("create", "--init", "--user", "10001:10001", "--cap-drop", "ALL",
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
        "--pids-limit", "64", "--memory", "1g", "--security-opt", "apparmor=yuki-bot-codemode",
        "--security-opt", "seccomp=" + str(policy), "--entrypoint", "python", image, "-c",
        "import runpy,asyncio,json;from pathlib import Path;"
        "ns=runpy.run_path('/opt/yuki-monty/verify_monty_isolation.py');"
        "print(json.dumps(asyncio.run(ns['verify'](Path('/opt/yuki-monty/monty'),Path('/opt/yuki-monty/monty-isolated')))))")
    if created.returncode: raise RuntimeError(created.stderr)
    cid = created.stdout.strip()
    try:
        result = call("start", "-a", cid)
        if result.returncode: raise RuntimeError(result.stderr)
        report = json.loads(result.stdout)
        assert report["verdict"] == "passed"
        assert report["worker"]["apparmor_profile"] == "yuki-bot-codemode//launcher//&yuki-bot-codemode//launcher//worker (enforce)"
        fields = dict(line.split(":", 1) for line in report["worker"]["status"].splitlines() if ":" in line)
        assert fields["Seccomp"].strip() == "2" and fields["NoNewPrivs"].strip() == "1"
        container = json.loads(call("inspect", cid).stdout)[0]
        assert container["Image"] == image
        assert not container["HostConfig"]["Binds"] and container["HostConfig"]["ReadonlyRootfs"]
        return {"image": image, "native": report, "container": container,
                "scope": "native image isolation", "formal_card_acceptance": False, "status": "PASS"}
    finally:
        removed = call("rm", "-f", cid)
        if removed.returncode: raise RuntimeError("test container cleanup failed: " + removed.stderr)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--image", required=True); p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(); assert not args.out.exists(), "choose a new evidence path"
    policy = Path(__file__).resolve().parents[1] / "deploy/security/yuki-codemode-seccomp.json"
    result = verify(args.image, policy)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "image": args.image}))
