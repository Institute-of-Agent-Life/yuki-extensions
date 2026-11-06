"""Run the installer against independently pinned, signed, clean producer packages."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import build_opener, ProxyHandler

from package import build


def prepare(root, output):
    work=output/"work";work.mkdir()
    pkg=output/"packages"
    release=build(root,"yuki-setup",pkg)
    exe=pkg/("yuki-setup.exe" if os.name=="nt" else "yuki-setup")
    oci=Path(os.environ["YUKI_CORE039_OCI"]);native=Path(os.environ["YUKI_CORE039_NATIVE"])
    pins=root/"tools/yuki-setup/inputs"
    pin=json.loads((pins/"source.lock.json").read_bytes())
    native_pin=json.loads((pins/"native.lock.json").read_bytes())
    optional=json.loads((pins/"web-fetch.lock.json").read_bytes())
    actions=[]
    secret="fixture-secret-reference-preserve"
    def setup(command, location, archive, *options, success=True):
        r=subprocess.run([exe,command,"--archive",archive,"--dir",location,*options],capture_output=True,text=True,timeout=120)
        actions.append({"command":command,"options":[str(v) for v in options],"success":r.returncode==0,"stdout":r.stdout,"stderr":r.stderr})
        if secret in r.stdout+r.stderr:raise AssertionError("installer printed private fixture value")
        if (r.returncode==0)!=success:raise RuntimeError(f"unexpected {command} exit {r.returncode}: {r.stderr}")
    kit=work/"direct"
    setup("init",kit,oci,"--profile","direct","--entry","local","--core",pin["core_version"])
    original=(kit/"compose.yaml").read_text()
    assert original==(root/"deploy/compose/direct.yaml").read_text(encoding="utf-8")
    assert pin["image_digest"] in original and "pull_policy: never" in original
    assert all(word not in original.lower() for word in ("napcat","monty","qq","docker.sock","execd","depends_on"))
    (kit/"compose.yaml").write_text("# operator comment\n"+original,encoding="utf-8",newline="\n")
    comments=(kit/"compose.yaml").read_bytes()
    existing=f'# hand maintained\r\nNAPCAT_HOME=old-value\r\nOPENAI_KEY_REF={secret}\r\nYUKI_TIMEZONE=UTC   # keep me\r\n'
    (kit/".env").write_bytes(existing.encode())
    setup("init",kit,oci,"--timezone","Asia/Shanghai")
    assert (kit/".env").read_bytes()==existing.replace("=UTC","=Asia/Shanghai").encode()
    assert (kit/"compose.yaml").read_bytes()==comments
    setup("doctor",kit,oci,"--timezone","Asia/Shanghai")
    for name,options in [("missing-Monty",["--profile","code"]),("missing-gateway",["--plugin","snowluma"]),
                         ("nonlocal",["--entry","external"]),("wrong-core",["--core","other"])]:
        dest=work/name;setup("init",dest,oci,*options,success=False)
        assert not dest.exists()
    foreign=work/"foreign";foreign.mkdir()
    (foreign/"compose.yaml").write_text("services: {foreign: {image: operator}}",encoding="utf-8")
    setup("init",foreign,oci,success=False)
    assert "foreign:" in (foreign/"compose.yaml").read_text() and not (foreign/".env").exists()
    corrupt=work/"bad.oci";corrupt.write_bytes(b"wrong candidate")
    setup("doctor",kit,corrupt,success=False)
    installed=work/"native"
    setup("native",installed,native)
    setup("native",installed,native,success=False)
    host=installed/"bin"/("yuki-core.exe" if os.name=="nt" else "yuki-core")
    info=json.loads((installed/"candidate.json").read_bytes())
    target=info["os"]+"/"+info["arch"]
    assert hashlib.sha256(host.read_bytes()).hexdigest()==native_pin["native"][target]["binary_sha256"]
    owner=work/"isolated-owner"
    def cli(*args):
        return subprocess.run([host,"--data",owner,*args],capture_output=True,text=True,check=True,timeout=20)
    cli("init")
    soul=owner/"SOUL.md"
    soul.write_bytes(b"# Operator fixture\n")
    again=subprocess.run([host,"--data",owner,"init"],capture_output=True,text=True,timeout=20)
    assert again.returncode!=0 and "preserves existing yuki.toml" in again.stderr and soul.read_bytes()==b"# Operator fixture\n"
    with (output/"native-host.txt").open("wb") as log:
        proc=subprocess.Popen([host,"--data",owner,"run"],stdout=log,stderr=log,cwd=work)
    try:
        until=time.monotonic()+15;listen=None
        while time.monotonic()<until and not listen:
            for line in (output/"native-host.txt").read_bytes().splitlines():
                try:listen=json.loads(line).get("listen")
                except ValueError:pass
            time.sleep(.05)
        if not listen:raise RuntimeError("native candidate did not become ready")
        opener=build_opener(ProxyHandler({}))
        with opener.open(f"http://{listen}/readyz",timeout=5) as r:
            ready=json.loads(r.read())
        assert ready["ready"] is True
        empty=subprocess.run([host,"--data",owner,"operator","host","status"],capture_output=True,text=True,timeout=10)
        assert empty.returncode!=0 and "plugin host not configured" in empty.stderr
        status={"configured":False,"operator":json.loads(empty.stderr)}
        cli("operator","shutdown");proc.wait(timeout=10)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    # Add one explicitly supplied candidate. The same host must negotiate its real executable.
    other=work/"selected"
    setup("native",work/"wrong-plugin",native,"--plugin","web-fetch","--plugin-file",corrupt,success=False)
    assert not (work/"wrong-plugin").exists()
    plugin_path=Path(os.environ["YUKI_SETUP_WEB_FETCH"])
    setup("native",other,native,"--plugin","web-fetch","--plugin-file",plugin_path)
    owner=other/"owner";host=other/"bin/yuki-core.exe"
    with (output/"optional-host.txt").open("wb") as log:
        proc=subprocess.Popen([host,"--data",owner,"run"],cwd=work,stdout=log,stderr=log)
    try:
        end=time.monotonic()+20
        while time.monotonic()<end:
            r=subprocess.run([host,"--data",owner,"operator","host","status"],capture_output=True,text=True,timeout=10)
            if not r.returncode:
                active=json.loads(r.stdout)
                if any(p["online"] for p in active["plugins"]):break
            time.sleep(.1)
        else:raise RuntimeError("selected native web-fetch did not negotiate")
        assert len(active["plugins"])==1
        cli("operator","shutdown");proc.wait(timeout=10)
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    return "setup-install.json",{"status":"PASS","card_status":"OFFLINE_SETUP_ON_UNPUBLISHED_SIGNED_CANDIDATE",
        "source_commit":pin["source_commit"],"handoff_commit":native_pin["handoff_commit"],
        "installer_sha256":release["artifacts"][exe.name],"oci_sha256":pin["archive_sha256"],
        "image":pin["image_digest"],"native":native_pin["native"][target],"sdk_versions":info["sdk_versions"],
        "schema_sha256":info["host_schema_sha256"],"ready_without_optional_gateways":ready,
        "host_status":status,"existing_soul_preserved":True,"operator_comments_and_napcat_reference_preserved":True,
        "compose":original,"actions":actions,"selected_plugin":{"source_commit":optional["source_commit"],"binary_sha256":optional["binary_sha256"],"consumer_sdk_sha256":optional["consumer_sdk_sha256"],"host_sdk_sha256":info["members"]["sdk/yuki-plugin-sdk-1.0.0-alpha.2.crate"]["sha256"],"host_status":active},"pending":"Full external ingress/optional packages and launched Compose need their actual producer/runtime."}


def run(root, output):
    return "setup-install.json",{"status":"BLOCKED","card_status":"AWAITING_PRODUCER_AND_DEPLOYMENT_INPUTS",
        "reason":"The current signed CORE-039 development candidate is unmerged and unpublished."}
