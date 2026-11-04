"""Materialize the verified executable from an explicitly supplied host candidate."""
import hashlib
import json
import os
from pathlib import Path
import zipfile


def materialize(root, work):
    pin = json.loads((root / "compat/core-032/source.lock.json").read_bytes())
    archive = Path(os.environ["YUKI_HOST_CANDIDATE"])
    expected = pin["platforms"]["windows-x86_64" if os.name=="nt" else "darwin-arm64"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected["sha256"]:
        raise ValueError("host archive hash mismatch")
    with zipfile.ZipFile(archive) as bundle:
        meta = json.loads(bundle.read("candidate.json"))
        if meta["source_commit"] != pin["source_commit"] or meta["dirty"] or meta["host_schema_sha256"] != pin["schema_sha256"]:
            raise ValueError("incompatible host candidate")
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
