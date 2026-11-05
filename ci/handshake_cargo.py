"""Build one isolated registry from checksum-locked crate distributions."""
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tomllib
from urllib.request import urlopen


def registry_crate(package):
    filename = f"{package['name']}-{package['version']}.crate"
    cache = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")) / "registry/cache"
    cache = Path(os.environ.get("YUKI_CRATE_CACHE", cache))
    for cached in cache.glob("*/" + filename):
        if hashlib.sha256(cached.read_bytes()).hexdigest() == package["checksum"]:
            return cached.read_bytes()
    url = f"https://static.crates.io/crates/{package['name']}/{filename}"
    with urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != package["checksum"]:
        raise ValueError("registry checksum mismatch: " + filename)
    return data


def unpack_crate(data, directory, name):
    target = directory / name
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as crate:
        members = crate.getmembers()
        for member in members:
            path = directory / member.name
            if not path.resolve().is_relative_to(target) or not (member.isfile() or member.isdir()):
                raise ValueError("invalid crate member: " + member.name)
        crate.extractall(directory, filter="data")
    # Hash the archive's actual members. Filesystems may create AppleDouble
    # sidecars during extraction; those are not part of the locked crate.
    files = {str(Path(m.name).relative_to(name)).replace("\\", "/"):
             hashlib.sha256((directory / m.name).read_bytes()).hexdigest()
             for m in members if m.isfile()}
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
