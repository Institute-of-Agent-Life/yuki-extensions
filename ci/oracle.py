"""Verify and consume the immutable CORE-002 handoff."""
import hashlib
import json
from pathlib import Path
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_oracle(root: Path):
    directory = root / "compat/core-002"
    pin = json.loads((directory / "source.lock.json").read_bytes())
    for name, expected in pin["files"].items():
        if digest((directory / name).read_bytes()) != expected:
            raise ValueError(f"CORE-002 digest mismatch: {name}")
    manifest = json.loads((directory / "manifest.json").read_bytes())
    index = json.loads((directory / "v4-oracle-index.json").read_bytes())
    producer = pin["producer_commit"]
    if (manifest["card"], manifest["status"], manifest["exit_code"], manifest["source"]["commit"],
            manifest["source"]["dirty"]) != ("CORE-002", "verified", 0, producer, False):
        raise ValueError("unverified producer run")
    archive = "v4-oracle-candidate.zip"
    for name in (archive, "v4-oracle-index.json"):
        if manifest["artifacts"][name] != pin["files"][name]:
            raise ValueError(f"producer manifest disagrees on {name}")
    if index["candidate"] != {"filename": archive, "sha256": pin["files"][archive], "source_commit": producer,
                              "source_dirty": False, "status": "unpublished"}:
        raise ValueError("index points to a different producer")
    with zipfile.ZipFile(directory / archive) as bundle:
        meta = json.loads(bundle.read("candidate.json"))
        if (meta["source_commit"], meta["source_dirty"], meta["baseline_commit"], meta["status"],
                meta["connector_distribution"], meta["connector_wire"], meta["client_revision"]) != (
                producer, False, pin["behavior_commit"], "unpublished", "0.4.3", 4, 9):
            raise ValueError("unexpected candidate identity or versions")
        if set(bundle.namelist()) != set(meta["files"]) | {"candidate.json"} or len(bundle.namelist()) != len(set(bundle.namelist())):
            raise ValueError("bundle member inventory mismatch")
        for name, expected in meta["files"].items():
            if digest(bundle.read(name)) != expected:
                raise ValueError(f"corrupt bundle member: {name}")
        if index["source_commit"] != meta["baseline_commit"] or index["connector_wire"] != 4:
            raise ValueError("index disagrees with bundle baseline")
        for name, expected in index["goldens"].items():
            if meta["files"].get(name) != expected:
                raise ValueError(f"golden not bound to index: {name}")
        if not {"legacy-wire4-reconnect", "legacy-client-admin-openapi"} <= set(meta["capabilities"]):
            raise ValueError("required capability absent from bundle")
        goldens = {Path(n).name: json.loads(bundle.read(n)) for n in index["goldens"]}
    return pin, index, goldens
