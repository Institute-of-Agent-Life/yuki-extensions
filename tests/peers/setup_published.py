"""Exercise explicit, offline selection of the public native distribution."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
from zipfile import ZipFile

from package import build


def sha(path):
    with path.open("rb") as s:
        return hashlib.file_digest(s, "sha256").hexdigest()


def verify(root, output, package_dir=None):
    archive = Path(os.environ["YUKI_STABLE_BASE_ZIP"])
    plugin_path = os.environ.get("YUKI_FROZEN_WEB_FETCH_ZIP")
    plugin = Path(plugin_path) if plugin_path else None
    pin = json.loads((root / "compat/stable-1.0/source.lock.json").read_bytes())
    machine = platform.machine().lower()
    arch = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    target = f"{platform.system().lower()}-{arch}"
    native = pin["platforms"][target]
    assert sha(archive) == native["sha256"]
    if plugin is not None:
        assert target == "windows-x86_64"
        assert sha(plugin) == pin["windows_fallback"]["web-fetch"]["sha256"]
    pkg = package_dir if package_dir is not None else output / "packages"
    manifest = (json.loads((pkg / "package-manifest.json").read_bytes())
                if package_dir is not None else build(root, "yuki-setup", pkg))
    setup = pkg / ("yuki-setup.exe" if os.name == "nt" else "yuki-setup")
    with tempfile.TemporaryDirectory(prefix="ext040-native-", dir="/tmp" if os.name != "nt" else None) as temp:
        return exercise(output, Path(temp), archive, plugin, pin, native, target, manifest, setup)


def verify_minors(root, output):
    archives = {
        version: Path(os.environ[f"YUKI_SETUP_BASE_{suffix}"]).resolve(strict=True)
        for version, suffix in (("1.1.0", "1_1"), ("1.2.0", "1_2"))
    }
    package = output / "packages"
    installer = build(root, "yuki-setup", package)
    setup = package / ("yuki-setup.exe" if os.name == "nt" else "yuki-setup")
    system = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}[platform.system()]
    binary = "yuki-core.exe" if system == "windows" else "yuki-core"
    results = {}
    with tempfile.TemporaryDirectory(prefix="setup-minor-", dir="/tmp" if os.name != "nt" else None) as temp:
        work = Path(temp)
        empty_path = work / "offline-path"
        empty_path.mkdir()
        env = {**os.environ, "PATH": str(empty_path)}

        def invoke(version, archive, destination, *extra, success=True):
            run = subprocess.run(
                [setup, "native", "--core", version, "--archive", archive, "--dir", destination, *extra],
                capture_output=True, text=True, timeout=60, env=env,
            )
            assert (run.returncode == 0) == success, run.stderr
            return json.loads(run.stdout) if success else run.stderr

        for version, archive in archives.items():
            lock = json.loads((root / "compat" / f"stable-{version[:3]}" / "source.lock.json").read_bytes())
            local_pin = json.loads((root / "tools/yuki-setup/inputs" / f"base-{version[:3]}.json").read_bytes())
            for field in ("source_commit", "published", "assets", "surface_sha256"):
                assert local_pin[field] == lock[field]
            assert all(lock["asset_sha256"][name] == digest for name, digest in local_pin["asset_sha256"].items())
            host_pin = lock["assets"][f"host-{system}"]
            assert sha(archive) == lock["asset_sha256"][archive.name]
            installed = work / version
            receipt = invoke(version, archive, installed)
            assert receipt["version"] == version and receipt["source"] == lock["source_commit"]
            assert receipt["binary"] == host_pin["sha256"] and receipt["plugins"] == []
            host = installed / "bin" / binary
            assert sha(host) == host_pin["sha256"]
            surface = json.loads(subprocess.check_output([host, "plugin-surface"], timeout=20, env=env))
            assert surface["version"] == version and surface["candidate_source"] == lock["source_commit"]
            assert surface["surface_sha256"] == lock["surface_sha256"]
            for language in ("rust", "python"):
                sdk = lock["assets"][f"{language}-sdk"]
                assert sha(installed / "sdk" / Path(sdk["path"]).name) == sdk["sha256"]
            owner = installed / "owner"
            def cli(*args):
                return subprocess.check_output([host, "--data", owner, *args], timeout=20, env=env)
            cli("init", "--memory-mode", "lexical-only")
            (owner / "SOUL.md").write_text("Preserved operator profile.\n", encoding="utf-8")
            before = {name: sha(owner / name) for name in ("yuki.toml", "SOUL.md")}
            invoke(version, archive, installed, success=False)
            assert all(sha(owner / name) == expected for name, expected in before.items())
            log = output / f"native-{version}.log"
            with log.open("wb") as stream:
                process = subprocess.Popen([host, "--data", owner, "run"], stdout=stream, stderr=stream, env=env)
            try:
                until = time.monotonic() + 20
                while time.monotonic() < until:
                    assert process.poll() is None, log.read_text(encoding="utf-8")
                    lines = log.read_bytes().splitlines()
                    if lines and lines[0].endswith(b"}"):
                        address = json.loads(lines[0])["listen"]
                        break
                    time.sleep(.05)
                else:
                    raise RuntimeError("installed Host did not become ready")
                with build_opener(ProxyHandler({})).open(f"http://{address}/readyz", timeout=5) as response:
                    ready = json.load(response)
                assert ready == {"ready": True}
                info = json.loads(cli("operator", "database-info"))
                assert info["schema_version"] == {"1.1.0": 56, "1.2.0": 60}[version]
                cli("operator", "shutdown")
                assert process.wait(timeout=10) == 0
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
            assert all(sha(owner / name) == expected for name, expected in before.items())
            results[version] = {"installed": receipt, "archive_sha256": sha(archive), "ready": ready,
                                "reader": info["schema_version"], "existing_owner_preserved": True}

        source = archives["1.2.0"]
        absent = work / "must-stay-absent"
        invoke("1.1.0", source, absent, success=False)
        invoke("1.2.0", source, absent, "--plugin", "web-fetch", success=False)
        invalid = work / "invalid"
        invalid.mkdir()
        for name in ("SHA256SUMS", "signer.pub", "manifest.json"):
            (invalid / name).write_bytes((source.parent / name).read_bytes())
        (invalid / "SHA256SUMS.sig").write_text("invalid signature", encoding="utf-8")
        assert "SHA-256 differs" in invoke("1.2.0", invalid / source.name, absent, success=False)
        (invalid / "SHA256SUMS.sig").write_bytes((source.parent / "SHA256SUMS.sig").read_bytes())
        (invalid / source.name).write_bytes(b"invalid archive")
        assert "SHA-256 differs" in invoke("1.2.0", invalid / source.name, absent, success=False)
        assert not absent.exists() and not list(work.glob(".yuki-native-*"))
    return "setup-install.json", {
        "status": "PASS", "card_status": "PUBLISHED_NATIVE_MINOR_INSTALLS_VERIFIED",
        "full_card_accepted": False, "offline": True, "platform": platform.platform(),
        "installer": installer["artifacts"], "versions": results,
        "rejected": ["mismatched version", "unqualified optional package", "changed signature", "changed archive"],
        "paid_calls": 0,
    }


def exercise(output, work, archive, plugin, pin, native, target, manifest, setup):
    actions = []
    empty_path = work / "offline-path"
    empty_path.mkdir()
    installer_env = dict(os.environ, PATH=str(empty_path))

    def invoke(label, dest, bundle=archive, version="1.0.0", extra=(), ok=True):
        cmd = [setup,"native","--core",version,"--archive",bundle,"--dir",dest,*extra]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, env=installer_env)
        actions.append({"case": label, "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
        assert (proc.returncode == 0) == ok, (label, proc.stderr)
        if ok:
            assert json.loads(proc.stdout)["binary"] == native["binary_sha256"]
        elif label != "existing installation":
            assert not dest.exists()

    def start(dest, selected):
        host = dest / native["binary"]
        owner = dest / "owner"
        assert sha(host) == native["binary_sha256"]
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
                if proc.poll() is not None:
                    raise RuntimeError(f"native host exited with {proc.returncode}; see {log.name}")
                records = [json.loads(line) for line in log.read_bytes().splitlines() if line.startswith(b'{"listen"') and line.endswith(b"}")]
                if records:
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
    invoke("wrong archive",bad,bundle=soul,ok=False)
    invoke("unknown option",bad,extra=["--entry","external"],ok=False)
    invoke("missing optional package",bad,extra=["--plugin","web-fetch"],ok=False)
    invoke("changed optional package",bad,extra=["--plugin","web-fetch","--plugin-file",soul],ok=False)
    if plugin is not None:
        selected = work/"selected"
        invoke("explicit frozen web-fetch",selected,extra=["--plugin","web-fetch","--plugin-file",plugin])
        selected_status = start(selected,True)
    else:
        selected_status = {
            "status": "not_run",
            "reason": ("YUKI_FROZEN_WEB_FETCH_ZIP was not supplied" if os.name == "nt"
                       else "The pinned web-fetch package targets Windows x86_64"),
        }
    assert not list(work.glob(".yuki-base-*"))
    assert not list(work.glob(".yuki-native-*"))
    return "setup-install.json", {"status":"PASS","card_status":"PUBLIC_NATIVE_PROFILE_VERIFIED",
                "full_card_accepted":False,"offline":True,"installer_path_empty":True,"core_source":pin["source_commit"],
                "target":target,"host_zip_sha256":sha(archive),"plugin_zip_sha256":sha(plugin) if plugin is not None else None,
                "installer":manifest["artifacts"],"actions":actions,"without_plugins":plain_status,
                "explicit_original":selected_status,"preserved":before}
