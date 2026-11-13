"""Replay two hash-verified native packages on the same installed topic namespace."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/peers"))
from telegram_attachment_delivery import materialize


def packages(inputs, output):
    output.mkdir()
    result = {}
    for package in inputs:
        manifest = json.loads((package / "package-manifest.json").read_bytes())
        assert manifest["unit_id"] == "feishu"
        assert all(c["exit_code"] == 0 for c in manifest["commands"])
        for name, digest in manifest["artifacts"].items():
            assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
        version = manifest["version"]
        assert version not in result
        name = "yuki-feishu.exe" if os.name == "nt" else "yuki-feishu"
        target = output / (version + ".bin")
        shutil.copyfile(package / name, target)
        (sdk,) = [
            p
            for p in tomllib.loads((package / "Cargo.lock").read_text())["package"]
            if p["name"] == "yuki-plugin-sdk"
        ]
        result[version] = {
            "binary": target.name,
            "binary_sha256": manifest["artifacts"][name],
            "sdk_version": sdk["version"],
            "sdk_sha256": sdk["checksum"],
            "manifest_sha256": hashlib.sha256(
                (package / "package-manifest.json").read_bytes()
            ).hexdigest(),
        }
    return result


def run(root, old, new, output, contract="core-038-topic", prior_topic_root=False):
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location(
        "original_feishu_case", root / "tests/cases/EXT-005.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    with tempfile.TemporaryDirectory(
        prefix="fs-history-", dir="/tmp" if os.name != "nt" else None
    ) as scratch:
        name, proof = fixture.prepare(
            root,
            output,
            contract=contract,
            reader_archives=(old, new),
            reader_loader=packages,
            reader_versions=tuple(
                json.loads((package / "package-manifest.json").read_bytes())["version"]
                for package in (old, new)
            ),
            reader_prior_topic_root=prior_topic_root,
            native_topics=True,
            expected_topic="omt_shared",
            expected_topic_root="om_root",
            message_sample=lambda app: (
                {
                    "message_type": "text",
                    "content": json.dumps({"text": "@_user_1 original topic"}),
                    "thread_id": "omt_shared",
                    "root_id": "om_root",
                },
                [],
            ),
            host_materializer=materialize,
            work_directory=Path(scratch) / "work",
        )
    (output / name).write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--contract",
        choices=[
            "core-038-topic",
            "core-038-bounded-text",
            "core-038-original-filename",
            "core-025-native-mentions",
        ],
        default="core-038-topic",
    )
    parser.add_argument("--prior-topic-root", action="store_true")
    args = parser.parse_args()
    proof = run(
        ROOT,
        args.old.resolve(),
        args.new.resolve(),
        args.out.resolve(),
        args.contract,
        args.prior_topic_root,
    )
    print(
        json.dumps(
            {
                "status": proof["status"],
                "events": proof["events"],
                "original_topic_roots": proof["original_topic_roots"],
            }
        )
    )
