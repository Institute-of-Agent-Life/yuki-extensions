"""Consume CORE-031's two packaged SDKs; keep publication a distinct gate."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from handshake_cargo import vendor_sdk
from handshake_wire import crosswire


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root, output):
    spec = importlib.util.spec_from_file_location("fetch_contract", root / "ci/fetch-contract.py")
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    contract = json.loads((root / "contracts.lock").read_bytes())
    archive = root / "compat/core-031/yuki-handshake-preview.zip"
    peer_src = root / "tests/peers"
    env = {k: v for k, v in os.environ.items() if k not in {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"}}

    with tempfile.TemporaryDirectory(prefix="ext002-") as tmp:
        work = Path(tmp).resolve()
        if work.is_relative_to(root):
            raise ValueError("consumer isolation requires a directory outside the checkout")
        meta, files = fetch.materialize(root, work / "contract")
        damaged = work / "tampered.zip"
        shutil.copyfile(archive, damaged)
        with zipfile.ZipFile(damaged, "a") as z:
            z.writestr("extra", b"wrong distribution")
        try:
            fetch.materialize(root, work / "invalid", damaged)
        except ValueError as exc:
            if "digest mismatch" not in str(exc):
                raise
            tamper = str(exc)
        else:
            raise AssertionError("modified archive accepted")

        def run(*argv, cwd=work):
            cmd = list(map(str, argv))
            proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
            with (output / "build.txt").open("a", encoding="utf-8") as log:
                print(cmd, proc.stdout, proc.stderr, file=log)
            proc.check_returncode()
            return proc.stdout.strip()

        project = work / "rust"
        shutil.copytree(peer_src / "handshake-rust", project, ignore=shutil.ignore_patterns("._*"))
        vendor_sdk(files["rust-sdk"], project)
        rustc = run("rustc", "+1.96.0", "--version")
        run("cargo", "+1.96.0", "build", "--offline", "--locked", "--release", cwd=project)
        rust_bin = project / "target/release" / ("ext002-rust-consumer.exe" if os.name == "nt" else "ext002-rust-consumer")
        python_project = work / "python"
        shutil.copytree(peer_src / "handshake-python", python_project, ignore=shutil.ignore_patterns("._*"))
        run(sys.executable, "-m", "venv", "--without-pip", work / "venv")
        # A consumer's local lock must reject the wrong wheel independently of the Rust lock.
        wheelhouse = work / "changed-wheel"
        wheelhouse.mkdir()
        changed_wheel = wheelhouse / files["python-sdk"].name
        with zipfile.ZipFile(files["python-sdk"]) as original, zipfile.ZipFile(changed_wheel, "w") as changed:
            for name in original.namelist():
                changed.writestr(name, original.read(name))
        assert sha(changed_wheel) != sha(files["python-sdk"])
        python = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        rejected = subprocess.run(["uv", "pip", "install", "--no-cache", "--python", python,
            "--no-index", "--find-links", wheelhouse, "--require-hashes",
            "-r", python_project / "requirements.txt"], cwd=work, env=env, capture_output=True, text=True,
            timeout=60)
        if rejected.returncode == 0 or "hash" not in rejected.stderr.lower():
            raise AssertionError("corrupted Python wheel was not rejected by the project lock: " + rejected.stderr)
        assert sha(project / "Cargo.lock") == sha(peer_src / "handshake-rust/Cargo.lock")
        run("uv", "pip", "install", "--python", python, "--no-index", "--find-links", files["python-sdk"].parent,
            "--require-hashes", "-r", python_project / "requirements.txt")
        installed = run(python, "-I", "-c",
            "from importlib.metadata import version; import yuki_plugin_sdk,sys; from pathlib import Path; "
            "assert Path(yuki_plugin_sdk.__file__).is_relative_to(Path(sys.prefix)); print(version('yuki-plugin-sdk'))")
        assert installed == meta["sdk_versions"]["python"]

        binding = {"namespace": "ext002.consumer", "manifest_revision": "ext002-r1", "grants": [], "declarations": []}
        binding_file = work / "binding.json"
        binding_file.write_text(json.dumps(binding), encoding="utf-8")
        host = [sys.executable, "-I", files["peer"], "--binding", binding_file, "--initiate"]
        index = json.loads(files["method-index"].read_bytes())
        errors = json.loads(files["schema"].read_bytes())["x-yuki"]["errors"]
        commands = {"rust": [rust_bin, binding_file],
                    "python": [python, "-I", python_project / "consumer.py", binding_file]}
        transcripts = {}
        for language, command in commands.items():
            wire = crosswire(command, host, work, binding, index, errors, env)
            transcripts[language] = asyncio.run(asyncio.wait_for(wire, timeout=30))
        return "handshake-preview.json", {"status": "PASS", "card_status": "AWAITING_PUBLICATION",
            "source_commit": meta["source_commit"], "bundle_sha256": sha(archive), "published": False,
            "sdk_versions": meta["sdk_versions"], "capabilities": meta["capabilities"],
            "member_sha256": {role: sha(path) for role, path in files.items()},
            "consumers": {"rust": {"binary_sha256": sha(rust_bin), "cargo_lock": sha(project / "Cargo.lock"),
                                   "compiler": rustc},
                          "python": {"script_sha256": sha(python_project / "consumer.py"),
                                     "requirements": sha(python_project / "requirements.txt"), "version": installed}},
            "python_lock_fault": {"rejected_exit_code": rejected.returncode, "stderr": rejected.stderr,
                                  "rust_lock_unchanged": True},
            "tampered_bundle": tamper, "producer_manifest_sha256": contract["files"]["manifest.json"],
            "wire": transcripts, "runtime_host": None, "official_plugins": []}


def run(root, output):
    return "published-sdk.json", {"status": "BLOCKED", "card_status": "AWAITING_PUBLICATION",
        "published": False, "reason": "The pinned CORE-031 bundle is an unpublished handshake preview.",
        "preview_command": "python ci/check.py EXT-002 --preparation --out artifacts/EXT-002/preview"}
