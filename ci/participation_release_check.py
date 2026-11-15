"""Replay the participation release profile with the published Plugin Base 1.3 Host."""

import hashlib
import json
from pathlib import Path
import platform
import runpy
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from maintenance_release_check import checked_member, unpack_worker
from participation_rule import run as replay_rule
from participation_semantic import run as replay_semantic
from rebuild_intake import sha

TAG = "plugin/participation/v0.1.0"


def replay(root, output, host_bundle, library, published_plugin=None):
    host = json.loads((root / "compat/stable-1.3/source.lock.json").read_bytes())
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    bundled_host = host["assets"]["host-" + system]
    expected_bundle = host["asset_sha256"]["yuki-plugin-base-1.3.0.zip"]
    if not host["published"] or sha(host_bundle) != expected_bundle:
        raise ValueError("Published Plugin Base 1.3.0 archive required")

    profile = root / "releases/participation/0.1.0"
    inputs = json.loads((profile / "qualification.json").read_bytes())
    packages = output / "packages"
    if published_plugin is None:
        prepare = runpy.run_path(str(root / "ci/publish-plugin.py"))["prepare"]
        package = prepare(root, TAG, packages, candidate=inputs)
    else:
        release = json.loads((root / "compat/participation-0.1.0/release.lock.json").read_bytes())
        asset = release["platforms"][system]
        if (release["status"] != "published-and-downloaded" or release["tag"] != TAG
                or release["host"]["archive_sha256"] != expected_bundle
                or release["host"]["source_commit"] != host["source_commit"]
                or release["sdk"]["version"] != host["sdk"]["rust"]
                or release["sdk"]["sha256"] != host["rust_crate_sha256"]
                or sha(published_plugin) != asset["sha256"]):
            raise ValueError("Published participation package differs from its release lock")
        package = unpack_worker(published_plugin.read_bytes(), packages, system, "0.1.0", unit_id="participation")
        if package["source"]["release_inputs_sha256"] != asset["release_inputs_sha256"]:
            raise ValueError("Published participation package does not bind its release inputs")

    binary = "yuki-participation.exe" if system == "windows" else "yuki-participation"
    worker = packages / binary
    if package["release_tag"] != TAG or package["source"]["sdk_contract"] != "compat/stable-1.3/source.lock.json":
        raise ValueError("Participation release uses a different contract")
    library_pin = json.loads((packages / "source.lock.json").read_bytes())
    if sha(library) != library_pin["source_sha256"]:
        raise ValueError("Packaged participation library digest differs")
    if package["artifacts"][binary] != sha(worker):
        raise ValueError("Participation executable differs from its manifest")
    if published_plugin is not None and package["artifacts"][binary] != asset["worker_sha256"]:
        raise ValueError("Participation executable differs from the published release")

    with TemporaryDirectory(prefix="ext025-stable-") as directory:
        scratch = Path(directory)
        executable = scratch / Path(bundled_host["path"]).name
        with ZipFile(host_bundle) as archive:
            executable.write_bytes(checked_member(archive, bundled_host))
            for role in ("rust-sdk", "python-sdk"):
                checked_member(archive, host["assets"][role])
        executable.chmod(0o700)
        surface = json.loads(subprocess.check_output([executable, "plugin-surface"], timeout=20))
        required = {"observer.event", "participation.source", "participation.promote", "participation.feedback",
                    "llm.complete", "llm.result"}
        if (surface["candidate_source"] != host["source_commit"] or surface["version"] != host["sdk"]["rust"]
                or surface["surface_sha256"] != host["surface_sha256"] or not surface["selected_by_default"]
                or not required.issubset(surface["methods"])):
            raise ValueError("Published Host surface differs from its pin")
        rule_out = output / "native-rule"
        rule_out.mkdir()
        rule = replay_rule(scratch / "rule", executable, worker, rule_out)
        review_out = output / "native-semantic"
        review_out.mkdir()
        replayed = replay_semantic(scratch / "review", executable, worker, packages / "semantic_bridge.py", library, review_out)
        installed = json.loads(subprocess.check_output(
            [executable, "--data", scratch / "reader", "init", "--memory-mode", "lexical-only"], timeout=30,
        ))
        if installed["schema_version"] != host["database_reader"]:
            raise ValueError("Installed Host reader differs from its pin")

    inputs_sha256 = hashlib.sha256(json.dumps(inputs["inputs"], sort_keys=True).encode()).hexdigest()
    if package["source"]["release_inputs_sha256"] != inputs_sha256:
        raise ValueError("Participation release input inventory differs")
    result = {
        "status": "PASS", "card_status": "PASS" if published_plugin else "RELEASE_CANDIDATE_VERIFIED",
        "published": published_plugin is not None, "platform": system, "tag": TAG,
        "host": {"published": True, "tag": host["tag"], "source_commit": host["source_commit"],
                 "archive_sha256": expected_bundle, "binary_sha256": bundled_host["sha256"],
                 "surface_sha256": host["surface_sha256"], "database_reader": host["database_reader"]},
        "sdk": {"versions": host["sdk"], "rust_sha256": host["rust_crate_sha256"]},
        "library": library_pin, "worker_sha256": sha(worker),
        "package_manifest_sha256": sha(packages / "package-manifest.json"),
        "release_inputs_sha256": inputs_sha256, "rule": rule, **replayed,
    }
    if published_plugin:
        result["release_package_sha256"] = sha(published_plugin)
        result["release_source_commit"] = release["source_commit"]
    return "ordinary-replay.json", result
