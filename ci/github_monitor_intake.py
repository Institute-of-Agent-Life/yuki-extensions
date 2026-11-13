"""Use the pinned SDK to probe the Rust Host with original Monitor requests."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from zipfile import ZipFile

from host_preview import materialize
from personal_preview import free_address


def peer(folder, sdk):
    sys.path.insert(0, str(sdk))
    from yuki_plugin_sdk.connection import Binding, Peer, encode, read_frame
    from yuki_plugin_sdk.host import Calls

    def send(frame):
        sys.stdout.buffer.write(encode(frame))
        sys.stdout.buffer.flush()

    def receive():
        raw = read_frame(sys.stdin.buffer)
        return json.loads(raw) if raw is not None else None

    binding = Binding.from_json(json.loads(os.environ["YUKI_PLUGIN_BINDING"]))
    handshake = Peer(binding)
    send(handshake.request(1, binding.offer()))
    first = read_frame(sys.stdin.buffer)
    handshake.receive(first)
    calls = Calls(json.loads(first)["result"])
    while frame := receive():
        kind, method, params = calls.receive(frame)
        assert kind == "call" and method == "command.invoke"
        action = params["arguments"]["text"].split(maxsplit=1)[-1]
        job = json.loads((folder / f"{action}.json").read_bytes())
        if job["method"] == "notification.grant_target":
            job["params"]["handle"] = params["handle"]
        request = calls.request(frame["id"] + "-callback", job["method"], job["params"])
        send(request)
        response = receive()
        assert response["id"] == request["id"]
        calls.receive(response)
        send({"jsonrpc": "2.0", "id": frame["id"], "result": {"ok": True, "data": response}})


def probe(root, work, replay):
    archive_path = Path(os.environ["YUKI_HOST_CANDIDATE"])
    host, pin, platform = materialize(root, work, "core-058")
    data = work / "owner"
    sdk = work / "sdk"
    sdk.mkdir()
    with ZipFile(archive_path) as archive:
        metadata = json.loads(archive.read("candidate.json"))
        member = f"sdk/yuki_plugin_sdk-{pin['sdk']['python']}-py3-none-any.whl"
        raw = archive.read(member)
        assert sha256(raw).hexdigest() == metadata["members"][member]["sha256"]
        wheel = sdk / "candidate.whl"
        wheel.write_bytes(raw)
        with ZipFile(wheel) as package:
            assert all((sdk / name).resolve().is_relative_to(sdk) for name in package.namelist())
            package.extractall(sdk)
    env = {key: value for key, value in os.environ.items() if "proxy" not in key.lower()}
    env["YUKI_MONITOR_FIXTURE_BOT"] = "local-monitor-fixture"

    def cmd(*args):
        return subprocess.run([host, "--data", data, *map(str, args)], cwd=work, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=15)

    def cli(*args):
        result = cmd(*args)
        assert result.returncode == 0, (args[:3], result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    cli("init")
    config = data / "yuki.toml"
    initial = (config.read_text(encoding="utf-8")
               .replace('mode = "hybrid"', 'mode = "lexical-only"')
               .replace('"127.0.0.1:0"', json.dumps(free_address())))

    @contextmanager
    def running(with_peer=False):
        process = subprocess.Popen([host, "--data", data, "run"], cwd=work, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 20
            status = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode(errors="replace"))
                status = cmd("operator", "host", "status") if with_peer else cmd("operator", "database-info")
                if status.returncode == 0 and (not with_peer or
                    any(row["online"] for row in json.loads(status.stdout)["plugins"])):
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError(f"Host did not become ready: {status.stderr if status else ''}")
            yield
        finally:
            if process.poll() is None:
                cmd("operator", "shutdown")
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stderr.close()

    def operator(*args):
        return cli("operator", *args)

    config.write_text(initial + "\n[[plugins]]\n" + "\n".join(
        f"{name}={json.dumps(value)}" for name, value in {
            "id": "github-monitor", "namespace": "github-monitor",
            "program": str(work / ("legacy-entry.exe" if os.name == "nt" else "legacy-entry")),
            "plugin_api": "9.0", "entrypoint": "github_monitor:GitHubMonitorPlugin",
        }.items()
    ) + "\n", encoding="utf-8")
    rejected = cmd("run")
    assert rejected.returncode != 0 and ("plugin_api" in rejected.stderr or "entrypoint" in rejected.stderr)
    legacy_rejection = {"exit_code": rejected.returncode, "stderr": rejected.stderr.replace(str(work), "$WORK")}
    config.write_text(initial, encoding="utf-8")
    with running():
        bot = operator("account", "open", "qq", "monitor-r11", "100", 1, "--start", 1)
        players = []
        for native in ("200", "201"):
            person = str(uuid.uuid4())
            operator("person", "create", person)
            operator("person", "set-admin", person, "true")
            account = operator("account", "open", "qq", "monitor-r11", native, 1, "--person", person, "--start", 1)
            entry = operator("entry", "private", account["assignment"], bot["assignment"])["entry"]
            players.append((person, account, entry))
    cfg = {
        "id": "monitor-fixture", "namespace": "monitor-fixture", "program": sys.executable,
        "args": [str(Path(__file__).resolve()), "--peer", str(work), str(sdk)],
        "grants": ["command.invoke", "notification.publish", "forget.owner"],
        "commands": ["/monitor-test"],
    }
    config.write_text(initial + "\n[qq]\nnamespace=\"monitor-r11\"\ndesignated_ingress=\"100\"\n"
                      + "[[qq.bots]]\nself_id=\"100\"\nstage=" + json.dumps(bot["assignment"])
                      + '\ntoken_env="YUKI_MONITOR_FIXTURE_BOT"'
                      + "\n[[plugins]]\n" + "\n".join(f"{name}={json.dumps(value)}" for name, value in cfg.items())
                      + "\n[plugins.notifications]\nagent=false\n", encoding="utf-8")

    def target(player):
        return {"target_type": "private", "target_id": player[0], "conversation_id": player[2]}

    operations = []

    def invoke(method, params, player):
        number = len(operations) + 1
        label = f"step-{number}"
        (work / f"{label}.json").write_text(json.dumps({"method": method, "params": params}), encoding="utf-8")
        event = operator("ingress", "record", json.dumps({
            "source": label, "account": player[1]["account"], "bot_stage": bot["assignment"], "reply_bot": "100",
            "kind": "message", "occurred": 100 + number, "observed": 100 + number,
            "segments": [{"type": "text", "text": f"/monitor-test {label}"}]
        }), "--accept")
        execution = operator("ingress", "claim", event["event"])["execution"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            response = cmd("operator", "effect", "read", execution, f"command:{event['event']}", player[0])
            if not response.returncode:
                receipt = json.loads(response.stdout)
                if receipt["state"] == "confirmed":
                    wire = receipt["result"]["data"]
                    operations.append({"method": method, "params": params, "frame": wire, "original": receipt["id"]})
                    return wire
            time.sleep(0.08)
        raise RuntimeError(f"missing {method} receipt")

    old = [row["request"] for row in replay["publication"] if row["request"]["event_type"] == "IssueCommentEvent"]
    assert len(old) == 3 and old[0]["event_key"] == old[1]["event_key"] and old[1] == old[2]
    a, b = players
    first = {**old[0], "target": target(a)}
    second = {**old[1], "target": target(b)}
    with running(with_peer=True):
        assert "result" in invoke("notification.grant_target", {"key": "grant-a", "target": target(a), "bot_user_id": "100"}, a)
        sent = invoke("notification.publish", first, a)["result"]
        assert sent["event_created"] and sent["delivery_enqueued"] and not sent["agent_turn_enqueued"]
        assert invoke("notification.publish", second, a)["error"]["code"] == -32003
        assert "result" in invoke("notification.grant_target", {"key": "grant-b", "target": target(b), "bot_user_id": "100"}, b)
        assert invoke("notification.publish", second, b)["error"]["code"] == -32003
        repeated = invoke("notification.publish", first, a)["result"]
        assert repeated["deduplicated"] and repeated["notification_id"] == sent["notification_id"]
        separated = {**second, "event_key": "monitor-proof:" + sha256(json.dumps(
            [second["event_key"], b[2]], separators=(",", ":")).encode()).hexdigest()}
        distinct = invoke("notification.publish", separated, b)["result"]
        assert distinct["event_created"] and distinct["notification_id"] != sent["notification_id"]
    return {"status": "PASS", "card_status": "BLOCKED", "host_source_commit": pin["source_commit"],
            "host": platform, "sdk": pin["sdk"], "sdk_wheel_sha256": sha256(raw).hexdigest(),
            "old_manifest_sha256": replay["manifest_sha256"], "old_host_package_declaration_rejected": legacy_rejection,
            "operations": operations, "physical_sends": 0, "paid_calls": 0}


def main():
    if sys.argv[1:2] == ["--peer"]:
        peer(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    result = probe(root, args.work.resolve(), json.loads(args.original.read_bytes()))
    with args.out.open("x", encoding="utf-8") as out:
        out.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
