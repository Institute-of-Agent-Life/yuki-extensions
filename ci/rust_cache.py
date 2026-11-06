"""Identify an optional CI build cache without changing the package contract."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from units import inside, load_catalog, validate_unit


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_root():
    return Path(os.environ.get("YUKI_RUST_BUILD_ROOT", Path(tempfile.gettempdir()).resolve() / "yuki-rust-src")).resolve()


def plan(root: Path, unit: dict) -> dict:
    path = inside(root, unit["path"])
    files = validate_unit(root, unit)
    if unit["ecosystem"] != "rust":
        return {"enabled": False}
    compiler = subprocess.check_output(["rustc", "--version", "--verbose"], cwd=path, text=True)
    cargo = subprocess.check_output(["cargo", "--version"], cwd=path, text=True)
    inputs = {
        "policy": 1, "unit": unit,
        "platform": [platform.system(), platform.machine(), platform.release()],
        "image": {key: os.environ.get(key, "") for key in ("ImageOS", "ImageVersion")},
        "compiler": compiler, "cargo": cargo,
        "build_root": str(build_root()),
        "environment": {key: os.environ.get(key, "") for key in (
            "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_BUILD_TARGET",
            "RUSTC", "RUSTC_WRAPPER", "CC", "CXX", "AR", "CFLAGS", "CXXFLAGS")},
        "sources": {name: sha256(inside(path, name)) for name in files},
        "builders": {name: sha256(root / "ci" / name) for name in (
            "package.py", "rust_cache.py", "handshake_cargo.py", "units.py")},
    }
    if contract := unit["source"].get("sdk_contract"):
        lock = inside(root, contract)
        sdk = json.loads(lock.read_bytes())
        crate = lock.parent / f"yuki-plugin-sdk-{sdk['sdk']['rust']}.crate"
        digest = sha256(crate)
        if digest != sdk["rust_crate_sha256"]:
            raise ValueError("plugin SDK crate digest mismatch")
        inputs["sdk"] = {"contract_sha256": sha256(lock), "crate_sha256": digest}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    return {"enabled": True, "key": f"rust-v1-{platform.system()}-{platform.machine()}-{unit['unit_id']}-{digest}",
            "digest": digest, "inputs": inputs}


@contextmanager
def project_directory(source_root: Path, unit_id: str, digest: str):
    # Not part of the cache archive. Each build creates its own source/vendor
    # tree at a stable path, then removes only the directory it just created.
    parent = source_root / unit_id
    parent.mkdir(parents=True, exist_ok=True)
    # Windows registry crates contain long fixture names. Only scratch source
    # paths use the short prefix; the persisted target/key retain all 256 bits.
    project = parent / digest[:16]
    project.mkdir()  # Refuse to overwrite any pre-existing work, even after a crash.
    try:
        yield project
    finally:
        shutil.rmtree(project)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = plan(root, load_catalog(root)[args.unit])
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"enabled={str(result['enabled']).lower()}\n")
        if result["enabled"]:
            output.write(f"key={result['key']}\ndigest={result['digest']}\n")


if __name__ == "__main__":
    main()
