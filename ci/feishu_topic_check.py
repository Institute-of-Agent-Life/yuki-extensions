"""Replay the original Feishu/Lark topic root through real native admission and ACKs."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

from package import build

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests/peers"))
from telegram_attachment_delivery import materialize


def run(root, output, contract="core-038-topic", *, package_source=None, released_host=None):
    output.mkdir(parents=True, exist_ok=False)
    package = output / "packages"
    if package_source is None:
        built = build(root, "feishu", package)
    else:
        shutil.copytree(package_source, package, ignore=shutil.ignore_patterns("._*"))
        built = json.loads((package / "package-manifest.json").read_bytes())
    spec = importlib.util.spec_from_file_location(
        "feishu_ingress_case", root / "tests/cases/EXT-005.py"
    )
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    def original_package(root, unit, destination):
        assert unit == "feishu"
        assert all(
            hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
            for name, digest in built["artifacts"].items()
        )
        shutil.copytree(package, destination)
        return built

    def selected_host(root, work, contract):
        if released_host is not None:
            return released_host
        return materialize(root, work, contract)

    cases = {}
    for scenario, thread, root_message, expected_root in [
        ("original-root", "omt_shared", "om_root", "om_root"),
        ("first-thread-message", "omt_shared", "", "om_shared"),
        ("ordinary-group", "", "", None),
    ]:

        def sample(app):
            return {
                "message_type": "text",
                "content": json.dumps({"text": "@_user_1 original topic"}),
                "thread_id": thread,
                "root_id": root_message,
            }, [
                {"type": "mention", "native": app, "label": "@Yuki"},
                {"type": "text", "text": " original topic"},
                {"type": "reply", "native_id": "om_original"},
            ]

        destination = output / scenario
        destination.mkdir()
        with tempfile.TemporaryDirectory(prefix="fs-topic-") as temporary:
            name, proof = fixture.prepare(
                root,
                destination,
                contract=contract,
                package_builder=original_package,
                message_sample=sample,
                expected_topic=thread or None,
                native_topics=True,
                expected_topic_root=expected_root,
                host_materializer=selected_host,
                work_directory=Path(temporary) / "work",
            )
        (destination / name).write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
        cases[scenario] = {
            "status": proof["status"],
            "topic": thread or None,
            "topic_root": expected_root,
            "original_topic_roots": proof["original_topic_roots"],
            "durable_events": proof["durable_events"],
            "host_sha256": proof["host"]["binary_sha256"],
        }
    receipt = {
        "status": "PASS",
        "card": "EXT-006",
        "card_status": "ORIGINAL_TOPIC_ROUTING_VERIFIED",
        "cases": cases,
        "package": built,
        "paid_calls": 0,
        "pending": [
            "original native outbound effects",
            "media upload receipts",
            "owner disposition",
        ],
        "files": {
            p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.rglob("*"))
            if p.is_file()
            and not any(part.startswith("._") for part in p.relative_to(output).parts)
            and "work" not in p.relative_to(output).parts
        },
    }
    (output / "original-topic.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
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
    args = parser.parse_args()
    print(json.dumps(run(ROOT, args.out.resolve(), args.contract)["cases"]))
