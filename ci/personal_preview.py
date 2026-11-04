"""Run a pinned personal Host with the named real plugin in its own isolated owner."""

from contextlib import contextmanager
import hashlib
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid

from host_preview import materialize
from package import build


def free_address():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return "127.0.0.1:" + str(s.getsockname()[1])


def http(address, method, path, body=None, token=None, headers=None):
    extra = dict(headers or {})
    if token:
        extra["Authorization"] = "Bearer " + token
    if body is not None:
        extra["Content-Type"] = "application/json"
    conn = HTTPConnection(address, timeout=12)
    try:
        conn.request(
            method,
            path,
            body=None if body is None else json.dumps(body).encode(),
            headers=extra,
        )
        r = conn.getresponse()
        data = r.read()
        if not data:
            return r.status, {}
        media = r.getheader("Content-Type", "").split(";", 1)[0].lower()
        if media == "application/json" or media.endswith("+json"):
            return r.status, json.loads(data)
        if r.status < 400:
            raise ValueError(f"unexpected successful response type {media}")
        return r.status, {"content_type": media}
    finally:
        conn.close()


class Owner:
    def __init__(
        self,
        root,
        out,
        unit,
        grants,
        *,
        contract="core-033",
        environment=None,
        relay=None,
        command_timeout=12,
    ):
        self.command_timeout = command_timeout
        self.root = root
        self.out = out
        self.unit = unit
        self.work = out / "work"
        self.work.mkdir()
        self.exe, self.pin, self.platform = materialize(root, self.work, contract)
        self.data = self.work / "owner"
        self.packages = out / "packages"
        package = build(root, unit, self.packages)
        self.plugin = self.packages / (
            "yuki-" + unit + (".exe" if os.name == "nt" else "")
        )
        self.binary_sha = package["artifacts"][self.plugin.name]
        self.address = free_address()
        self.edge = free_address()
        while self.address == self.edge:
            self.edge = free_address()
        self.trace = self.work / "wire.jsonl"
        prefix = "YUKI_" + unit.upper().replace("-", "_")
        self.env = dict(os.environ)
        settings = {prefix + "_CORE": self.address, prefix + "_LISTEN": self.edge}
        if unit == "local-agent":
            settings[prefix + "_STATE"] = str(self.work / "catalog")
        settings.update(environment or {})
        self.env.update(settings)
        self.cli("init")
        cfg = self.data / "yuki.toml"
        text = cfg.read_text(encoding="utf-8")
        assert '"127.0.0.1:0"' in text
        text = text.replace('"127.0.0.1:0"', json.dumps(self.address))
        fields = {
            "id": unit,
            "namespace": unit,
            "program": sys.executable,
            "args": [
                str(root / "tests/peers" / (relay or "observe_stdio.py")),
                str(self.plugin),
                str(self.trace),
            ],
            "grants": grants,
            "env": list(settings),
        }
        if relay:
            fields["args"].append(str(self.work / "control"))
            (self.work / "control").mkdir()
        cfg.write_text(
            text
            + "\n[[plugins]]\n"
            + "\n".join(k + "=" + json.dumps(v) for k, v in fields.items())
            + "\n",
            encoding="utf-8",
        )

    def command(self, *args):
        return subprocess.run(
            [self.exe, "--data", self.data, *args],
            cwd=self.work,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=self.command_timeout,
        )

    def cli(self, *args):
        r = self.command(*args)
        if r.returncode:
            raise RuntimeError(
                "Host CLI refused " + str(args[:2]) + ": " + r.stderr[:200]
            )
        return json.loads(r.stdout) if r.stdout.strip() else None

    def issue(self, person, purpose):
        return self.cli(
            "operator", "personal", "issue", person, str(uuid.uuid4()), purpose
        )["code"]

    @contextmanager
    def running(self):
        with (self.out / "host.txt").open("ab") as log:
            proc = subprocess.Popen(
                [self.exe, "--data", self.data, "run"],
                cwd=self.work,
                env=self.env,
                stdout=log,
                stderr=log,
            )
        try:
            end = time.monotonic() + 20
            while time.monotonic() < end:
                if proc.poll() is not None:
                    raise RuntimeError("candidate exited before handshake")
                r = self.command("operator", "host", "status")
                if r.returncode == 0 and any(
                    p["online"] for p in json.loads(r.stdout)["plugins"]
                ):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("personal plugin handshake timed out")
            yield
        finally:
            if proc.poll() is None:
                self.command("operator", "shutdown")
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            if self.trace.exists():
                (self.out / "wire.jsonl").write_bytes(self.trace.read_bytes())

    def evidence(self):
        return {
            "source_commit": self.pin["source_commit"],
            "handoff_commit": self.pin["handoff_commit"],
            "published": False,
            "host": self.platform,
            "sdk": {
                "version": self.pin["sdk"]["rust"],
                "sha256": self.pin["rust_crate_sha256"],
            },
            "host_schema_sha256": self.pin["schema_sha256"],
            "personal_schema_sha256": self.pin.get("personal_schema_sha256"),
            "media_schema_sha256": self.pin.get("media_schema_sha256"),
            "plugin_sha256": self.binary_sha,
            "wire_sha256": hashlib.sha256(self.trace.read_bytes()).hexdigest(),
        }
