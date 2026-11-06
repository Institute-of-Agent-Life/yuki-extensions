"""Original installed Connector address continuity; no backend replacement."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from package import build


def prepare(root, output):
    runtime = json.loads((root / "compat/wire4/address_cases/consumer.lock.json").read_bytes())
    for name, digest in runtime["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
    work = output / "work"
    work.mkdir()
    package = build(root, "connector", output / "packages")
    wheel = next((output / "packages").glob("*.whl"))
    environment = work / "environment"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    commands = []
    for argv in [["uv", "venv", "--python", sys.executable, str(environment)],
                 ["uv", "pip", "install", "--python", str(python), "--offline", "--no-index", str(wheel)]]:
        p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=180)
        commands.append({"argv": argv, "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr})
        if p.returncode: raise RuntimeError("locked Connector environment failed")
    (output / "environment.json").write_text(json.dumps(commands, indent=2), encoding="utf-8")
    p = subprocess.run([str(python), "-X", "utf8", str(root / "tests/peers/connector_address.py"),
                        str(root), str(output)], capture_output=True, text=True, encoding="utf-8", timeout=240)
    (output / "peer.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode: raise RuntimeError("original Connector address peer failed; see peer.txt")
    result = json.loads((output / "address-results.json").read_bytes())
    p = subprocess.run([str(python), "-X", "utf8", str(root / "tests/peers/connector_service_address.py"), str(output)],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    (output / "native-service.txt").write_text(p.stdout + p.stderr, encoding="utf-8")
    if p.returncode: raise RuntimeError("owned disabled Windows service test failed; see native-service.txt")
    result["cases"].append(json.loads((output / "native-service.json").read_bytes()))
    return "connector-address-continuity.json", {"status": "PASS",
        "card_status": "CANDIDATE_ON_UNPUBLISHED_EXT011", "connector_version": package["version"],
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "runtime_source_changed": False,
        "runtime_bindings": runtime,
        **result, "ext011_witness": "artifacts/EXT-011/connector-analysis-01/analysis.json",
        "not_claimed": ["a core Work authorization test", "public deployment", "formal publication"]}


def run(root, output):
    return "connector-address-continuity.json", {"status": "BLOCKED",
        "card_status": "AWAITING_PUBLISHED_EXT011", "reason":
        "Functional address continuity has a real Windows preparation entry; EXT-011 producer/consumer publication remains pending."}
