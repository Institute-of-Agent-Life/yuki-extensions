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


def reflect(source, host, output):
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
    return {"cases": cases, "plugin": built["artifacts"]}


def export_trace(source, folder, host, output):
    from control_intake import prepare

    previous = json.loads((source / "compat/core-037-export/source.lock.json").read_bytes())
    manifest = json.loads((folder / "candidate.json").read_bytes())
    if manifest["source_commit"] != previous["source_commit"]:
        raise ValueError("trace replay requires the core revision in the extension lock")
    system, arch = load(source / "compat/base/verify_dist.py").native_target()
    target = f"{system}-{arch}"
    archive, = folder.glob("yuki-control-preview-*.zip")
    if previous["schema_sha256"] != manifest["host_schema_sha256"]:
        raise ValueError("trace candidate schema differs from the reviewed lock")
    entry = {
        "archive": archive.name,
        "sha256": sha(archive),
        "binary_sha256": manifest["members"]["bin/" + host.name]["sha256"],
        "validation_manifest_sha256": manifest["validation"]["manifest_sha256"],
    }
    expected = previous["platforms"].get(target)
    if expected is not None and expected != entry:
        raise ValueError("trace candidate differs from the Windows lock")
    previous["platforms"][target] = entry
    previous["unverified_platforms"] = [x for x in previous.get("unverified_platforms", []) if x != target]
    with TemporaryDirectory(prefix="ext37-") as directory:
        staging = Path(directory)
        for name in ["catalog", "ci", "compat", "connector", "images", "plugins", "tests", "tools"]:
            shutil.copytree(source / name, staging / name, ignore=shutil.ignore_patterns("._*", "target"))
        (staging / "compat/core-037-export/source.lock.json").write_text(
            json.dumps(previous, indent=2) + "\n", encoding="utf-8")
        os.environ["YUKI_HOST_CANDIDATE"] = str(archive)
        replay = output / "export"
        replay.mkdir()
        result = prepare(staging, replay, real_plugin=True, export=True)
    return {"cases": result, "host_lock": entry}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card", choices=["EXT-035", "EXT-037"])
    parser.add_argument("revision")
    parser.add_argument("core_revision")
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    source, folder, output = (path.resolve() for path in (args.source, args.candidate, args.out))
    actual = subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    if actual != args.revision:
        raise ValueError("wrong extension checkout")
    sys.path.insert(0, str(source / "ci"))
    candidate = json.loads((folder / "candidate.json").read_bytes())
    if candidate["source_commit"] != args.core_revision or candidate["dirty"]:
        raise ValueError("wrong core candidate")
    archive, = folder.glob("yuki-*.zip")
    output.mkdir(exist_ok=False)
    with TemporaryDirectory(prefix="yuki-host-") as scratch:
        host = Path(scratch) / ("yuki-core.exe" if os.name == "nt" else "yuki-core")
        member = "bin/" + host.name
        with ZipFile(archive) as package:
            host.write_bytes(package.read(member))
        if sha(host) != candidate["members"][member]["sha256"]:
            raise ValueError("core executable differs from its package")
        host.chmod(0o700)
        if args.card == "EXT-035":
            verifier = load(source / "compat/base/verify_dist.py")
            verifier.verify(archive, folder / "signer.pub", args.core_revision, sha(archive),
                            candidate["members"]["fixtures/host-boundaries.json"]["sha256"])
            result = reflect(source, host, output)
        else:
            result = export_trace(source, folder, host, output)
        receipt = {
            "status": "PASS", "card": args.card, "platform": platform.platform(),
            "extension_commit": args.revision,
            "core_commit": args.core_revision, "core_archive_sha256": sha(archive),
            "core_binary_sha256": sha(host), "paid_calls": 0, **result,
        }
    (output / "native-replay.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
