"""Replay a Rust extension against a native Host built at the pinned source."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from zipfile import ZipFile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_producer(path, candidate, card):
    report = json.loads(path.read_bytes())
    source = report["source"]
    assertions = report["assertions"]
    validation = candidate["validation"]
    proof = validation["verification"] if card == "CORE-039" else validation
    count_key = "passed_assertions" if card == "CORE-039" else "assertions"
    if (
        report["card"] != card
        or validation["card"] != card
        or report["status"] != "verified"
        or report["exit_code"] != 0
        or source["dirty"]
        or source["commit"] != candidate["source_commit"]
        or source["tree_sha256"] != candidate["source_tree_sha256"]
        or report["platform"] != proof["platform"]
        or not assertions
        or not all(item["passed"] is True for item in assertions)
        or len(assertions) != proof[count_key]
        or sha(path) != proof["manifest_sha256"]
    ):
        raise ValueError("candidate differs from the passing producer manifest")


def reflect(source, host, output, *, scheduled_tools=False, continuity=False):
    from package import build

    package = output / "packages"
    built = build(source, "memory-maintenance", package)
    peer = load(source / "tests/cases/EXT-034.py")
    reflection = load(source / "tests/cases/EXT-035.py")
    binary = package / ("yuki-memory-maintenance.exe" if os.name == "nt" else "yuki-memory-maintenance")
    schedule = tomllib.loads((package / "plugin-reflection-schedule.toml").read_text(encoding="utf-8"))
    tools = tomllib.loads((package / "plugin-reflection-tools.toml").read_text(encoding="utf-8"))
    event = tomllib.loads((package / "plugin-reflection.toml").read_text(encoding="utf-8"))
    rebuild = tomllib.loads((package / "plugin-rebuild.toml").read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="ext35-") as scratch:
        work = Path(scratch)
        policy = output / "policy"
        policy.mkdir()
        scheduled = output / "schedule"
        scheduled.mkdir()
        cases = {
            "foreground": reflection.exercise_schedule(
                peer, source, work / "f", policy, host, binary, schedule,
                daily_limit=1, foreground=True,
            ),
            "schedule": reflection.exercise_schedule(
                peer, source, work / "s", scheduled, host, binary, schedule,
            ),
            "events": reflection.exercise(peer, source, work / "e", output, host, binary, event),
            "tools": reflection.exercise_tool_receipts(
                peer, source, work / "t", output / "tools", host, binary, tools,
            ),
            "rebuild": {
                label: peer.check(source, output / label, work / label, host, binary, rebuild, allowed)
                for label, allowed in [("denied", False), ("authorized", True)]
            },
        }
        if scheduled_tools:
            cases["scheduled_tools"] = reflection.exercise_scheduled_tools(
                peer, source, work / "a", output / "scheduled-tools", host, binary, schedule,
            )
        if continuity:
            context = output / "scheduled-context"
            context.mkdir()
            cases["scheduled_context"] = reflection.exercise_schedule(
                peer, source, work / "c", context, host, binary, schedule,
                include_tools=True, include_context=True,
            )
    return {"cases": cases, "plugin": built["artifacts"]}


def export_trace(source, archive, candidate, member, archive_hash, output):
    from control_intake import prepare

    lock = json.loads((source / "compat/core-037-export/source.lock.json").read_bytes())
    if (
        candidate["source_commit"] != lock["source_commit"]
        or candidate["source_tree_sha256"] != lock["source_tree_sha256"]
        or candidate["host_schema_sha256"] != lock["schema_sha256"]
        or candidate["control_schema_sha256"] != lock["control_schema_sha256"]
        or candidate["database_schema_revision"] != lock["database_schema_revision"]
        or candidate["sdk_versions"] != lock["producer_sdk"]
    ):
        raise ValueError("trace candidate differs from the reviewed source or contract")
    target = f"{candidate['os']}-{candidate['arch']}"
    entry = {
        "archive": archive.name,
        "sha256": archive_hash,
        "binary_sha256": candidate["members"][member]["sha256"],
        "validation_manifest_sha256": candidate["validation"]["manifest_sha256"],
    }
    recorded = lock["platforms"].get(target)
    # Bind this run's verified build in a temporary lock. The checked-in
    # lock continues to identify the original candidate for ordinary intake.
    lock["platforms"][target] = entry
    if "unverified_platforms" in lock:
        lock["unverified_platforms"] = [x for x in lock["unverified_platforms"] if x != target]
    with TemporaryDirectory(prefix="ext37-") as directory:
        staging = Path(directory)
        checked = subprocess.check_output(["git", "-C", source, "ls-files", "-z"]).decode()
        for name in checked.split("\0"):
            if not name or name.startswith("artifacts/"):
                continue
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, path)
        (staging / "compat/core-037-export/source.lock.json").write_text(
            json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        os.environ["YUKI_HOST_CANDIDATE"] = str(archive)
        with TemporaryDirectory(prefix="t37-", dir="/tmp" if sys.platform == "darwin" else None) as replay:
            try:
                result = prepare(staging, Path(replay), real_plugin=True, export=True)
            finally:
                shutil.copytree(replay, output / "export", ignore=shutil.ignore_patterns("work", "._*"))
    return {"cases": result, "host_lock": entry, "recorded_host_lock": recorded}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", choices=["EXT-035", "EXT-035-scheduled-tools", "EXT-035-context", "EXT-037"])
    parser.add_argument("revision")
    parser.add_argument("core_revision")
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("producer_manifest", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    source, folder, output = (path.resolve() for path in (args.source, args.candidate, args.out))
    actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    if actual != args.revision:
        raise ValueError("wrong extension checkout")
    sys.path.insert(0, str(source / "ci"))
    verifier = load(source / "compat/base/verify_dist.py")
    system, arch = verifier.native_target()
    archive, = folder.glob("yuki-*.zip")
    raw = (folder / "candidate.json").read_bytes()
    candidate = json.loads(raw)
    if (
        candidate["source_commit"] != args.core_revision
        or candidate["dirty"]
        or (candidate["os"], candidate["arch"]) != (system, arch)
    ):
        raise ValueError("wrong core candidate or native target")
    with ZipFile(archive) as package:
        if package.read("candidate.json") != raw:
            raise ValueError("core archive and candidate metadata differ")
    producer_card = "CORE-037" if args.card == "EXT-037" else "CORE-039"
    verify_producer(args.producer_manifest, candidate, producer_card)
    archive_hash = sha(archive)
    member = "bin/yuki-core.exe" if system == "windows" else "bin/yuki-core"
    output.mkdir(exist_ok=False)
    if producer_card == "CORE-039":
        verifier.verify(
            archive, folder / "signer.pub", args.core_revision, archive_hash,
            candidate["members"]["fixtures/host-boundaries.json"]["sha256"],
        )
        with TemporaryDirectory(prefix="yuki-host-") as scratch:
            host = Path(scratch) / Path(member).name
            with ZipFile(archive) as package:
                host.write_bytes(package.read(member))
            host.chmod(0o700)
            result = reflect(source, host, output,
                             scheduled_tools=args.card in {"EXT-035-scheduled-tools", "EXT-035-context"},
                             continuity=args.card == "EXT-035-context")
    else:
        result = export_trace(source, archive, candidate, member, archive_hash, output)
    receipt = {
        "status": "PASS", "card": args.card, "platform": platform.platform(),
        "extension_commit": args.revision,
        "core_commit": args.core_revision, "core_archive_sha256": archive_hash,
        "core_source_tree_sha256": candidate["source_tree_sha256"],
        "core_binary_sha256": candidate["members"][member]["sha256"],
        "core_producer_manifest_sha256": sha(args.producer_manifest),
        "paid_calls": 0, **result,
    }
    (output / "native-replay.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
