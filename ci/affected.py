"""Print the independent release units affected by changed paths."""

import argparse
import json
from pathlib import Path
import subprocess

from units import select_units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--changed", nargs="*", default=[])
    parser.add_argument("--event", type=Path, help="GitHub event JSON; diff exact base/head commits")
    args = parser.parse_args()
    changed = args.changed
    if args.event:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        pull = event.get("pull_request", {})
        base = pull.get("base", {}).get("sha") or event.get("before")
        head = pull.get("head", {}).get("sha") or event.get("after") or "HEAD"
        command = ["git", "diff", "--name-only", "-z", base, head] if base and set(base) != {"0"} else ["git", "ls-files", "-z"]
        result = subprocess.run(command, cwd=args.root, check=True, capture_output=True)
        changed = [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]
    print(json.dumps(select_units(args.root, changed)))


if __name__ == "__main__":
    main()
