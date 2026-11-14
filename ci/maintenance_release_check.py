"""Replay the witnessed Rust maintenance plugin against the published 1.2 Host."""

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from package import sha256

TAG = "plugin/memory-maintenance/v0.1.0"


def checked_member(archive, entry):
    data = archive.read("evidence/" + entry["path"])
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError("changed release member: " + entry["path"])
    return data


def unpack_worker(worker_bytes, destination, system, version):
    with ZipFile(io.BytesIO(worker_bytes)) as worker:
        raw = worker.read("package-manifest.json")
        manifest = json.loads(raw)
        members = manifest["artifacts"]
        if (manifest["unit_id"] != "memory-maintenance"
                or manifest["version"] != version
                or sorted(worker.namelist()) != sorted(["package-manifest.json", *members])):
            raise ValueError("unexpected maintenance package")
        destination.mkdir()
        for name, digest in members.items():
            data = worker.read(name)
            if (name in {"", ".", ".."} or any(c in name for c in "/\\:")
                    or hashlib.sha256(data).hexdigest() != digest):
                raise ValueError("changed maintenance package member: " + name)
            (destination / name).write_bytes(data)
        (destination / "package-manifest.json").write_bytes(raw)
        if system != "windows":
            (destination / "yuki-memory-maintenance").chmod(0o700)
        return manifest


def replay(root, output, bundle, exercise, *, qualify=False, published_plugin=None):
    lock = json.loads((root / "compat/stable-1.2/source.lock.json").read_bytes())
    path = Path(bundle).resolve(strict=True)
    expected = lock["asset_sha256"]["yuki-plugin-base-1.2.0.zip"]
    if not lock["published"] or sha256(path) != expected:
        raise ValueError("published plugin base 1.2.0 bundle required")
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    host_asset = lock["assets"]["host-" + system]
    sdk_asset = lock["assets"]["rust-sdk"]
    witness = lock["maintenance_witnesses"][system]
    sdk = json.loads((root / "compat/core-035/source.lock.json").read_bytes())
    published = published_plugin is not None
    if published and qualify:
        raise ValueError("choose the released package or the build candidate")
    if published:
        release = json.loads((root / "compat/memory-maintenance-0.1.0/release.lock.json").read_bytes())
        plugin_archive = Path(published_plugin).resolve(strict=True)
        plugin_asset = release["platforms"][system]
        if (release["status"] != "published-and-downloaded" or release["tag"] != TAG
                or release["host"]["archive_sha256"] != expected
                or release["sdk"]["sha256"] != sdk_asset["sha256"]
                or sha256(plugin_archive) != plugin_asset["sha256"]):
            raise ValueError("published maintenance plugin does not match the release lock")
    if qualify:
        qualification = json.loads((root / "releases/memory-maintenance/0.1.0/qualification.json").read_bytes())
        prepare = runpy.run_path(str(root / "ci/publish-plugin.py"))["prepare"]

        def install_release(_root, _unit, destination):
            return prepare(root, TAG, destination, candidate=qualification)

    with ZipFile(path) as archive:
        host_bytes = checked_member(archive, host_asset)
        if not published and not qualify:
            worker_bytes = checked_member(archive, witness["package"])
        checked_member(archive, sdk_asset)
        checked_member(archive, lock["assets"]["python-sdk"])

    with TemporaryDirectory(prefix="yuki-maintenance-", dir="/tmp" if system == "macos" else None) as scratch:
        host = Path(scratch) / Path(host_asset["path"]).name
        host.write_bytes(host_bytes)
        host.chmod(0o700)
        surface = json.loads(subprocess.check_output([host, "plugin-surface"], timeout=20))
        required = {"maintenance.audit", "maintenance.audit.apply", "maintenance.reembed", "forget.request"}
        if (surface["version"] != lock["sdk"]["rust"]
                or surface["candidate_source"] != lock["source_commit"]
                or surface["surface_sha256"] != lock["surface_sha256"]
                or not required.issubset(surface["methods"])):
            raise ValueError("released Host differs from the pinned maintenance contract")

        def install_witness(_root, _unit, destination):
            if published:
                package = unpack_worker(plugin_archive.read_bytes(), destination, system, "0.1.0")
                binary = "yuki-memory-maintenance.exe" if system == "windows" else "yuki-memory-maintenance"
                if (package["release_tag"] != TAG or package["artifacts"][binary] != plugin_asset["binary_sha256"]
                        or package["source"]["release_inputs_sha256"] != plugin_asset["release_inputs_sha256"]):
                    raise ValueError("released package differs from the qualified plugin")
                return package
            return unpack_worker(worker_bytes, destination, system, "0.1.0-alpha.4")

        pin = (lock if qualify or published else
               {**lock, "sdk": sdk["sdk"], "rust_crate_sha256": sdk["rust_crate_sha256"]})
        native = {**host_asset, "binary_sha256": host_asset["sha256"], "archive_sha256": expected}
        label, result = exercise(
            root, output, integrity=True, retain=True,
            released_host=(host, pin, native),
            package_builder=install_release if qualify else install_witness,
        )
    result["published_base"] = {
        "tag": lock["tag"], "source_commit": lock["source_commit"], "sdk": lock["sdk"],
        "rust_sdk_sha256": sdk_asset["sha256"], "archive_sha256": expected,
        "surface_sha256": lock["surface_sha256"], "database_reader": lock["database_reader"],
    }
    if published:
        result["plugin"].update(release_tag=TAG, source_commit=release["source_commit"],
                                package_sha256=plugin_asset["sha256"], published=True)
        result.update(card_status="PASS", candidate_only=False, remaining=[])
    elif qualify:
        package = json.loads((output / "packages/package-manifest.json").read_bytes())
        result["plugin"].update(release_tag=package["release_tag"],
                                release_inputs_sha256=package["source"]["release_inputs_sha256"],
                                published=False)
        result["card_status"] = "RELEASE_CANDIDATE_VERIFIED"
        result["remaining"] = ["publish and download the independent plugin"]
    else:
        result["plugin"].update(source_commit=witness["source_commit"],
                                package_sha256=witness["package"]["sha256"], published=False)
    return label, result
