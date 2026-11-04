"""Verify the unchanged source port against the historical wheel on Windows.

This is preparation for EXT-007, not its cross-repository acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        parser.error("use a new evidence directory")
    connector = Path(__file__).resolve().parents[1]
    source = json.loads((connector / "packaging/source.lock.json").read_text(encoding="utf-8"))
    commands = []
    report = {"status": "FAIL", "scope": "unchanged-source-and-historical-wheel preparation",
              "card_status": "BLOCKED", "blockers": ["CORE-002 immutable v4-oracle-index.json not delivered"],
              "source_commit": source["commit"], "historical_ci": source["historical_ci"],
              "platform": platform.platform(), "python": sys.version, "commands": commands}

    def call(argv, cwd=connector, timeout=600):
        print("Source check:", " ".join(map(str, argv[:4])), flush=True)
        result = subprocess.run(list(map(str, argv)), cwd=cwd, text=True, capture_output=True,
                                env={k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "VIRTUAL_ENV"}},
                                timeout=timeout)
        commands.append({"command": list(map(str, argv)), "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            raise RuntimeError(f"source check failed: {argv[0:4]}; see recorded command output")
        return result

    try:
        for name, expected in source["original_files_sha256"].items():
            actual = hashlib.sha256((connector / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError("original source changed before baseline run: " + name)
        report["original_files_hash_checked"] = len(source["original_files_sha256"])
        wheel = Path(os.environ["YUKI_BASELINE_WHEEL"])
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != source["historical_ci"]["wheel_sha256"]:
            raise ValueError("historical wheel SHA mismatch")
        work = output / "work"
        work.mkdir()
        env = work / "env"
        call(["uv", "venv", "--python", sys.executable, env])
        python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        requirements = work / "requirements.txt"
        call(["uv", "export", "--frozen", "--all-groups", "--no-emit-project", "--output-file", requirements])
        call(["uv", "pip", "install", "--python", python, "--require-hashes", "--no-index",
              "--find-links", os.environ["UV_FIND_LINKS"], "-r", requirements])
        call(["uv", "pip", "install", "--python", python, "--no-deps", wheel])
        call([python, "-I", "-c", "import importlib.util,importlib.metadata; "
              "assert importlib.util.find_spec('yuki') is None; "
              "import yuki_agent_connector; "
              "assert yuki_agent_connector.__version__ == importlib.metadata.version('yuki-agent-connector') == '0.4.3'"])
        call([python, "-m", "ruff", "check", "src", "tests", "scripts"])
        call([python, "-m", "mypy", "src"])
        call([python, "-m", "pytest", "-q", "--junitxml", output / "baseline-tests.xml"], timeout=1200)
        junit = ET.parse(output / "baseline-tests.xml")
        report["pytest_suites"] = [dict(s.attrib) for s in junit.iter("testsuite")]
        report["pytest_skips"] = [{"case": c.attrib, "reason": s.attrib} for c in junit.iter("testcase") for s in c.findall("skipped")]
        data = work / "empty-device"
        call([python, "-I", "-c", "from pathlib import Path; "
              "from yuki_agent_connector.config import Config; "
              f"Config('ws://127.0.0.1:9', 'source-only-device', 'test-only-no-credential').save(Path({str(data / 'config.json')!r}))"])
        doctor = call([python, "-m", "yuki_agent_connector", "--data-dir", data, "doctor"])
        if json.loads(doctor.stdout) != []:
            raise ValueError("empty-device doctor unexpectedly inspected a native instance")
        report["status"] = "PASS"
        report["not_verified"] = ["new connector distribution", "CORE-002 wire oracle consumption",
                                  "new Rust Host integration", "real provider login/model call", "installed OS service"]
    except Exception:
        report["failure"] = traceback.format_exc()
        traceback.print_exc()
    finally:
        payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (output / "source-preparation.json").write_bytes(payload)
        manifest = {"scope": report["scope"], "status": report["status"], "card_status": report["card_status"],
                    "source_snapshot_sha256": os.environ.get("YUKI_SOURCE_SNAPSHOT_SHA256"),
                    "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
        (output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
