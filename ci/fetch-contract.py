"""Verify and materialize the fixed CORE-031 handshake distribution."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from urllib.request import urlopen
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def materialize(root, output, archive=None):
    lock = json.loads((root / "contracts.lock").read_bytes())
    directory = root / "compat/core-031"
    name = "yuki-handshake-preview.zip"
    archive = archive or directory / name
    inputs = {}
    for filename, expected in lock["files"].items():
        path = archive if filename == name else directory / filename
        inputs[filename] = path.read_bytes()
        if digest(inputs[filename]) != expected:
            raise ValueError("contract digest mismatch: " + filename)
    manifest = json.loads(inputs["manifest.json"])
    receipt = json.loads(inputs["sdk-crosswire.json"])
    commit = lock["source_commit"]
    if (manifest["card"], manifest["status"], manifest["exit_code"], manifest["source"]["commit"],
            manifest["source"]["dirty"]) != ("CORE-031", "verified", 0, commit, False):
        raise ValueError("unverified producer run")
    if (manifest["artifacts"]["handshake-preview/" + name] != lock["files"][name]
            or manifest["artifacts"]["sdk-crosswire.json"] != lock["files"]["sdk-crosswire.json"]
            or receipt["archive_sha256"] != lock["files"][name] or receipt["source_commit"] != commit
            or receipt["sdk_versions"] != lock["versions"] or receipt["status"] != "handshake-preview"):
        raise ValueError("producer receipt does not bind this archive")
    with zipfile.ZipFile(io.BytesIO(inputs[name])) as bundle:
        meta = json.loads(bundle.read("candidate.json"))
        if (meta["source_commit"], meta["source_dirty"], meta["status"], meta["verification"],
                meta["sdk_versions"], meta["capabilities"]) != (
                commit, False, "unpublished", "verified", lock["versions"], ["initialize"]):
            raise ValueError("unexpected handshake candidate")
        if receipt["members"] != meta["members"] or meta["status"] != lock["candidate_build_status"]:
            raise ValueError("candidate and producer receipt disagree")
        expected = {m["name"] for m in meta["members"].values()} | {"candidate.json"}
        if sorted(bundle.namelist()) != sorted(expected):
            raise ValueError("unexpected archive inventory")
        members = {}
        for role, member in meta["members"].items():
            filename = member["name"]
            if Path(filename).name != filename or "/" in filename or "\\" in filename:
                raise ValueError("invalid member path")
            data = bundle.read(filename)
            if len(data) != member["bytes"] or digest(data) != member["sha256"]:
                raise ValueError("member digest mismatch: " + filename)
            members[role] = data
    index = json.loads(members["method-index"])
    if (list(index["methods"]) != lock["capabilities"] or index["sdk_versions"] != lock["versions"]
            or index["schema_sha256"] != digest(members["schema"])
            or meta["schema_sha256"] != index["schema_sha256"]):
        raise ValueError("method index disagrees with schema or versions")
    verification = json.loads(members["verification"])
    if verification["status"] != "verified" or not verification["portable_peer_verified"]:
        raise ValueError("producer did not verify the portable peer")
    for role in ("python-sdk", "peer"):
        with zipfile.ZipFile(io.BytesIO(members[role])) as distribution:
            if distribution.read("yuki_plugin_sdk/handshake.schema.json") != members["schema"]:
                raise ValueError("different embedded schema in " + role)
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for role, data in members.items():
        files[role] = output / meta["members"][role]["name"]
        files[role].write_bytes(data)
    return meta, files


def obtain_release(root, directory):
    lock = json.loads((root / "contracts.lock").read_bytes())
    release = lock["release"]
    directory.mkdir()
    for name, asset in release["assets"].items():
        if name not in {"yuki-handshake-preview.zip", "SHA256SUMS", "release-receipt.json"}:
            raise ValueError("unexpected release asset")
        if staged := os.environ.get("YUKI_CORE031_RELEASE_DIR"):
            data = (Path(staged) / name).read_bytes()
        else:
            with urlopen(asset["url"], timeout=60) as response:
                data = response.read()
        if digest(data) != asset["sha256"]:
            raise ValueError("release asset digest mismatch: " + name)
        (directory / name).write_bytes(data)
    receipt = json.loads((directory / "release-receipt.json").read_bytes())
    name = "yuki-handshake-preview.zip"
    expected = {f"{release['assets'][key]['sha256']}  {key}" for key in (name, "release-receipt.json")}
    if set((directory / "SHA256SUMS").read_text(encoding="ascii").splitlines()) != expected:
        raise ValueError("release checksum list mismatch")
    if (receipt["kind"], receipt["source_commit"], receipt["tag"], receipt["release_url"],
            receipt["bundle_sha256"], receipt["bundle_url"]) != (
            release["kind"], lock["source_commit"], release["tag"], release["url"],
            lock["files"][name], release["assets"][name]["url"]):
        raise ValueError("release receipt does not bind the source commit and asset")
    return directory / name, receipt


def published_contract(root, output, download):
    archive, receipt = obtain_release(root, download)
    meta, files = materialize(root, output, archive)
    for key in ("sdk_versions", "schema_revision", "schema_sha256", "capabilities", "members"):
        if receipt[key] != meta[key]:
            raise ValueError("release receipt differs from the delivered bundle: " + key)
    return meta, files, receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.bundle:
        candidate, _ = materialize(root, args.out, args.bundle)
    else:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            candidate, _, _ = published_contract(root, args.out, Path(tmp) / "release")
    print(json.dumps({key: candidate[key] for key in ("source_commit", "status", "sdk_versions")}))
