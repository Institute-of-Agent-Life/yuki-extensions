"""Exercise real Connector pairing and the missing device-independent wire authority."""

import hashlib
import json
import os
import subprocess
import sys
import uuid

from package import build
from personal_preview import Owner, http


def prepare(root, output):
    owner = Owner(root, output, "local-agent", [])
    connector = build(root, "connector", owner.packages / "connector")
    wheel = next((owner.packages / "connector").glob("*.whl"))
    env = owner.work / "connector-env"
    python = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def run(args, **kwargs):
        p = subprocess.run(args, capture_output=True, text=True, timeout=120, **kwargs)
        if p.returncode:
            raise RuntimeError(
                "Connector fixture command failed: "
                + str(args[:3])
                + ": "
                + p.stderr[-350:]
            )
        return p

    run(["uv", "venv", "--python", sys.executable, str(env)])
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--offline",
            "--no-index",
            str(wheel),
        ]
    )
    person = str(uuid.uuid4())
    config = owner.work / "connector.json"
    with owner.running():
        owner.cli("operator", "person", "create", person)
        wrong = owner.issue(person, "chat")
        code, payload = http(
            owner.edge,
            "POST",
            "/agents/v1/pair",
            {"code": wrong, "device_label": "wrong-purpose"},
        )
        assert code == 401
        code, reply = http(
            owner.address,
            "POST",
            "/client/v1/pair",
            {"code": wrong, "device_label": "chat-fixture"},
        )
        assert code == 200
        chat = reply.get("data", reply)["token"]
        pair_code = owner.issue(person, "connector")
        run(
            [
                python,
                "-m",
                "yuki_agent_connector",
                "--config",
                config,
                "pair",
                "--url",
                "http://" + owner.edge,
                "--label",
                "HJW Catalog",
                "--code-stdin",
            ],
            input=pair_code + "\n",
        )
        saved = json.loads(config.read_bytes())
        device = saved["device_id"]
        token = saved["token"]
        assert (
            http(
                owner.edge,
                "POST",
                "/agents/v1/pair",
                {"code": pair_code, "device_label": "replay"},
            )[0]
            == 401
        )
        assert http(owner.address, "GET", "/client/v1/me", token=token)[0] == 401
        auth_probe = {}
        for key, credential in [("chat", chat), ("connector", token)]:
            auth_probe[key] = http(
                owner.address,
                "POST",
                "/core/v1/entry/exchange",
                {"purpose": "connector", "plugin": "local-agent"},
                credential,
            )[0]
        assert auth_probe["connector"] == 422
        results = {}
        for key, credential in [("none", None), ("chat", chat), ("original", token)]:
            status, _ = http(
                owner.edge,
                "GET",
                "/agents/v1/connect",
                token=credential,
                headers={
                    "Connection": "Upgrade",
                    "Upgrade": "websocket",
                    "Sec-WebSocket-Version": "13",
                    "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ==",
                },
            )
            results[key] = status
        assert results == {"none": 401, "chat": 503, "original": 503}
    with owner.running():
        visible = json.loads(run([owner.plugin, "--catalog"], env=owner.env).stdout)
        assert visible == {"devices": [device]}
        assert http(owner.address, "GET", "/client/v1/me", token=chat)[0] == 200
    wire = [json.loads(line) for line in owner.trace.read_text().splitlines()]
    assert len([r for r in wire if r["frame"].get("method") == "initialize"]) == 2
    for secret in [pair_code, wrong, token, chat]:
        assert (
            secret not in (output / "host.txt").read_text()
            and secret not in owner.trace.read_text()
        )
    return "device-catalog.json", {
        "status": "PASS",
        "card_status": "PARTIAL_PAIRING_ON_UNPUBLISHED_CANDIDATE",
        **owner.evidence(),
        "connector": {
            "version": connector["version"],
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        },
        "original_device": device,
        "after_restart": visible,
        "wrong_purpose_pair": 401,
        "one_time_code_replay": 401,
        "connector_on_chat_route": 401,
        "workless_exchange": auth_probe,
        "wire4_upgrade": results,
        "transcript": wire,
        "pending": "The Host must bind an idle connector proof to its authenticated device before a hello or catalog can be accepted, including revoked/previously paired devices.",
    }


def run(root, output):
    return "device-catalog.json", {
        "status": "BLOCKED",
        "card_status": "AWAITING_DEVICE_SCOPED_AUTHORITY",
        "reason": "CORE-033 preview grants a Work-scoped proof. The original wire4 hello carries no Work and cannot authenticate the device id.",
    }
