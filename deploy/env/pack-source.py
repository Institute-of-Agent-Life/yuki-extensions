"""Export the pinned legacy Manager and environment image sources. No deployment."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

BASELINE = "329ca7c487414d2f54ddd98ff4727446ed2446cd"
MODULES = """domain.conversations domain.messages emoji.media emoji.sticker_index
gateway.media sandbox.completions sandbox.computer_control sandbox.computer_keys
sandbox.computer_runtime sandbox.computer_transport sandbox.environment_supervisor
sandbox.environment_tools sandbox.execd sandbox.legacy_acp sandbox.legacy_acp_protocol
sandbox.manager sandbox.persistent sandbox.protocol services.media_resolver vision.models
workspace.artifact_lock workspace.files workspace.store""".split()
INPUTS = [
    "LICENSE", "deploy/sandbox/Dockerfile.environment", "deploy/sandbox/requirements-manager.txt",
    "deploy/sandbox/environment-storage.sh", "deploy/sandbox/network-guard.sh",
    "deploy/sandbox/yuki-environment-storage.service", "deploy/sandbox/yuki-sandbox.service",
]


def export(checkout):
    def git(*args):
        return subprocess.check_output(["git","-C",str(checkout),*args],stderr=subprocess.PIPE)
    assert git("rev-parse",BASELINE+"^{commit}").decode().strip()==BASELINE
    tree=set(git("ls-tree","-r","--name-only",BASELINE).decode().splitlines())
    names=set(INPUTS)
    for module in MODULES:
        path=Path("src/yuki",*module.split(".")).with_suffix(".py")
        names.add(path.as_posix())
        names.update((parent/"__init__.py").as_posix() for parent in path.parents
                     if (parent/"__init__.py").as_posix() in tree)
    out=io.BytesIO()
    entries={}
    with zipfile.ZipFile(out,"w") as archive:
        for name in sorted(names):
            value=git("show",BASELINE+":"+name)
            entries[name]={"sha256":hashlib.sha256(value).hexdigest(),"bytes":len(value),
                           "git_blob":git("rev-parse",BASELINE+":"+name).decode().strip()}
            header=zipfile.ZipInfo(name,(2026,1,1,0,0,0))
            header.create_system=3
            header.external_attr=0o100644<<16
            # Stored bytes yield identical archives across zlib versions.
            archive.writestr(header,value)
    data=out.getvalue()
    lock={"repository":"https://github.com/YuanYeYouTao/Yuki","source_commit":BASELINE,
          "source_archive":"manager-source.zip","archive_sha256":hashlib.sha256(data).hexdigest(),
          "source_members":entries,"manager_python":"3.12","manager_websockets":"15.0.1",
          "execd_source":"https://github.com/opensandbox-group/OpenSandbox",
          "execd_commit":"441042c288a3eacbe93b36236a9baf6f6254ad4d",
          "runtime":"runsc","historical_runtime_release":"release-20260831.0",
          "historical_runtime_reference":"docs/operations/social-sandbox-validation.md",
          "runtime_image_digest":None,"runtime_binary_digest":None}
    return data,(json.dumps(lock,indent=2)+"\n").encode()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("historical_checkout",type=Path)
    parser.add_argument("output",type=Path,help="new directory for the archive and lock")
    args=parser.parse_args()
    data,lock=export(args.historical_checkout)
    args.output.mkdir(exist_ok=False,parents=True)
    (args.output/"manager-source.zip").write_bytes(data)
    (args.output/"source.lock.json").write_bytes(lock)
