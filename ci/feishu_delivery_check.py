"""Replay original Feishu/Lark text effects on the pinned native Host."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from package import build

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/peers"))
from feishu_delivery import exercise
from feishu_upload import SCENARIOS as UPLOAD_SCENARIOS

SCENARIOS = [
    "private",
    "denied",
    "token-rejected",
    "group",
    "topic",
    "parts",
    "reply",
    "expiry",
    "lost",
    "rejected",
    "malformed",
    "recall",
    "recall-rejected",
    "recall-lost",
    "recall-denied",
]


def run(root, output, existing=None, scenarios=SCENARIOS):
    output.mkdir(parents=True, exist_ok=False)
    packages = output / "packages"
    if existing:
        shutil.copytree(existing, packages)
        package = json.loads((packages / "package-manifest.json").read_bytes())
    else:
        package = build(root, "feishu", packages)
    cases = []
    for domain in ["feishu", "lark"]:
        for scenario in scenarios:
            cases.append(
                exercise(
                    root, packages, output / (domain + "-" + scenario), domain, scenario
                )
            )
            print(domain, scenario, cases[-1]["state"], flush=True)
    result = {
        "status": "PASS",
        "card": "EXT-006",
        "card_status": (
            "ORIGINAL_UPLOAD_VERIFIED"
            if all(s.startswith("upload-") for s in scenarios)
            else "ORIGINAL_TEXT_DELIVERY_VERIFIED"
        ),
        "published": False,
        "package": package,
        "cases": cases,
        "paid_calls": 0,
        "pending": [
            *(
                []
                if all(s.startswith("upload-") for s in scenarios)
                else ["original uploads and dependent sends"]
            ),
            "structured native mentions",
            "owner disposition",
            "expanded published contract",
        ],
        "files": {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
            and not any(part.startswith("._") for part in p.relative_to(output).parts)
        },
    }
    (output / "original-delivery.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--uploads", action="store_true")
    parser.add_argument(
        "--scenario", choices=SCENARIOS + UPLOAD_SCENARIOS, action="append"
    )
    args = parser.parse_args()
    run(
        ROOT,
        args.out.resolve(),
        args.package.resolve() if args.package else None,
        args.scenario or (UPLOAD_SCENARIOS if args.uploads else SCENARIOS),
    )
