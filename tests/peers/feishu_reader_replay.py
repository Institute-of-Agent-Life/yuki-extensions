"""Replay the stopped Feishu installation with two exact historical Windows packages."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tomllib
import zipfile

from joint_base import exchange


PACKAGES = {
    "0.1.0-alpha.1": "724da1a529274a87d4a94b63756ac8d942a4002cc7b1cfa2e3a161435359b4ad",
    "0.1.0-alpha.2": "e3ef5dbad9f5b628d5b354343c46d7dd58db2b7b86c045259447b893ffb0d3fc",
}


def packages(paths, work):
    work.mkdir()
    result = {}
    for (version, sha), path in zip(PACKAGES.items(), paths, strict=True):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("package-manifest.json"))
            assert archive.testzip() is None
            assert manifest["unit_id"] == "feishu" and manifest["version"] == version
            assert sorted(archive.namelist()) == sorted([*manifest["artifacts"], "package-manifest.json"])
            for name, expected in manifest["artifacts"].items():
                assert hashlib.sha256(archive.read(name)).hexdigest() == expected
            locked = tomllib.loads(archive.read("Cargo.lock").decode())
            sdk, = [p for p in locked["package"] if p["name"] == "yuki-plugin-sdk"]
            exe = archive.read("yuki-feishu.exe")
            dest = work / (version + ".exe")
            dest.write_bytes(exe)
            result[version] = dict(binary=dest.name, binary_sha256=hashlib.sha256(exe).hexdigest(),
                                   sdk_version=sdk["version"], sdk_sha256=sdk["checksum"], archive_sha256=sha)
    return result


def send_phase(phase, conn, frame, ack, first):
    second = json.loads(first)
    second["event"]["message"]["message_id"] = "om_second"
    raw = json.dumps(second).encode()
    mid = len(raw) // 2
    head, tail = frame("event",raw[:mid],0,2,serial=22), frame("event",raw[mid:],1,2,serial=22)
    if phase == "old":
        conn.send(frame("event",first,serial=11))
        ack(11,200)
        conn.send(head)
        conn.send(frame("card",b"{}",serial=33))
        ack(33,200)
    elif phase == "new":
        conn.send(tail)
        conn.send(frame("card",b"{}",serial=34))
        ack(34,200)
        conn.send(head)
        ack(22,200)
        conn.send(frame("event",first,serial=11))
        ack(11,200)
    elif phase == "rollback":
        conn.send(frame("event",raw,serial=22))
        ack(22,200)
    else:
        raise ValueError(phase)


def event_ids(wire, phase):
    calls = list(exchange(wire, "gateway.inbound", "from_plugin"))
    expected = {"old":["om_shared"],"new":["om_second","om_shared"],"rollback":["om_second"]}[phase]
    assert [call["params"]["source"] for call, _ in calls] == expected
    ids = [reply["result"]["event"] for _, reply in calls]
    assert all(isinstance(i,int) and i > 0 for i in ids)
    return ids


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/"ci"))
    old, new, output = [Path(arg).resolve() for arg in sys.argv[1:]]
    output.mkdir()
    prepare = runpy.run_path(root/"tests/cases/EXT-005.py")["prepare"]
    _, result = prepare(root, output, contract="core-038-main", reader_archives=(old,new))
    (output/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
