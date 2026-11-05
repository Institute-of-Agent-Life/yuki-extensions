"""Send a content-addressed source snapshot to the authorized Windows test host."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import urllib.request
import zipfile


def invoke(argv, **kwargs):
    result = subprocess.run(argv, text=True, capture_output=True, **kwargs)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr, flush=True)
    return result


def powershell(host, code):
    prefix = "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; "
    prefix += "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); $env:PYTHONUTF8='1'; "
    encoded = base64.b64encode((prefix + code).encode("utf-16le")).decode()
    stdin = None
    if len(encoded) > 7200:
        # Windows OpenSSH starts its command through cmd.exe (8191-character limit).
        # Keep the signed-in host and original PowerShell error/exit behavior.
        stdin = base64.b64encode((prefix + code).encode("utf-8")).decode() + "\r\n"
        loader = "& ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([Console]::In.ReadLine()))))"
        encoded = base64.b64encode(loader.encode("utf-16le")).decode()
    return invoke(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                   "-o", "StrictHostKeyChecking=yes", host, "powershell", "-NoProfile",
                   "-NonInteractive", "-EncodedCommand", encoded], input=stdin)


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task")
    parser.add_argument("--run", default="01")
    parser.add_argument("--host", default="hjw")
    parser.add_argument("--remote-root", default="C:/Users/Hilbert/yuki-extension-tests",
                        help="isolated test directory on the Windows host")
    parser.add_argument("--connector-source", action="store_true", help="baseline source verification only, not EXT-007 acceptance")
    parser.add_argument("--connector-candidate", action="store_true", help="verify the independent EXT-007 candidate")
    parser.add_argument("--preparation", action="store_true", help="run the card preparation entry point")
    args = parser.parse_args()
    driver_case = args.task in {"EXT-008", "EXT-009", "EXT-010"}
    connector_mode = args.connector_source or args.connector_candidate or driver_case or args.task == "EXT-011"
    if args.connector_source and args.connector_candidate:
        parser.error("select one connector verification mode")
    if not re.fullmatch(r"EXT-\d{3}", args.task) or not re.fullmatch(r"[a-zA-Z0-9-]+", args.run):
        parser.error("invalid task/run")
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts" / args.task / args.run
    if output.exists():
        parser.error("output exists; use a new run ID")
    source = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            cwd=root, check=True, capture_output=True).stdout
    files = sorted(set(os.fsdecode(p) for p in source.split(b"\0") if p))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            parts = PurePosixPath(name).parts
            if parts[0] in {"artifacts", ".ci-transfer"} or any(p.startswith("._") for p in parts):
                continue
            path = root / name
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"source snapshot cannot follow external links: {name}")
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(buffer.getvalue()).hexdigest()
    transfer = root / ".ci-transfer"
    transfer.mkdir(exist_ok=True)
    snapshot = transfer / (digest + ".zip")
    snapshot.write_bytes(buffer.getvalue())
    # A separate per-task test directory, never the user's existing checkout/journal.
    remote = args.remote_root.rstrip("/\\") + "/" + digest[:20]
    tooling = "C:/Users/Hilbert/yuki-extension-tests/tooling-uv-0.12.0"
    locked = json.loads((root / "ci/tooling.lock.json").read_text(encoding="utf-8"))["packages"]
    wheelhouse = transfer / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    for package in locked.values():
        wheel = wheelhouse / package["filename"]
        if not wheel.exists() or hashlib.sha256(wheel.read_bytes()).hexdigest() != package["sha256"]:
            with urllib.request.urlopen(package["url"], timeout=90) as response:
                wheel.write_bytes(response.read())
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != package["sha256"]:
            raise ValueError("build-tool wheel digest mismatch: " + wheel.name)
    extra = []
    if args.task == "EXT-005":
        pins = json.loads((root / "tests/peers/lark-fixture.lock.json").read_bytes())
        for entry in pins["wheels"]:
            wheel = wheelhouse / entry["filename"]
            if not wheel.exists():
                with urllib.request.urlopen(entry["url"], timeout=90) as response:
                    wheel.write_bytes(response.read())
            if hashlib.sha256(wheel.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("platform fixture wheel digest mismatch: " + wheel.name)
            extra.append(wheel)
    if connector_mode:
        if not driver_case and args.task not in {"EXT-007", "EXT-011"}:
            parser.error("connector source mode belongs to EXT-007 preparation")
        manifest_path = transfer / "connector-wheels.json"
        helper = invoke(["uv", "run", "--no-project", "--offline", "--python", "3.12", "python",
                         str(root / "ci/download-wheelhouse.py"), str(root / "connector/uv.lock"),
                         "--out", str(wheelhouse), "--manifest", str(manifest_path)])
        if helper.returncode:
            return helper.returncode
        extra = [wheelhouse / f["filename"] for f in json.loads(manifest_path.read_text())["files"]]
        source_lock = json.loads((root / "connector/packaging/source.lock.json").read_text())
        baseline = source_lock["historical_ci"]
        oracle = root / "tests/fixtures/connector" / baseline["wheel_name"]
        if hashlib.sha256(oracle.read_bytes()).hexdigest() != baseline["wheel_sha256"]:
            raise ValueError("baseline wheel digest mismatch")
        extra.append(oracle)
    runtime_input = None
    if args.connector_candidate:
        import ast
        script = (root / "connector/scripts/build_runtime.py").read_text(encoding="utf-8")
        pins = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(script).body
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in {"TARGETS", "PYTHON_VERSION", "PYTHON_RELEASE"}}
        _, _, triple, expected = pins["TARGETS"]["win32", "AMD64"]
        filename = f"cpython-{pins['PYTHON_VERSION']}+{pins['PYTHON_RELEASE']}-{triple}-install_only_stripped.tar.gz"
        runtime_input = transfer / "python-runtime" / filename
        if not runtime_input.exists():
            runtime_input.parent.mkdir(exist_ok=True)
            subprocess.run(["gh", "release", "download", pins["PYTHON_RELEASE"], "--repo",
                            "astral-sh/python-build-standalone", "--pattern", filename,
                            "--dir", str(runtime_input.parent)], check=True)
        if hashlib.sha256(runtime_input.read_bytes()).hexdigest() != expected:
            raise ValueError("pinned Windows Python archive digest mismatch")
    desktop_tools = []
    if args.task == "EXT-019":
        from desktop_tooling import inputs
        desktop_tools = inputs(root, transfer / "desktop-tools", windows_node=True)
    release_assets = []
    if args.task == "EXT-002" and not args.preparation:
        contract = json.loads((root / "contracts.lock").read_bytes())
        release = contract["release"]
        destination = transfer / "core031-github-release" / release["tag"]
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gh", "release", "download", release["tag"], "--repo", contract["repository"],
                        "--dir", str(destination), "--clobber"], check=True)
        for filename, asset in release["assets"].items():
            path = destination / filename
            if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
                raise ValueError("release download digest mismatch: " + filename)
            release_assets.append(path)
    # Include only locked wheels, not arbitrary files already in the transport cache.
    tools_zip = transfer / "tooling.zip"
    host_candidate = None
    if args.task in {"EXT-003", "EXT-005", "EXT-011", "EXT-015", "EXT-020", "EXT-028", "EXT-031", "EXT-036", "EXT-037"}:
        host_candidate = Path(os.environ["YUKI_HOST_CANDIDATE"])
        contract = "core-037" if args.task == "EXT-037" else "core-035" if args.task == "EXT-036" else "core-038" if args.task == "EXT-031" else ("core-033" if args.task in {"EXT-011","EXT-015"} else "core-032")
        pin = json.loads((root / "compat" / contract / "source.lock.json").read_bytes())["platforms"]["windows-x86_64"]
        if hashlib.sha256(host_candidate.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("unexpected Windows host candidate")
    native_crates = []
    if args.task in {"EXT-005", "EXT-011", "EXT-015", "EXT-020", "EXT-028", "EXT-031", "EXT-036", "EXT-037"}:
        import tomllib
        from handshake_cargo import registry_crate
        cache = transfer / "native-crates"
        cache.mkdir(exist_ok=True)
        unit = {"EXT-005": "feishu", "EXT-011": "local-agent", "EXT-015": "client", "EXT-020": "env", "EXT-028": "web-fetch", "EXT-031": "media", "EXT-036": "memory-maintenance", "EXT-037": "trace"}[args.task]
        project = tomllib.loads((root / "plugins" / unit / "Cargo.lock").read_text())
        for package in project["package"]:
            if not package.get("source") or package["name"] == "yuki-plugin-sdk":
                continue
            path = cache / f"{package['name']}-{package['version']}.crate"
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != package["checksum"]:
                path.write_bytes(registry_crate(package))
            native_crates.append(path)
    codec_inputs = []
    if args.task == "EXT-031":
        codecs = json.loads((root / "plugins/media/packaging/codecs.lock").read_bytes())
        for codec in [*codecs["document_backend"]["packages"].values(), codecs["ffmpeg"]["platforms"]["windows-x86_64"]]:
            path = transfer / "media-codecs" / codec["filename"]
            path.parent.mkdir(exist_ok=True)
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != codec["sha256"]:
                with urllib.request.urlopen(codec["url"], timeout=90) as response:
                    path.write_bytes(response.read())
            if hashlib.sha256(path.read_bytes()).hexdigest() != codec["sha256"]:
                raise ValueError("codec wheel hash mismatch")
            codec_inputs.append(path)
    setup_inputs = []
    if args.task == "EXT-040":
        pins = root / "tools/yuki-setup/inputs"
        oci = json.loads((pins/"source.lock.json").read_bytes())
        native = json.loads((pins/"native.lock.json").read_bytes())["native"]["windows/x86_64"]
        for env, pin in [("YUKI_CORE039_OCI", oci), ("YUKI_CORE039_NATIVE", native)]:
            package = Path(os.environ[env])
            if hashlib.sha256(package.read_bytes()).hexdigest() != pin["archive_sha256"]:
                raise ValueError("unexpected setup input: " + env)
            setup_inputs.append((env, package))
        plugin = Path(os.environ["YUKI_SETUP_WEB_FETCH"])
        plug = json.loads((pins / "web-fetch.lock.json").read_bytes())
        if hashlib.sha256(plugin.read_bytes()).hexdigest() != plug["binary_sha256"]:
            raise ValueError("unexpected optional web-fetch binary")
        setup_inputs.append(("YUKI_SETUP_WEB_FETCH", plugin))
    with zipfile.ZipFile(tools_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for package in codec_inputs:
            archive.write(package, "media-codecs/" + package.name)
        for _, package in setup_inputs:
            archive.write(package, "setup-inputs/" + package.name)
        for crate in native_crates:
            archive.write(crate, "native-crates/locked/" + crate.name)
        if host_candidate:
            archive.write(host_candidate, "extension-host-candidate.zip")
        for package in locked.values():
            archive.write(wheelhouse / package["filename"], package["filename"])
        for path in release_assets:
            archive.write(path, "core031-release/" + path.name)
        for path in desktop_tools:
            archive.write(path, "desktop-tools/" + path.name)
        if runtime_input:
            archive.write(runtime_input, "runtime-cache/" + runtime_input.name)
        existing = {p["filename"] for p in locked.values()}
        for path in extra:
            if path.name not in existing:
                archive.write(path, path.name)
                existing.add(path.name)
    assert powershell(args.host, f"New-Item -ItemType Directory -Force {quote(remote)} | Out-Null").returncode == 0
    assert invoke(["scp", "-q", str(snapshot), f"{args.host}:{remote}/source.zip"]).returncode == 0
    assert invoke(["scp", "-q", str(tools_zip), f"{args.host}:{remote}/tooling.zip"]).returncode == 0
    sdk_environment = ""
    if args.task in {"EXT-001", "EXT-002", "EXT-003", "EXT-005", "EXT-011", "EXT-015", "EXT-020", "EXT-028", "EXT-031", "EXT-036", "EXT-037", "EXT-040"}:
        # Use the host's existing pinned toolchain, with a separate writable Cargo home.
        sdk_environment = r"""
