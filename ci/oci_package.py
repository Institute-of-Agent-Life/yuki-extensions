"""Build the portable, checksum-locked source distribution of one OCI release unit."""
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

from units import inside


def build_source(root, unit, output):
    path = inside(root, unit["path"])
    archive = output / (unit["unit_id"] + "-" + unit["version"] + "-source.tar.gz")
    members = {}
    with archive.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w|", format=tarfile.PAX_FORMAT) as bundle:
            for file in sorted(path.rglob("*")):
                rel = file.relative_to(path)
                if any(p in {"inputs", "__pycache__", "target", ".git"} or p.startswith("._") for p in rel.parts):
                    continue
                if not file.is_file():
                    continue
                inside(path, rel.as_posix())
                data = file.read_bytes()
                members[rel.as_posix()] = hashlib.sha256(data).hexdigest()
                info = tarfile.TarInfo(rel.as_posix()); info.size = len(data); info.mode = 0o644
                import io
                bundle.addfile(info, io.BytesIO(data))
    report = {
        "unit_id": unit["unit_id"], "version": unit["version"], "release_tag": unit["tag_prefix"] + unit["version"],
        "published": False, "scope": "portable OCI build source; no native execution in this package job",
        "runtime_platform": "linux/amd64", "source": unit["source"], "license": unit["license"],
        "manifest_sha256": hashlib.sha256((path / "runtime.toml").read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256((path / "runtime.lock").read_bytes()).hexdigest(),
        "members": members, "artifacts": {archive.name: hashlib.sha256(archive.read_bytes()).hexdigest()},
    }
    (output / "package-manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report
