"""Build Telegram and verify original attachment delivery on this native platform."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from package import build

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests/peers"))
from telegram_media_wire import exercise as check_original_media


def run(root, output):
    output.mkdir(parents=True, exist_ok=False)
    curl_program = os.environ.get("YUKI_TELEGRAM_CURL") or shutil.which("curl") or "curl"
    curl = subprocess.check_output(
        [curl_program, "--version"], text=True, encoding="utf-8"
    )
    version = tuple(map(int, curl.split()[1].split(".")))
    if version < (8, 3, 0):
        raise RuntimeError(
            "Telegram attachments require curl 8.3 or newer on the selected PATH"
        )
    package = output / "packages"
    built = build(root, "telegram", package)
    assert all(
        hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
        for name, digest in built["artifacts"].items()
    )
    binary = package / (
        "yuki-telegram.exe" if sys.platform == "win32" else "yuki-telegram"
    )
    media = check_original_media(binary, output / "original-media")
    (output / "original-media.json").write_text(
        json.dumps(media, indent=2) + "\n", encoding="utf-8"
    )
    cases = {}
    for scenario in [
        "confirmed",
        "denied",
        "rejected",
        "lost",
        "caption",
        "caption-lost",
        "forget",
        "reply",
        "reply-text",
        "reply-rejected",
    ]:
        case = output / scenario
        with (output / (scenario + ".log")).open("xb") as log:
            subprocess.run(
                [
                    sys.executable,
                    str(root / "tests/peers/telegram_attachment_delivery.py"),
                    "--package",
                    str(package),
                    "--out",
                    str(case),
                    "--scenario",
                    scenario,
                ],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=100,
            )
        cases[scenario] = json.loads((case / "attachment-delivery.json").read_bytes())
    receipt = {
        "status": "PASS",
        "card": "EXT-004",
        "card_status": "PARTIAL_OUTBOUND_ATTACHMENT_VERIFIED",
        "pending": ["recall", "typing-lifecycle"],
        "platform": platform.platform(),
        "curl": {"program": curl_program, "version": curl},
        "package": built,
        "cases": cases,
        "files": {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file() and not p.name.startswith("._")
        },
    }
    (output / "telegram-delivery.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": "PASS", "platform": receipt["platform"], "cases": len(cases)}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.out.resolve())
