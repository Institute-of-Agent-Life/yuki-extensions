"""Run a driver contract against a fresh installation of its independent wheel."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from package import build


def installed_case(root, output, observer, nodes):
    connector = root / "connector"
    work = output / "work"
    work.mkdir()
    package_dir = output / "packages"
    package = build(root, "connector", package_dir)
    wheel, = package_dir.glob("*.whl")
    wheel_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if package["artifacts"][wheel.name] != wheel_hash:
        raise ValueError("built wheel digest mismatch")
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}

    def run(*argv):
        result = subprocess.run(list(map(str, argv)), cwd=connector, env=env, capture_output=True,
                                text=True, timeout=600)
        with (output / "commands.txt").open("a", encoding="utf-8") as log:
            print(list(map(str, argv)), result.stdout, result.stderr, file=log)
        result.check_returncode()

    run("uv", "venv", "--python", sys.executable, work / "env")
    python = work / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    requirements = work / "requirements.txt"
    run("uv", "export", "--frozen", "--all-groups", "--no-emit-project", "--output-file", requirements)
    run("uv", "pip", "install", "--python", python, "--require-hashes", "-r", requirements)
    run("uv", "pip", "install", "--python", python, "--no-deps", wheel)
    trace = work / "peer.json"
    run(python, "-I", root / "tests/peers" / observer, trace, *nodes)
    report = json.loads(trace.read_bytes())
    if report["distribution"] != package["version"] or not report["cases"]:
        raise ValueError("installed peer has wrong version or no cases")
    if any(case["call"] != "passed" for case in report["cases"].values()):
        raise ValueError("driver case skipped or failed")
    return {"wheel": wheel.name, "sha256": wheel_hash, "lock_sha256": package["lock_sha256"], **report}
