"""Real installed CLI, original journals and pipe shell with two TLS wire fixtures.

These local protocol fixtures do not implement or stand in for a core Host.
Only the existing Connector is exercised; its runtime sources are unchanged.
"""
import asyncio
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
import sys
import time
import uuid

from websockets.asyncio.server import serve
from yuki_agent_connector.config import Config, Instance
from yuki_agent_connector.journal import Journal

ROOT, OUT = map(Path, sys.argv[1:3])
WORK = OUT / "work"
TOKEN = "ISOLATED_ADDRESS_TOKEN_NEVER_PRINT"
SECRET = "ISOLATED_NATIVE_SECRET_NEVER_PRINT"
CASES, WIRE, PROCESSES = [], [], []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(name, **facts):
    CASES.append({"case": name, **facts})
    (OUT / "cases.json").write_text(json.dumps(CASES, ensure_ascii=False, indent=2), encoding="utf-8")


def journal_snapshot(path):
    with sqlite3.connect(path) as db:
        return {t: db.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
                for t in ["installation", "operations", "events"]}


async def eventually(function, label, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = function()
        if value: return value
        await asyncio.sleep(.05)
    raise RuntimeError("timeout: " + label)


async def cli(directory, *arguments, running=False):
    p = await asyncio.create_subprocess_exec(sys.executable, "-X", "utf8", "-m", "yuki_agent_connector",
        "--data-dir", str(directory), *arguments, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    PROCESSES.append(p)
    if running: return p
    stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=15)
    text = (stdout + stderr).decode("utf-8")
    assert TOKEN not in text and SECRET not in text
    return p.returncode, text


async def stop(p):
    if p.returncode is None: p.terminate()
    return await asyncio.wait_for(p.communicate(), timeout=10)


class WireFixture:
    def __init__(self, name, context, *, mode="normal", dropped=()):
        self.name, self.context, self.mode = name, context, mode
        self.dropped = set(dropped)
        self.connections, self.events, self.pending = [], [], {}
        self.TLS = []
        self.socket = None

    async def __aenter__(self):
        self.server = await serve(self.connection, "127.0.0.1", 0, ssl=self.context)
        self.url = f"wss://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/agents/v1/connect"
        return self

    async def __aexit__(self, *args):
        self.server.close()
        await self.server.wait_closed()

    async def connection(self, socket):
        assert socket.request.headers["Authorization"] == "Bearer " + TOKEN
        secure = socket.transport.get_extra_info("ssl_object")
        assert secure is not None
        self.TLS.append({"version": secure.version(), "cipher": secure.cipher()[0]})
        self.connections.append(socket)
        if self.mode != "normal":
            reason = "unsupported_connector_protocol" if self.mode == "protocol" else "credential_revoked"
            await socket.close(code=1008, reason=reason)
            return
        self.socket = socket
        try:
            async for raw in socket:
                value = json.loads(raw)
                WIRE.append({"endpoint": self.name, "direction": "from_connector", "frame": value,
                             "frame_sha256": hashlib.sha256(raw.encode()).hexdigest()})
                if value.get("type") == "hello":
                    assert value["protocol_version"] == 4
                elif value.get("type") == "response":
                    self.pending.pop(value["id"]).set_result(value)
                elif "event_id" in value:
                    self.events.append(value["event_id"])
                    # The fixture owns this receipt, not core state. Persist before ACK.
                    receipt = WORK / (self.name + "-received.json")
                    receipt.write_text(json.dumps(self.events), encoding="utf-8")
                    if value["event_id"] not in self.dropped:
                        await socket.send(json.dumps({"type": "ack", "event_id": value["event_id"]}))
        finally:
            if self.socket is socket: self.socket = None

    async def rpc(self, command):
        await eventually(lambda: self.socket is not None, self.name + " connected")
        key = command["id"]
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        frame = {"type": "command", **command}
        raw = json.dumps(frame, ensure_ascii=False)
        WIRE.append({"endpoint": self.name, "direction": "to_connector", "frame": frame,
                     "frame_sha256": hashlib.sha256(raw.encode()).hexdigest()})
        await self.socket.send(raw)
        value = await asyncio.wait_for(future, timeout=15)
        assert "error" not in value, value
        return value["result"]


async def simple_addresses():
    targets = [("https://new.example/role/yuki/", "wss://new.example/role/yuki/agents/v1/connect"),
               ("http://127.0.0.1:18767/role/yuki", "ws://127.0.0.1:18767/role/yuki/agents/v1/connect"),
               ("http://localhost:18767", "ws://localhost:18767/agents/v1/connect"),
               ("http://[::1]:18767", "ws://[::1]:18767/agents/v1/connect")]
    for index, (target, expected) in enumerate(targets):
        directory = WORK / f"save-{index}"; directory.mkdir()
        original = Config("wss://old.example/agents/v1/connect", str(uuid.uuid4()), TOKEN,
            [Instance("original", "acp", "Original", "not-started-native-program", ["--original"],
                      str(directory), {"NATIVE_SECRET": SECRET}, endpoint="ws://native-owner.invalid")], True)
        path = directory / "config.json"; original.save(path)
        service = directory / "service.xml"; service.write_bytes(b"never-installed original registration")
        before = sha(service)
        code, text = await cli(directory, "server", "--url", target)
        assert code == 0, text
        assert asdict(Config.load(path)) == asdict(replace(original, url=expected))
        assert sha(service) == before and not (directory / "journal.sqlite3").exists()
        record("save-original-installation", target=target, expected_endpoint=expected,
               original_fields_preserved=True, service_marker_sha256=before, journal_created=False)
    for index, target in enumerate(["http://100.100.100.100", "http://remote.invalid", "ftp://host"]):
        directory = WORK / f"unsafe-{index}"; directory.mkdir()
        path = directory / "config.json"; Config("wss://old.example/agents/v1/connect", str(uuid.uuid4()), TOKEN).save(path)
        before = path.read_bytes();code, text = await cli(directory, "server", "--url", target)
        assert code == 1 and path.read_bytes() == before, text
        record("remote-TLS-required", target=target, exit_code=code, config_unchanged=True)


async def legacy_journals(context):
    for version in [0, 1]:
        directory = WORK / f"legacy-{version}"; directory.mkdir()
        device = str(uuid.uuid4());path = directory / "journal.sqlite3"
        journal = Journal(path, namespace=json.dumps(["wss://old.example/agents/v1/connect", device]))
        for key, state in [("original-completed", "succeeded"), ("original-pending", "running")]:
            journal.begin({"id": key, "resource": "terminal", "action": "exec", "run_id": key})
            journal.complete(key, {"result": {"status": state, "run_id": key}})
        journal.append({"type": "terminal_event", "event_id": "original-unconfirmed-event",
            "operation_id": "original-pending", "kind": "progress",
            "result": {"status": "running", "run_id": "original-pending"}})
        if version == 0: journal.db.execute("UPDATE operations SET receipt=NULL")
        journal.db.execute("ALTER TABLE operations DROP COLUMN owner_source")
        journal.db.execute(f"PRAGMA user_version={version}");journal.db.commit();journal.close()
        before = journal_snapshot(path)
        async with WireFixture(f"legacy-{version}", context, dropped=["original-unconfirmed-event"]) as endpoint:
            Config(endpoint.url, device, TOKEN).save(directory / "config.json")
            p = await cli(directory, "run", running=True)
            try:
                await eventually(lambda: endpoint.events, "legacy event sent")
                after = journal_snapshot(path)
                assert after["installation"] == [(device,)]
                assert [row[0] for row in after["operations"]] == ["original-completed", "original-pending"]
                assert [json.loads(row[4])["status"] for row in after["operations"]] == ["succeeded", "running"]
                assert after["events"][0][1] == "original-unconfirmed-event"
                assert all(row[-1] is None for row in after["operations"])
                if version == 1:
                    assert [row[:-1] for row in after["operations"]] == before["operations"]
                    assert after["events"] == before["events"]
            finally: await stop(p)
        reopened = Journal(path, namespace=device);reopened.close()
        assert journal_snapshot(path) == after
        record("upgrade-original-url-namespace", receipt_version=version, before=before, after=after,
               original_unconfirmed_event_preserved=True, same_device_reopen=True)
    directory = WORK / "different-device";directory.mkdir();path = directory / "journal.sqlite3"
    original = str(uuid.uuid4());other = str(uuid.uuid4())
    journal = Journal(path, namespace=json.dumps(["wss://old.example/agents/v1/connect", original]))
    journal.begin({"id": "original-operation", "action": "exec", "run_id": "original-run"});journal.close()
    before = journal_snapshot(path)
    Config("wss://new.example/agents/v1/connect", other, TOKEN).save(directory / "config.json")
    code, text = await cli(directory, "run")
    assert code == 1 and journal_snapshot(path) == before, text
    record("different-device-rejected-before-connect", exit_code=code, original_evidence_preserved=True)


async def live_shell(context):
    directory = WORK / "live-shell";directory.mkdir();device = str(uuid.uuid4())
    path = directory / "journal.sqlite3"
    journal = Journal(path, namespace=device)
    journal.begin({"id": "offline-unknown", "resource": "terminal", "action": "exec", "run_id": "unknown-run"})
    for key in ["already-acked", "retained-before-url"]:
        journal.append({"type": "terminal_event", "event_id": key, "kind": "progress", "result": {"status": "unknown"}})
    journal.close()
    counter, pidfile, script = directory / "launches.txt", directory / "native.pid", directory / "original-shell.py"
    script.write_text("import os,pathlib\np=pathlib.Path(__file__).parent\n(p/'launches.txt').open('a').write('launch\\n')\n(p/'native.pid').write_text(str(os.getpid()))\ninput()\nprint('original-shell-completed-完成',flush=True)\n", encoding="utf-8")
    def q(value): return "'" + str(value).replace("'", "''") + "'"
    command = {"id": "original-address-shell", "resource": "terminal", "action": "exec", "run_id": "original-address-run",
               "arguments": {"command": "& " + q(sys.executable) + " -X utf8 -u " + q(script), "cwd": str(directory), "tty": False}}
    async with WireFixture("WSS-A", context, dropped=["retained-before-url"]) as first, WireFixture("WSS-B", context) as second:
        Config(first.url, device, TOKEN, full_access=True).save(directory / "config.json")
        service = directory / "service.xml";service.write_bytes(b"stopped service registration; never installed")
        p = await cli(directory, "run", running=True)
        try:
            started = await first.rpc(command)
            assert started["run_id"] == command["run_id"] and started["admitted"] is True
            await eventually(pidfile.exists, "original shell started")
            pid = int(pidfile.read_text());assert counter.read_text().splitlines() == ["launch"]
            target = "https://" + second.url.removeprefix("wss://").removesuffix("/agents/v1/connect")
            code, text = await cli(directory, "server", "--url", target)
            assert code == 0, text
            assert Config.load(directory / "config.json").url == second.url
            assert len(first.connections) == 1 and not second.connections
            result = await first.rpc({"id": "original-address-input", "resource": "terminal", "action": "input",
                "run_id": command["run_id"], "arguments": {"text": "continue\n"}})
            assert result["input_delivered"] is True
            last = None
            for i in range(100):
                last = await first.rpc({"id": "read-" + str(i), "resource": "terminal", "action": "get",
                    "arguments": {"operation_id": command["id"]}})
                if last.get("status") == "succeeded": break
                await asyncio.sleep(.05)
            assert last["status"] == "succeeded" and last["exit_code"] == 0, last
            output = await first.rpc({"id": "output-before-restart", "resource": "terminal", "action": "read", "run_id": command["run_id"], "arguments": {"cursor": 0}})
            assert "original-shell-completed-完成" in output["output"]
            assert int(pidfile.read_text()) == pid and counter.read_text().splitlines() == ["launch"]
            record("live-shell-kept-while-saving-address", original_pid=pid, run_id=command["run_id"],
                   input_delivered=True, original_socket_retained=len(first.connections) == 1,
                   new_endpoint_connections=0, receipt=last, service_marker_sha256=sha(service))
            await eventually(lambda: not any(row[1] == "already-acked" for row in journal_snapshot(path)["events"]), "first ACK committed")
        finally: await stop(p)
        before = journal_snapshot(path)
        assert any(row[1] == "retained-before-url" for row in before["events"])
        pending_before_restart = [row[1] for row in before["events"]]
        p = await cli(directory, "run", running=True)
        try:
            await eventually(lambda: "retained-before-url" in second.events, "original event replay")
            original = await second.rpc({"id": "get-after-restart", "resource": "terminal", "action": "get", "arguments": {"operation_id": command["id"]}})
            unknown = await second.rpc({"id": "get-offline-unknown", "resource": "terminal", "action": "get", "arguments": {"operation_id": "offline-unknown"}})
            assert original["status"] == "succeeded" and original["run_id"] == command["run_id"]
            assert unknown["status"] == "unknown" and counter.read_text().splitlines() == ["launch"]
            assert "already-acked" not in second.events
            await eventually(lambda: not journal_snapshot(path)["events"], "second ACK committed")
            assert set(second.events) == set(pending_before_restart)
            record("same-device-new-WSS-reuses-originals", original_receipt=original, unknown_receipt=unknown,
                   first_events=first.events, second_events=second.events, native_launches=1,
                   namespace=journal_snapshot(path)["installation"], original_pid=pid,
                   pending_before_restart=pending_before_restart, pending_after_ACK=[],
                   first_TLS=first.TLS, second_TLS=second.TLS,
                   service_scope="unchanged registration marker; no OS service install/start exercised")
        finally: await stop(p)


async def negative_connections(context):
    for mode in ["protocol", "revoked"]:
        directory = WORK / ("negative-" + mode);directory.mkdir();device = str(uuid.uuid4())
        path = directory / "journal.sqlite3";journal = Journal(path, namespace=device)
        journal.begin({"id": "unknown-original", "action": "exec", "run_id": "old-run"});journal.close()
        before = journal_snapshot(path)
        async with WireFixture(mode, context, mode=mode) as endpoint:
            Config(endpoint.url, device, TOKEN).save(directory / "config.json")
            p = await cli(directory, "run", running=True)
            try:
                await eventually(lambda: endpoint.connections, mode + " first connection")
                await asyncio.sleep(.5)
                assert len(endpoint.connections) == 1 and journal_snapshot(path) == before
                record(mode + "-does-not-replay-native-operation", connections=1, original_evidence_preserved=True,
                       foreground_exit_code=p.returncode, emitted_events=endpoint.events)
            finally: await stop(p)


async def main():
    sys.path.insert(0, str(ROOT / "tests/peers"))
    from connector_tls import certificate
    certificate(WORK)
    os.environ["SSL_CERT_FILE"] = str(WORK / "ingress.pem")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(WORK / "ingress.pem", WORK / "ingress-key.pem")
    try:
        await simple_addresses()
        await legacy_journals(context)
        await live_shell(context)
        await negative_connections(context)
        baseline = json.loads((ROOT / "compat/wire4/address_cases/source.lock.json").read_bytes())
        assert len(baseline["receipts"]) == 11
        for item in baseline["receipts"]:
            assert sha(ROOT / "compat/wire4/address_cases" / item["file"]) == item["sha256"]
        for value in [CASES, WIRE]:
            encoded = json.dumps(value, ensure_ascii=False)
            assert TOKEN not in encoded and SECRET not in encoded
        result = {"cases": CASES, "old_inputs": {"count": 11, "source_commit": baseline["baseline"],
                  "github_artifact_digest": baseline["github_artifact"]["digest"], "historical_only": True},
                  "transport": "two isolated WSS wire4 fixtures with original TLS verification",
                  "core_host_substituted": False,
                  "service_scope": "wire phase uses registration markers; a separate native helper verifies a disabled owned Windows task",
                  "paid_calls": "not configured or invoked"}
        (OUT / "address-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        for p in PROCESSES:
            if p.returncode is None: await stop(p)
        (OUT / "wire.json").write_text(json.dumps(WIRE, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