$tools=Join-Path $env:USERPROFILE 'yuki-core-tooling'
$env:RUSTUP_HOME=Join-Path $tools 'rustup'
$env:YUKI_CRATE_CACHE=Join-Path $tools 'cargo/registry/cache'
$env:PATH="$(Join-Path $tools 'cargo/bin');$(Join-Path $tools 'winlibs/mingw64/bin');$env:PATH"
$env:CARGO_HOME=Join-Path $env:TEMP 'cargo-home'
"""
    if args.task == "EXT-001":
        fixture_home = quote(args.remote_root.rstrip("/\\") + "/rust-fixture-1.90/rustup")
        sdk_environment += f"""
if (Test-Path (Join-Path {fixture_home} 'toolchains/1.90.0-x86_64-pc-windows-gnu/bin/rustc.exe')) {{
    $env:RUSTUP_HOME={fixture_home}
    $env:RUSTUP_TOOLCHAIN='1.90.0-x86_64-pc-windows-gnu'
}}
"""
    for key, package in setup_inputs:
        sdk_environment += "$env:" + key + "=" + quote(remote + "/wheelhouse/setup-inputs/" + package.name) + "\n"
    if codec_inputs:
        sdk_environment += "$env:YUKI_MEDIA_CODEC_WHEELS=" + quote(remote + "/wheelhouse/media-codecs") + "\n"
    if host_candidate:
        sdk_environment += "$env:YUKI_HOST_CANDIDATE=" + quote(remote + "/wheelhouse/extension-host-candidate.zip") + "\n"
    if native_crates:
        sdk_environment += "$env:YUKI_CRATE_CACHE=" + quote(remote + "/wheelhouse/native-crates") + "\n"
    if release_assets:
        sdk_environment += "$env:YUKI_CORE031_RELEASE_DIR=" + quote(remote + "/wheelhouse/core031-release")
    setup = f"""
