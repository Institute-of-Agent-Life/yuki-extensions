"""One owned, disabled per-user task; never start a service or touch existing tasks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from yuki_agent_connector.config import Config
from yuki_agent_connector.service import UserService


def main(output):
    if os.name != "nt": raise RuntimeError("this case requires Windows Task Scheduler")
    directory = output / "work" / ("stopped-task-" + uuid.uuid4().hex)
    directory.mkdir()
    config = directory / "config.json"
    original = Config("wss://old.example/agents/v1/connect", str(uuid.uuid4()), "ISOLATED_SERVICE_TOKEN")
    original.save(config)
    service = UserService(config, directory)
    before = service.state()
    assert not before["installed"] and not service.artifact.exists()

    def owned():
        state = service.state()
        assert state["installed"]
        expected = {str(Path(sys.executable).resolve()).lower(), str(Path(sys.executable).with_name("pythonw.exe").resolve()).lower()}
        assert str(Path(state["executable"]).resolve()).lower() in expected, state
        assert state["argumentLine"] == subprocess.list2cmdline(service.arguments), state
        return state

    def task(*args):
        return subprocess.run(["schtasks", *args, "/TN", service.name], capture_output=True, check=True).stdout

    result = None
    try:
        service.install()  # Original least-privilege InteractiveToken installation, no start.
        assert not owned()["running"]
        task("/Change", "/Disable")
        installed = owned(); assert not installed["running"]
        xml = task("/Query", "/XML")
        artifact_sha = hashlib.sha256(service.artifact.read_bytes()).hexdigest()
        p = subprocess.run([sys.executable, "-m", "yuki_agent_connector", "--data-dir", str(directory),
            "server", "--url", "https://new.example/role/yuki"], capture_output=True, text=True, encoding="utf-8", timeout=20)
        assert p.returncode == 0, p.stderr
        saved = Config.load(config)
        assert saved.device_id == original.device_id and saved.token == original.token
        assert saved.url == "wss://new.example/role/yuki/agents/v1/connect"
        after = owned(); assert not after["running"]
        assert task("/Query", "/XML") == xml
        assert hashlib.sha256(service.artifact.read_bytes()).hexdigest() == artifact_sha
        assert not (directory / "journal.sqlite3").exists()
        result = {"case": "native-stopped-user-task-not-started-by-address-change", "status": "PASS",
            "before": before, "installed_disabled": installed, "after_address_change": after,
            "task_xml_sha256": hashlib.sha256(xml).hexdigest(), "registration_file_sha256": artifact_sha,
            "task_name": service.name, "start_invoked": False, "existing_task_replaced": False}
    finally:
        current = service.state()
        if current["installed"]:
            owned()  # Confirm this exact generated action before deleting our test task.
            service.uninstall()
        assert not service.state()["installed"]
    result["after_cleanup"] = service.state()
    (output / "native-service.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
