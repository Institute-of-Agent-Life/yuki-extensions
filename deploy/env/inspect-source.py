"""Verify and unpack the independent legacy backend source bundle."""
import hashlib
import json
from pathlib import Path
import zipfile


def extract(archive, lock_file, directory):
    lock=json.loads(lock_file.read_bytes())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=lock["archive_sha256"]:
        raise ValueError("manager source archive digest mismatch")
    with zipfile.ZipFile(archive) as bundle:
        expected=lock["source_members"]
        if sorted(bundle.namelist())!=sorted(expected):
            raise ValueError("manager archive member set mismatch")
        for name,entry in expected.items():
            target=(directory / name).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError("manager source path outside destination")
            data=bundle.read(name)
            blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            if len(data)!=entry["bytes"] or hashlib.sha256(data).hexdigest()!=entry["sha256"] or blob!=entry["git_blob"]:
                raise ValueError("manager source member mismatch: "+name)
            target.parent.mkdir(parents=True,exist_ok=True)
            with target.open("xb") as out:
                out.write(data)
    return lock
