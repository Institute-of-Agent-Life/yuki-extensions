"""Exercise explicit, offline selection of the public native distribution on Windows."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import ProxyHandler, build_opener

from package import build


def sha(path):
    with path.open("rb") as s:
        return hashlib.file_digest(s, "sha256").hexdigest()


def verify(root, output):
    if os.name != "nt":
        raise ValueError("this consumer proof requires the frozen Windows web-fetch")
    archive = Path(os.environ["YUKI_STABLE_BASE_ZIP"])
    plugin = Path(os.environ["YUKI_FROZEN_WEB_FETCH_ZIP"])
    pin = json.loads((root / "compat/stable-1.0/source.lock.json").read_bytes())
    platform = pin["platforms"]["windows-x86_64"]
    assert sha(archive) == platform["sha256"] and sha(plugin) == pin["windows_fallback"]["web-fetch"]["sha256"]
    pkg = output / "packages"
    manifest = build(root, "yuki-setup", pkg)
    setup = pkg / "yuki-setup.exe"
    work = output / "work"
    work.mkdir()
    actions = []
    def invoke(label, dest, bundle=archive, version="1.0.0", extra=(), ok=True):
        cmd = [setup,"native","--core",version,"--archive",bundle,"--dir",dest,*extra]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        actions.append({"case": label, "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
        assert (proc.returncode == 0) == ok, (label, proc.stderr)
        if ok:
            assert json.loads(proc.stdout)["binary"] == platform["binary_sha256"]
        elif label != "existing installation":
            assert not dest.exists()

    def start(dest, selected):
        host = dest / "bin/yuki-base.exe"
        owner = dest / "owner"
        assert sha(host) == platform["binary_sha256"]
        def cli(*args):
            return subprocess.run([host,"--data",owner,*args],capture_output=True,text=True,timeout=15)
        if not selected:
            assert not owner.exists()
            cli("init","--memory-mode","lexical-only").check_returncode()
        original = (owner / "yuki.toml").read_bytes()
        if selected:
            assert sha(dest / "plugins/web-fetch/yuki-web-fetch.exe") == pin["windows_fallback"]["web-fetch"]["members"]["yuki-web-fetch.exe"]
        log = output / (dest.name+"-host.log")
        with log.open("wb") as file:
            proc = subprocess.Popen([host,"--data",owner,"run"],stdout=file,stderr=file,cwd=work)
        try:
            end = time.monotonic()+20
            while time.monotonic()<end:
                records = [json.loads(line) for line in log.read_bytes().splitlines() if line.startswith(b'{"listen"') and line.endswith(b"}")]
                if records and proc.poll() is None:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("host did not become ready")
            with build_opener(ProxyHandler({})).open("http://"+records[-1]["listen"]+"/readyz",timeout=5) as resp:
                health = json.load(resp)
            assert health["ready"] is True
            while time.monotonic()<end:
                r = cli("operator","host","status")
                if not selected:
                    r.check_returncode()
                    status = json.loads(r.stdout)
                    assert status["plugins"] == [] and status["host_schema_revision"] == 2
                    break
                if r.returncode == 0:
                    status = json.loads(r.stdout)
                    if len(status["plugins"])==1 and status["plugins"][0]["online"]:
                        assert "official.web-fetch" in json.dumps(status["plugins"][0])
                        break
                time.sleep(.1)
            else:
                raise RuntimeError("installed original plugin did not negotiate")
            cli("operator","shutdown").check_returncode()
            assert proc.wait(timeout=10)==0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        assert (owner / "yuki.toml").read_bytes() == original
        return {"host_sha256":sha(host),"health":health,"status":status,"config_sha256":sha(owner/"yuki.toml")}

    plain = work/"plain"
    invoke("new offline base", plain)
    plain_status = start(plain,False)
    owner = plain/"owner"
    soul = owner/"SOUL.md"
    soul.write_bytes(b"# retained operator SOUL\n")
    before = {p.name:sha(p) for p in [owner/"yuki.toml",soul]}
    invoke("existing installation",plain,ok=False)
    assert all(sha(owner/n)==h for n,h in before.items())
    bad = work/"foreign"
    invoke("wrong version",bad,version="2.0.0",ok=False)
    invoke("wrong archive",bad,bundle=plugin,ok=False)
    invoke("unknown option",bad,extra=["--entry","external"],ok=False)
    invoke("missing optional package",bad,extra=["--plugin","web-fetch"],ok=False)
    invoke("changed optional package",bad,extra=["--plugin","web-fetch","--plugin-file",soul],ok=False)
    selected = work/"selected"
    invoke("explicit frozen web-fetch",selected,extra=["--plugin","web-fetch","--plugin-file",plugin])
    selected_status = start(selected,True)
    assert not list(work.glob(".yuki-base-*"))
    return "setup-install.json", {"status":"PASS","card_status":"PUBLIC_NATIVE_PROFILE_VERIFIED",
                "full_card_accepted":False,"offline":True,"core_source":pin["source_commit"],
                "host_zip_sha256":sha(archive),"plugin_zip_sha256":sha(plugin),
                "installer":manifest["artifacts"],"actions":actions,"without_plugins":plain_status,
                "explicit_original":selected_status,"preserved":before}
