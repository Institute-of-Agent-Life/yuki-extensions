"""Execute one task's acceptance scenarios and write named evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import traceback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--preparation", action="store_true", help="run independent preparation, not card acceptance")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    case = root / "tests" / "cases" / (args.task + ".py")
    if not case.is_file() or case.parent != root / "tests" / "cases":
        parser.error("unknown acceptance case")
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "manifest.json").exists():
        parser.error("evidence already exists; select a new output directory")
    spec = importlib.util.spec_from_file_location("acceptance_case", case)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    status = "PASS"
    report = {}
    try:
        runner = module.prepare if args.preparation else module.run
        report_name, report = runner(root, args.out.resolve())
        status = report.get("status", "PASS")
        (args.out / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        status = "FAIL"
        (args.out / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True)
    manifest = {"task": args.task, "status": status,
                "phase": "preparation" if args.preparation else "acceptance",
                "card_status": report.get("card_status", status),
                "platform": platform.platform(), "python": sys.version,
                "source_commit": commit.stdout.strip() if commit.returncode == 0 else None,
                "source_snapshot_sha256": os.environ.get("YUKI_SOURCE_SNAPSHOT_SHA256"),
                "command": [sys.executable, "ci/check.py", args.task, *(["--preparation"] if args.preparation else []), "--out", str(args.out)],
                "files": {p.relative_to(args.out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(args.out.rglob("*")) if p.is_file() and not {"work", "packages"}.intersection(p.relative_to(args.out).parts)}}
    (args.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"task": args.task, "status": status, "out": str(args.out)}))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