Expand-Archive -LiteralPath {quote(remote + '/tooling.zip')} -DestinationPath {quote(remote + '/wheelhouse')} -Force
if (-not (Test-Path {quote(tooling + '/Scripts/uv.exe')})) {{
  py -3.12 -m venv {quote(tooling)}
  if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
  & {quote(tooling + '/Scripts/python.exe')} -m pip install --disable-pip-version-check --no-index --no-deps {quote(remote + '/wheelhouse/' + locked['uv']['filename'])}
  if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
}}
$env:PATH={quote(tooling + '/Scripts;')}+$env:PATH
$env:TEMP={quote(remote + '/temp')}
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
$env:UV_CACHE_DIR={quote(args.remote_root.rstrip('/') + '/uv-cache')}
$env:UV_OFFLINE='true'
$env:UV_NO_INDEX='1'
$env:UV_FIND_LINKS={quote(remote + '/wheelhouse')}
$expected={quote(digest)}
$actual=(Get-FileHash -Algorithm SHA256 {quote(remote + '/source.zip')}).Hash.ToLower()
if ($actual -ne $expected) {{ throw 'snapshot digest mismatch' }}
Expand-Archive -LiteralPath {quote(remote + '/source.zip')} -DestinationPath {quote(remote + '/src')} -Force
Set-Location {quote(remote + '/src')}
$env:YUKI_SOURCE_SNAPSHOT_SHA256=$expected
{('$env:YUKI_BASELINE_WHEEL=' + quote(remote + '/wheelhouse/' + baseline['wheel_name'])) if connector_mode else ''}
$env:YUKI_DESKTOP_TOOLS={quote(remote + '/wheelhouse/desktop-tools')}
$env:YUKI_RUNTIME_CACHE={quote(remote + '/wheelhouse/runtime-cache')}
{sdk_environment}
py -3.12 {'connector/packaging/verify_source.py' if args.connector_source else 'ci/check.py ' + args.task}{' --preparation' if args.preparation else ''} --out artifacts/{args.task}/{args.run}
$result=$LASTEXITCODE
$zipCode=@'
import pathlib, zipfile
p=pathlib.Path('artifacts/{args.task}/{args.run}')
with zipfile.ZipFile('../evidence-{args.task}-{args.run}.zip','w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(p.rglob('*')):
        if f.is_file() and not any(x in {{'work','packages','__pycache__'}} for x in f.relative_to(p).parts):
            z.write(f,f.relative_to(p))
'@
py -3.12 -c $zipCode
if ($LASTEXITCODE -ne 0) {{ exit $LASTEXITCODE }}
exit $result
"""
    result = powershell(args.host, setup)
    evidence = transfer / f"{digest}-{args.task}-{args.run}.zip"
    copy = invoke(["scp", "-q", f"{args.host}:{remote}/evidence-{args.task}-{args.run}.zip", str(evidence)])
    if copy.returncode == 0:
        output.mkdir(parents=True)
        with zipfile.ZipFile(evidence) as archive:
            for info in archive.infolist():
                path = output / info.filename
                if not path.resolve().is_relative_to(output.resolve()):
                    raise ValueError("invalid remote evidence path")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(info))
        (output / "transport.json").write_text(json.dumps({"host": args.host, "remote_directory": remote,
            "source_snapshot_sha256": digest, "evidence_zip_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            "exit_code": result.returncode}, indent=2) + "\n", encoding="utf-8")
        print("Evidence:", output)
    return result.returncode or copy.returncode


if __name__ == "__main__":
    sys.exit(main())
