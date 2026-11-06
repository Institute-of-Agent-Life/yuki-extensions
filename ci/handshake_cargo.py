"""Build one isolated registry from checksum-locked crate distributions."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import tomllib
from urllib.request import urlopen


def registry_crate(package):
    if (not re.fullmatch(r"[A-Za-z0-9_-]+", package["name"])
            or not re.fullmatch(r"[A-Za-z0-9.+_-]+", package["version"])
            or not re.fullmatch(r"[0-9a-f]{64}", package["checksum"])):
        raise ValueError("invalid locked registry package")
    filename = f"{package['name']}-{package['version']}.crate"
    cache = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "registry/cache"
    cache = Path(os.environ.get("YUKI_CRATE_CACHE", cache))
    for cached in [cache / filename, *cache.glob("*/" + filename)]:
        if cached.is_file():
            data = cached.read_bytes()
            if hashlib.sha256(data).hexdigest() == package["checksum"]:
                return data
    url = f"https://static.crates.io/crates/{package['name']}/{filename}"
    with urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != package["checksum"]:
        raise ValueError("registry checksum mismatch: " + filename)
    # Only an explicitly selected CI cache is writable. Cargo's user cache is
    # read-only here. Different distributions of the same version cannot alias.
    if "YUKI_CRATE_CACHE" in os.environ:
        destination = cache / package["checksum"] / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as pending:
            pending.write(data)
            temporary = Path(pending.name)
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return data


def unpack_crate(data, directory, name):
    target = directory / name
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as crate:
        for member in crate.getmembers():
            path = directory / member.name
            if not path.resolve().is_relative_to(target) or not (member.isfile() or member.isdir()):
                raise ValueError("invalid crate member: " + member.name)
        crate.extractall(directory, filter="data")
    files = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(target.rglob("*")) if p.is_file()}
    checksum = {"files": files, "package": hashlib.sha256(data).hexdigest()}
    (target / ".cargo-checksum.json").write_text(json.dumps(checksum), encoding="utf-8")
    return target


def vendor_sdk(sdk, project, dependency_lock=None):
    directory = (project / "vendor").resolve()
    directory.mkdir()
    sdk_root = unpack_crate(sdk.read_bytes(), directory, sdk.stem)
    locked = tomllib.loads((dependency_lock or sdk_root / "Cargo.lock").read_text(encoding="utf-8"))
    for entry in locked["package"]:
        if entry["name"] == "yuki-plugin-sdk":
            if "checksum" in entry and entry["checksum"] != hashlib.sha256(sdk.read_bytes()).hexdigest():
                raise ValueError("consumer lock selected a different SDK distribution")
            continue
        if "source" not in entry:
            # The local binary described by this consumer's own project lock.
            if entry["name"] != tomllib.loads((project / "Cargo.toml").read_text(encoding="utf-8"))["package"]["name"]:
                raise ValueError("undeclared local source in consumer lock")
            continue
        if entry["source"] != "registry+https://github.com/rust-lang/crates.io-index":
            raise ValueError("unexpected registry: " + entry["name"])
        data = registry_crate(entry)
        unpack_crate(data, directory, f"{entry['name']}-{entry['version']}")
    config_dir = project / ".cargo"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[source.crates-io]\nreplace-with = "preview"\n[source.preview]\ndirectory = "vendor"\n',
        encoding="utf-8")
