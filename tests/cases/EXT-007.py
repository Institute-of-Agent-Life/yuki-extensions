"""Build/install a real Connector candidate and upgrade copied device evidence.

The independent preparation can pass before CORE-002. Card acceptance cannot.
"""

from __future__ import annotations

import email
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from package import build


VERSION = "0.4.4.dev0"


def audit_wheel(path, source):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        expected = {name.removeprefix("src/"): sha for name, sha in source["original_files_sha256"].items()
                    if name.startswith("src/") and name.endswith(".py")}
        code = {n for n in names if n.startswith("yuki_agent_connector/") and not n.endswith("/")}
        if code != set(expected):
            raise ValueError("runtime wheel content differs from the fixed module inventory")
        for name, sha in expected.items():
            content = archive.read(name)
            if name == "yuki_agent_connector/__init__.py":
                content = content.replace(('__version__ = "' + VERSION + '"').encode(), b'__version__ = "0.4.3"')
            if hashlib.sha256(content).hexdigest() != sha:
                raise ValueError("unreviewed runtime source change: " + name)
        info = f"yuki_agent_connector-{VERSION}.dist-info/"
        if any(not n.startswith(("yuki_agent_connector/", info)) or ".." in Path(n).parts for n in names):
            raise ValueError("unexpected private/config data in the wheel")
        if any(Path(n).name in {".env", "config.json", "journal.db"} or n.endswith((".pyc", ".sqlite3", ".db")) for n in names):
            raise ValueError("private/device data packaged in wheel")
        metadata = email.message_from_bytes(archive.read(info + "METADATA"))
        if metadata["Name"] != "yuki-agent-connector" or metadata["Version"] != VERSION:
            raise ValueError("candidate metadata version/name mismatch")
        if not any(n.startswith(info + "licenses/") for n in names):
            raise ValueError("distribution lost its license text")
        return {"runtime_files": len(code), "files": names, "version": metadata["Version"],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare(root: Path, output: Path):
    connector = root / "connector"
    source = json.loads((connector / "packaging/source.lock.json").read_text(encoding="utf-8"))
    commands = []
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}

    def call(argv, cwd=connector, timeout=900):
        print("Candidate check:", " ".join(map(str, argv[:4])), flush=True)
        result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, text=True,
                                capture_output=True, timeout=timeout)
        commands.append({"command": list(map(str, argv)), "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        (output / "commands.json").write_bytes((json.dumps(commands, indent=2) + "\n").encode())
        if result.returncode:
            raise RuntimeError("candidate check failed; see commands.json: " + str(argv[:4]))
        return result

    packages = output / "packages"
    provided = os.environ.get("YUKI_CONNECTOR_PACKAGE_DIR")
    if provided:
        packages = Path(provided).resolve()
        package = json.loads((packages / "package-manifest.json").read_text())
        assert package["manifest_sha256"] == hashlib.sha256((connector / "pyproject.toml").read_bytes()).hexdigest()
        assert package["lock_sha256"] == hashlib.sha256((connector / "uv.lock").read_bytes()).hexdigest()
        for name, expected in package["artifacts"].items():
            assert hashlib.sha256((packages / name).read_bytes()).hexdigest() == expected
    else:
        package = build(root, "connector", packages)
    assert package["version"] == VERSION
    (output / "connector-package.json").write_bytes((json.dumps(package, indent=2) + "\n").encode())
    wheel = next(packages.glob("*.whl"))
    inventory = audit_wheel(wheel, source)
    work = output / "work"
    work.mkdir()
    injected = work / "injected.whl"
    shutil.copyfile(wheel, injected)
    with zipfile.ZipFile(injected, "a") as archive:
        archive.writestr(".env", "test-only-package-canary")
    try:
        audit_wheel(injected, source)
    except ValueError as exc:
        rejected_private_file = str(exc)
    else:
        raise AssertionError("private configuration injection was accepted")

    # Historical CI input is a pinned test fixture, not a new CORE-002 release.
    baseline = root / "tests/fixtures/connector" / source["historical_ci"]["wheel_name"]
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == source["historical_ci"]["wheel_sha256"]
    requirements = work / "requirements.txt"
    call(["uv", "export", "--frozen", "--all-groups", "--no-emit-project", "--output-file", requirements])
    interpreters = {}
    for label, artifact in [("old", baseline), ("candidate", wheel)]:
        directory = work / (label + "-env")
        call(["uv", "venv", "--python", sys.executable, directory])
        python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        interpreters[label] = python
        local_index = ["--no-index", "--find-links", env["UV_FIND_LINKS"]] if env.get("UV_FIND_LINKS") else []
        call(["uv", "pip", "install", "--python", python, *local_index, "--require-hashes", "-r", requirements])
        call(["uv", "pip", "install", "--python", python, "--no-deps", artifact])
    old = interpreters["old"]
    candidate = interpreters["candidate"]
    original = work / "original-0.4.3"
    upgraded = work / "upgrade-copy"
    probe = root / "tests/peers/connector_upgrade.py"
    upgraded.mkdir()
    old_state = json.loads(call([old, "-I", probe, "seed", original, upgraded / "journal.db"]).stdout)
    assert old_state == {"version": "0.4.3", "operations": 2}
    before = hashlib.sha256((original / "journal.db").read_bytes()).hexdigest()
    journal = json.loads(call([candidate, "-I", probe, "reopen", upgraded / "journal.db", VERSION]).stdout)
    assert hashlib.sha256((original / "journal.db").read_bytes()).hexdigest() == before

    # Merely installing/upgrading and querying status must not start a native daemon.
    marker = work / "native-daemon-started"
    peer = work / "must-not-start.py"
    peer.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('unexpected start')\n", encoding="utf-8")
    device = work / "device"
    setup = ("from pathlib import Path; from yuki_agent_connector.config import Config,Instance; "
             f"Config('ws://127.0.0.1:9','fixture-device-a','test-only-no-credential',"
             f"[Instance('native-original','codex','fixture',{str(candidate)!r},[{str(peer)!r}])]).save(Path({str(device / 'config.json')!r}))")
    call([old, "-I", "-c", setup])
    config_digest = hashlib.sha256((device / "config.json").read_bytes()).hexdigest()
    call([old, "-I", "-m", "yuki_agent_connector", "--data-dir", device, "status", "--json"])
    call(["uv", "pip", "install", "--python", old, "--no-deps", wheel])
    in_place = json.loads(call([old, "-I", "-m", "yuki_agent_connector", "--data-dir", device, "status", "--json"]).stdout)
    assert in_place["version"] == VERSION
    assert hashlib.sha256((device / "config.json").read_bytes()).hexdigest() == config_digest

    status = json.loads(call([candidate, "-I", "-m", "yuki_agent_connector", "--data-dir", device, "status", "--json"]).stdout)
    assert status["version"] == VERSION and not marker.exists()
    empty = work / "empty-device"
    call([candidate, "-I", "-c", "from pathlib import Path; from yuki_agent_connector.config import Config; "
          f"Config('ws://127.0.0.1:9','fixture-empty','test-only-no-credential').save(Path({str(empty / 'config.json')!r}))"])
    assert json.loads(call([candidate, "-I", "-m", "yuki_agent_connector", "--data-dir", empty, "doctor"]).stdout) == []

    call([candidate, "-m", "ruff", "check", "src", "tests", "scripts"])
    call([candidate, "-m", "mypy", "src"])
    call([candidate, "-m", "pytest", "-q", "--junitxml", output / "candidate-tests.xml"], timeout=1200)
    junit = ET.parse(output / "candidate-tests.xml")
    suites = [dict(s.attrib) for s in junit.iter("testsuite")]
    runtime = output / "packages/runtime"
    cache = Path(os.environ.get("YUKI_RUNTIME_CACHE", str(work / "python-cache")))
    call([candidate, "scripts/build_runtime.py", "--output", runtime, "--cache", cache, "--wheel", wheel], timeout=1200)
    runtime_manifest = json.loads((runtime / "manifest.json").read_text(encoding="utf-8"))
    assert runtime_manifest["version"] == VERSION and runtime_manifest["protocol"] == 4
    assert runtime_manifest["connector_wheel"]["sha256"] == inventory["sha256"]
    assert (runtime / "legal/Yuki-LICENSE").read_bytes() == (connector / "LICENSE").read_bytes()
    (output / "connector-runtime.json").write_bytes((json.dumps(runtime_manifest, indent=2) + "\n").encode())
    report = {"status": "PASS", "card_status": "AWAITING_CORE_002", "scope": "independent distribution preparation",
              "version": VERSION, "published": False, "protocol": 4, "source": source,
              "wheel": inventory, "private_file_injection_rejected": rejected_private_file,
              "journal_upgrade": journal, "original_database_unchanged": True,
              "in_place_version": in_place["version"], "device_config_preserved": True,
              "daemon_started": marker.exists(), "pytest_suites": suites,
              "runtime": {k: v for k, v in runtime_manifest.items() if k != "files"},
              "core_oracle_consumed": None, "host_sdk_consumed": None}
    return "connector-upgrade.json", report


def run(root: Path, output: Path):
    return "connector-upgrade.json", {
        "status": "BLOCKED", "card_status": "AWAITING_CORE_002",
        "reason": "This checkout requires the pinned CORE-002 v4-oracle-index.json and its manifest for card acceptance.",
        "preparation_command": "python ci/check.py EXT-007 --preparation --out artifacts/EXT-007/candidate-check",
    }
