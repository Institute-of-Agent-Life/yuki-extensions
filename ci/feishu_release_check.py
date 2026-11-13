"""Qualify a standalone Feishu package on the published 1.1 Host."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tempfile
import zipfile

from package import sha256


TAG = "plugin/feishu/v0.1.0"
DOMAINS = ("feishu", "lark")
SCENARIOS = {"mention-caption": "confirmed", "recall": "confirmed", "denied": "failed"}


@contextmanager
def published_host(root):
    bundle = Path(os.environ["YUKI_STABLE_1_1_BUNDLE"]).resolve(strict=True)
    lock = json.loads((root / "compat/stable-1.1/source.lock.json").read_bytes())
    digest = sha256(bundle)
    if not lock["published"] or digest != lock["asset_sha256"]["yuki-plugin-base-1.1.0.zip"]:
        raise ValueError("published plugin base 1.1.0 bundle required")
    system = {"darwin": "macos", "linux": "linux", "windows": "windows"}[platform.system().lower()]
    host = lock["assets"]["host-" + system]
    with tempfile.TemporaryDirectory(prefix="yuki-feishu-stable-", dir="/tmp" if os.name != "nt" else None) as tmp:
        path = Path(tmp) / Path(host["path"]).name
        with zipfile.ZipFile(bundle) as archive:
            path.write_bytes(archive.read(host["path"]))
        if sha256(path) != host["sha256"]:
            raise ValueError("published Host binary changed")
        path.chmod(0o700)
        descriptor = json.loads(
            subprocess.check_output([path, "plugin-surface"], timeout=20)
        )
        if (descriptor["version"] != lock["sdk"]["rust"]
                or descriptor["candidate_source"] != lock["source_commit"]
                or descriptor["surface_sha256"] != lock["surface_sha256"]):
            raise ValueError("Host does not describe the pinned public contract")
        yield system, (path, lock, {"binary_sha256": host["sha256"], "sha256": digest})


def native(root, output):
    sys.path.insert(0, str(root / "tests/peers"))
    from feishu_delivery import exercise

    with published_host(root) as (system, released_host):
        _, lock, host = released_host
        prepare = runpy.run_path(str(root / "ci/publish-plugin.py"))["prepare"]
        package = output / "packages"
        manifest = prepare(root, TAG, package)
        if manifest["release_tag"] != TAG or manifest["published"]:
            raise ValueError("unexpected release candidate")
        cases = {}
        for domain in DOMAINS:
            for scenario, state in SCENARIOS.items():
                key = domain + "-" + scenario
                folder = output / key
                result = exercise(root, package, folder, domain, scenario, released_host=released_host)
                if (result["status"] != "PASS" or result["state"] != state
                        or not result["original_receipt_reopened"] or result["paid_calls"] != 0
                        or result["host_sha256"] != host["binary_sha256"]
                        or (state == "failed" and (result["native_requests"] or result["token_issuances"]))):
                    raise ValueError("published Host replay failed: " + key)
                cases[key] = {
                    "state": state, "native_requests": result["native_requests"],
                    "receipt_reopened": result["original_receipt_reopened"],
                    "sha256": sha256(folder / "delivery.json"),
                }
    binary = "yuki-feishu.exe" if os.name == "nt" else "yuki-feishu"
    return {"status": "PASS", "tag": TAG, "platform": system, "published": False,
            "host_sha256": host["binary_sha256"], "host_bundle_sha256": host["sha256"],
            "source_commit": lock["source_commit"], "rust_sdk_sha256": lock["rust_crate_sha256"],
            "binary_sha256": manifest["artifacts"][binary], "cases": cases, "paid_calls": 0}
