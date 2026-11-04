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
    return invoke(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                   "-o", "StrictHostKeyChecking=yes", host, "powershell", "-NoProfile",
                   "-NonInteractive", "-EncodedCommand", encoded])


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
    args = parser.parse_args()
    connector_mode = args.connector_source or args.connector_candidate
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
    if connector_mode:
        if args.task != "EXT-007":
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
    # Include only locked wheels, not arbitrary files already in the transport cache.
    tools_zip = transfer / "tooling.zip"
    with zipfile.ZipFile(tools_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for package in locked.values():
            archive.write(wheelhouse / package["filename"], package["filename"])
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
$env:YUKI_RUNTIME_CACHE={quote(remote + '/wheelhouse/runtime-cache')}
py -3.12 {'connector/packaging/verify_source.py' if args.connector_source else 'ci/check.py ' + args.task} --out artifacts/{args.task}/{args.run}
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
