"""Embedded offline installer for the signed, separately selected native base."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile


def commit_directory(stage, dst):
    """Atomically install a complete verified tree, refusing an existing destination."""
    if os.name == "nt":
        stage.rename(dst)  # MoveFileEx without MOVEFILE_REPLACE_EXISTING.
        return
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    paths = (os.fsencode(stage), os.fsencode(dst))
    if sys.platform == "darwin":
        result = libc.renamex_np(*paths, 4)  # RENAME_EXCL
    else:
        result = libc.renameat2(-100, paths[0], -100, paths[1], 1)  # AT_FDCWD, RENAME_NOREPLACE
    if result:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(dst))


def install_base(archive, dst, pin, plugin):
    machine = platform.machine().lower()
    target = (platform.system().lower(), {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine))
    selected = pin["platforms"].get("-".join(target))
    if not selected or (plugin and target != ("windows", "x86_64")):
        raise ValueError("no verified package on this native target")
    if dst.exists() or dst.is_symlink():
        raise ValueError("native destination must be new")
    with tempfile.TemporaryDirectory(prefix=".yuki-base-", dir=dst.parent) as tmp:
        tmp = Path(tmp)
        # Keep verification and materialization on the same private snapshot.
        snapshot = tmp / "base.zip"
        shutil.copyfile(archive, snapshot)
        with snapshot.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != selected["archive_sha256"]:
                raise ValueError("published base archive digest mismatch")
        with zipfile.ZipFile(snapshot) as z:
            for name, digest in pin["verifiers"].items():
                code = z.read("ci/" + name)
                if hashlib.sha256(code).hexdigest() != digest:
                    raise ValueError("packaged verifier mismatch")
                (tmp / name).write_bytes(code)
            sys.path.insert(0, str(tmp))
            import verify_base
            import verify_dist
            use_pinned_verifier(verify_dist)
            key = tmp / "signer.pub"
            key.write_bytes(pin["signer"].encode("ascii"))
            manifest = verify_base.verify_base(snapshot, key, selected["archive_sha256"], pin["source_commit"], target)
            if manifest["members"][manifest["binary"]] != selected["binary_sha256"]:
                raise ValueError("published binary differs from pin")
            stage = tmp / "installation"
            z.extractall(stage)
            host = stage / manifest["binary"]
            for member in z.infolist():
                if member.external_attr >> 16 & 0o111:
                    (stage / member.filename).chmod(0o755)
            host.chmod(0o755)
        if plugin:
            opt = pin["windows_web_fetch"]
            data = Path(plugin).read_bytes()
            if hashlib.sha256(data).hexdigest() != opt["sha256"]:
                raise ValueError("web-fetch package digest mismatch")
            relative = Path("plugins/web-fetch")
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if set(z.namelist()) != set(opt["members"]) or len(z.namelist()) != len(opt["members"]):
                    raise ValueError("unexpected web-fetch inventory")
                for n, h in opt["members"].items():
                    if Path(n).name != n or hashlib.sha256(z.read(n)).hexdigest() != h:
                        raise ValueError("invalid web-fetch member")
                z.extractall(stage / relative)
            package = stage / relative / "plugin.toml"
            plugin_config = package.read_text(encoding="utf-8")
            spec = tomllib.loads(plugin_config)
            owner = stage / "owner"
            subprocess.run([host, "--data", owner, "init", "--memory-mode", "lexical-only"],
                           check=True, capture_output=True, timeout=30)
            with (owner / "yuki.toml").open("a", encoding="utf-8", newline="\n") as settings:
                print("\n[[plugins]]", file=settings)
                for k, v in {"id":spec["id"], "namespace":"official.web-fetch", "grants":spec["grants"],
                             "env":spec["env"], "program":str(dst / relative / "yuki-web-fetch.exe")}.items():
                    print(k, "=", json.dumps(v), file=settings)
                print("[[plugins.tools]]" + plugin_config.split("[[tools]]", 1)[1], file=settings)
        commit_directory(stage, dst)
    print(json.dumps({"version": pin["version"], "source": pin["source_commit"], "binary":selected["binary_sha256"],
                      "platform": "-".join(target), "plugins": ["web-fetch"] if plugin else []}))


if __name__ == "__main__":
    archive, destination, locked, optional_file = sys.argv[1:]
    install_base(Path(archive), Path(destination).absolute(), json.loads(locked), optional_file)
