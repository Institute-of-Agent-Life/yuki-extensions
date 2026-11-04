from pathlib import Path
import hashlib
import json
import platform
import sys
import tempfile
import subprocess
import tomllib

archive, destination, lock, verifier, verifier_hash, optional_lock, optional_file = sys.argv[1:]
pin = json.loads(lock)
target = (platform.system().lower(), {"amd64":"x86_64","aarch64":"arm64"}.get(platform.machine().lower(),platform.machine().lower()))
entry = pin["native"].get("/".join(target))
if not entry:
    raise ValueError("no pinned host for this native target")
dst = Path(destination).absolute()
if dst.exists() or dst.is_symlink():
    raise ValueError("native destination must be new")
with tempfile.TemporaryDirectory(prefix=".yuki-native-",dir=dst.parent) as tmp:
    root=Path(tmp)
    raw=verifier.encode()
    if hashlib.sha256(raw).hexdigest()!=verifier_hash:
        raise ValueError("packaged verifier mismatch")
    (root/"verify_dist.py").write_bytes(raw)
    sys.path.insert(0,str(root))
    import verify_dist
    use_pinned_verifier(verify_dist)
    from verify_dist import verify
    key=entry["signer"].encode()
    if hashlib.sha256(key).hexdigest()!=entry["signer_sha256"]:
        raise ValueError("setup signer differs")
    (root/"signer.pub").write_bytes(key)
    stage=root/"verified"
    meta=verify(archive,root/"signer.pub",pin["source_commit"],entry["archive_sha256"],
                pin["fixtures_sha256"],target=target,destination=stage)
    if meta["dirty"] or meta["status"]!="unpublished-development-candidate":
        raise ValueError("unexpected native candidate")
    if optional_file:
        plug=json.loads(optional_lock)
        if "/".join(target)!=plug["target"] or meta["host_schema_sha256"]!=plug["required_host_schema_sha256"]:
            raise ValueError("no verified optional plugin for the selected host")
        plugin=Path(optional_file).read_bytes()
        if hashlib.sha256(plugin).hexdigest()!=plug["binary_sha256"]:
            raise ValueError("optional plugin digest mismatch")
        manifest=tomllib.loads(plug["manifest"])
        rel=Path("plugins/web-fetch/yuki-web-fetch.exe")
        program=stage/rel
        program.parent.mkdir(parents=True)
        program.write_bytes(plugin)
        owner=stage/"owner"
        subprocess.run([stage/"bin/yuki-core.exe","--data",owner,"init"],check=True,capture_output=True,timeout=20)
        with (owner/"yuki.toml").open("a",encoding="utf-8",newline="\n") as config:
            print("\n[[plugins]]",file=config)
            for key,value in {"id":manifest["id"],"namespace":"official.web-fetch","program":str(dst/rel),
                              "grants":manifest["grants"],"env":manifest["env"]}.items():
                print(key,"=",json.dumps(value),file=config)
            # Preserve the release unit's original schema, flags and tool description.
            tools=plug["manifest"].split("[[tools]]",1)[1]
            print("[[plugins.tools]]"+tools,file=config)
    stage.rename(dst)
print("verified native candidate", pin["source_commit"], "/".join(target), entry["archive_sha256"])
