"""Materialize the verified executable from an explicitly supplied host candidate."""
import hashlib
import json
import os
import platform
from pathlib import Path
import zipfile


def materialize(root, work, contract="core-032"):
    pin = json.loads((root / "compat" / contract / "source.lock.json").read_bytes())
    archive = Path(os.environ["YUKI_HOST_CANDIDATE"])
    # Verify the package target before executing a producer binary.
    system = platform.system().lower()
    arch = {"aarch64":"arm64", "amd64":"x86_64"}.get(platform.machine().lower(), platform.machine().lower())
    expected = pin["platforms"][f"{system}-{arch}"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("host archive hash mismatch")
    with zipfile.ZipFile(archive) as bundle:
        meta = json.loads(bundle.read("candidate.json"))
        if meta["source_commit"] != pin["source_commit"] or meta["dirty"] or meta["host_schema_sha256"] != pin["schema_sha256"]:
            raise ValueError("incompatible host candidate")
        if "personal_schema_sha256" in pin and meta.get("personal_schema_sha256") != pin["personal_schema_sha256"]:
            raise ValueError("personal schema digest mismatch")
        if "media_schema_sha256" in pin and meta.get("media_schema_sha256") != pin["media_schema_sha256"]:
            raise ValueError("media schema digest mismatch")
        if "aux_schema_sha256" in pin and meta.get("aux_schema_sha256") != pin["aux_schema_sha256"]:
            raise ValueError("aux schema digest mismatch")
        if sorted(bundle.namelist()) != sorted([*meta["members"], "candidate.json"]):
            raise ValueError("unexpected host package member set")
        for name, member in meta["members"].items():
            data = bundle.read(name)
            if hashlib.sha256(data).hexdigest() != member["sha256"] or len(data)!=member["bytes"]:
                raise ValueError("host member mismatch: "+name)
        host = work / ("yuki-core.exe" if os.name=="nt" else "yuki-core")
        data=bundle.read("bin/"+host.name)
        if hashlib.sha256(data).hexdigest()!=expected["binary_sha256"]:
            raise ValueError("unexpected platform host")
        host.write_bytes(data)
        host.chmod(0o700)
    return host, pin, expected
