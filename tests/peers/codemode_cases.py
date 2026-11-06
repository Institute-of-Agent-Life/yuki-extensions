"""Run native candidate fixtures; unsupported hosts never produce a mock pass."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run_cases(root, out, modes):
    if os.name != "nt" or not os.environ.get("YUKI_CODE_FIXTURE_ROOT"):
        raise RuntimeError("requires the prepared Windows Host + Arch native runtime; see EXT-023-024-sequences.md")
    if not os.environ.get("YUKI_CODE_PLUGIN_SHA256") or not os.environ.get("YUKI_CODE_LINUX_PLUGIN"):
        raise RuntimeError("pin the actual native Rust binary and SHA-256")
    work = out / "work"
    work.mkdir()
    cases = {}
    for mode in modes:
        result = subprocess.run([sys.executable, "-X", "utf8", str(root / "tests/peers/codemode_owner.py"),
                                 mode, str(work / mode)], capture_output=True, text=True, encoding="utf-8")
        case = out / mode
        case.mkdir()
        for path in (work / mode).glob("*"):
            if path.is_file():
                shutil.copy2(path, case / path.name)
        (case / "command.json").write_text(json.dumps({"exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr}, indent=2) + "\n", encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"native {mode} failed; see {case}")
        cases[mode] = json.loads((case / "result.json").read_bytes())
        assert cases[mode]["status"] == "PASS"
        from codemode_evidence import inspect_case
        analysis = inspect_case(case)
        (case / "native-identities.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    return {"status": "PASS", "card_status": "BLOCKED", "published": False,
            "scope": "real Windows Host and isolated native Rust/Monty candidate", "cases": cases}
