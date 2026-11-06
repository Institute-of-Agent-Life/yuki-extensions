"""Real Rust wire4 catalog, current core device authority and original Connector."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from package import build
from personal_preview import Owner, http


def prepare(root, output):
    owner = Owner(root, output, "local-agent", ["device.connections"],
                  contract="core-033-connector", relay="device_stdio.py", command_timeout=30,
                  environment={"YUKI_LOCAL_AGENT_INSTALLATION": "local-agent"})
    connector_package = build(root, "connector", owner.packages / "connector")
    wheel = next((owner.packages / "connector").glob("*.whl"))
    environment = owner.work / "connector-env"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    peers, commands, cases, secrets = [], [], [], []
    tls = None
    model_requests = []

    class Recorder(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            model_requests.append(self.path)
            self.send_response(503); self.send_header("Content-Length", "0"); self.end_headers()
    recorder = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=recorder.serve_forever, daemon=True).start()
    config = owner.data / "yuki.toml"
    text = config.read_text(encoding="utf-8").replace('mode = "hybrid"', 'mode = "lexical-only"')
    # Installation authority is independent of the SDK tool namespace.
    assert 'namespace="local-agent"' in text
    text = text.replace('namespace="local-agent"', 'namespace="connector-catalog"')
    text = text.replace("\n[[plugins]]", f'\n[main]\nendpoint="http://127.0.0.1:{recorder.server_port}/model"\nbinding_endpoint="http://127.0.0.1:{recorder.server_port}/binding"\nmodel="fixture"\nname="Yuki"\nmerge_ms=1\nroot_slots=8\nroot_tool_calls=8\nmax_input_units=200000\nmax_output=512\n\n[[plugins]]')
    config.write_text(text, encoding="utf-8")

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(argv, **kwargs):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, encoding="utf-8", timeout=180, **kwargs)
        if result.returncode:
            raise RuntimeError("fixture command failed: " + str(argv[:2]) + ": " + result.stderr[-600:])
        return result

    def wait(function, label, timeout=25):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = function()
            if value: return value
            time.sleep(.1)
        raise RuntimeError("timed out: " + label)

    def snapshot():
        return json.loads(run([owner.plugin, "--catalog"], env=owner.env).stdout)

    def device(value, identity):
        return next((x for x in value["catalog"] if x["device_id"] == identity), None)

    def note(name, value):
        cases.append({"case": name, "result": value}); save("cases.json", cases)

    def pair(person, label):
        code = owner.issue(person, "connector"); secrets.append(code)
        target = owner.work / (label + "-paired.json")
        run([python, "-m", "yuki_agent_connector", "--config", target, "pair", "--url",
             "http://" + owner.edge, "--label", label, "--code-stdin"], input=code + "\n")
        value = json.loads(target.read_bytes()); secrets.append(value["token"])
        assert http(owner.edge, "POST", "/agents/v1/pair", {"code": code, "device_label": "replay"})[0] == 401
        return value

    def peer(label, credential, instances, *, allow_closed=False, automatic=False):
        work = owner.work / label; work.mkdir()
        control = work / "control"; control.mkdir()
        private = work / "credential.json"
        private.write_text(json.dumps({"url": tls.url,
            "device_id": credential["device_id"], "token": credential["token"], "instances": instances,
            "automatic": automatic}), encoding="utf-8")
        with (output / (label + ".txt")).open("wb") as log:
            process = subprocess.Popen([str(python), "-X", "utf8", str(root / "tests/peers/connector_catalog_peer.py"),
                str(private), str(control)], stdout=log, stderr=log,
                env={**os.environ, "SSL_CERT_FILE": str(owner.work / "ingress.pem")})
        item = {"label": label, "process": process, "control": control, "next": 0}
        peers.append(item)
        wait(lambda: (control / "connected.json").exists() or process.poll() is not None, label + " transport")
        assert (control / "connected.json").exists() and (allow_closed or process.poll() is None), (label, (output / (label + ".txt")).read_text())
        connection = json.loads((control / "connected.json").read_bytes())
        assert connection["tls"]["certificate_required"] and connection["tls"]["hostname_check"]
        assert connection["journal_namespace"] == credential["device_id"]
        save(label + "-transport.json", connection)
        return item

    def tell(item, command):
        item["next"] += 1
        (item["control"] / f'command-{item["next"]}.json').write_text(json.dumps(command), encoding="utf-8")

    def close(item):
        if item["process"].poll() is None:
            tell(item, {"action": "close"})
        item["process"].wait(timeout=10)
        assert item["process"].returncode == 0, (item["label"], (output / (item["label"] + ".txt")).read_text())
        return json.loads((item["control"] / "result.json").read_bytes())

    try:
        run(["uv", "venv", "--python", sys.executable, str(environment)])
        run(["uv", "pip", "install", "--python", python, "--offline", "--no-index", wheel])
        run([python, root / "tests/peers/connector_tls.py", owner.work])
        sys.path.insert(0, str(root / "tests/peers"))
        from connector_tls import Ingress
        tls = Ingress(owner.work / "ingress.pem", owner.work / "ingress-key.pem", owner.edge)
        save("tls-ingress.json", {"url": tls.url, "certificate_sha256":
            hashlib.sha256((owner.work / "ingress.pem").read_bytes()).hexdigest(),
            "certificate_verification": "original Python TLS defaults with explicit isolated test CA",
            "wire_modification": False, "public_deployment": False})
        original, merged, other = [str(uuid.uuid4()) for _ in range(3)]
        with owner.running():
            for person in [original, merged, other]: owner.cli("operator", "person", "create", person)
            chat_code = owner.issue(original, "chat"); secrets.append(chat_code)
            status, response = http(owner.address, "POST", "/client/v1/pair", {"code": chat_code, "device_label": "chat"})
            assert status == 200
            chat = response.get("data", response)["token"]; secrets.append(chat)
            account_before = owner.cli("operator", "account", "open", "qq", "connector-auth", "external", "1", "--person", original, "--start", "1")
            credential = pair(original, "original")
            identity = credential["device_id"]
            assert http(owner.address, "GET", "/client/v1/me", token=credential["token"])[0] == 401
            headers = {"Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
                       "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="}
            for label, token in [("missing", None), ("chat", chat)]:
                code, _ = http(owner.edge, "GET", "/agents/v1/connect", token=token, headers=headers)
                assert code in {401, 403}, (label, code)
                note(label + "-credential-denied", code)
            first = peer("empty-original", credential, [])
            initial = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connected"] else None), "empty device")
            assert initial["instances"] == []
            namespace, epoch = initial["journal_namespace"], initial["connection_epoch"]
            assert namespace and epoch > 0
            note("original-connector-empty-device", initial)
            second = peer("replacement", credential, [{"id": "native", "label": "new snapshot"}])
            current = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connection_epoch"] > epoch and x["instances"] else None), "new epoch")
            assert current["journal_namespace"] == namespace
            tell(first, {"action": "catalog", "instances": [{"id": "late", "label": "must not publish"}]})
            wait(lambda: first["process"].poll() is not None, "old connection rejected")
            close(first)
            retained = device(snapshot(), identity)
            assert retained["connected"] and retained["connection_epoch"] == current["connection_epoch"]
            assert [x["id"] for x in retained["instances"]] == ["native"]
            note("old-catalog-and-close-fenced", retained)
            tell(second, {"action": "catalog", "instances": []})
            empty = wait(lambda: (x if (x := device(snapshot(), identity)) and not x["instances"] and x["connected"] else None), "full empty catalog")
            note("full-snapshot-removes-instances-keeps-device", empty)
            close(second)
            wait(lambda: not device(snapshot(), identity)["connected"], "disconnect retained")
            renewing = peer("original-run-renewal", credential, [], automatic=True)
            start = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connected"] else None), "original run connected")
            before_renewal = time.monotonic()
            renewed_path = renewing["control"] / "connection-2.json"
            wait(lambda: renewed_path.exists() or renewing["process"].poll() is not None, "original run automatic renewal", timeout=275)
            assert renewed_path.exists() and renewing["process"].poll() is None
            renewed = json.loads(renewed_path.read_bytes())
            assert renewed["automatic_run"] and not renewed["owner_stopped"]
            assert renewed["journal_namespace"] == identity
            assert renewed["tls"]["certificate_required"] and renewed["tls"]["hostname_check"]
            after = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connected"] and x["connection_epoch"] > start["connection_epoch"] else None), "renewed original epoch")
            elapsed = time.monotonic() - before_renewal
            assert 220 <= elapsed < 290, elapsed
            assert after["journal_namespace"] == namespace
            note("original-run-renews-before-expiry-without-authorization-loss", {"elapsed_seconds": elapsed, "before": start, "after": after, "original_run": renewed})
            close(renewing)
            merge = owner.cli("operator", "person", "merge", original, merged)
            assert merge["original"] == original and merge["root"] == merged
            after_merge = peer("person-merged", credential, [{"id": "same", "label": "same device"}])
            merged_view = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connected"] and x["instances"] else None), "merged device")
            assert merged_view["journal_namespace"] == namespace and merged_view["connection_epoch"] > current["connection_epoch"]
            note("person-merge-keeps-original-device-namespace", merged_view)
            close(after_merge)
            # The public operator transition ends the old assignment first.
            # account.open alone correctly refuses a different current owner.
            account_after = owner.cli("operator", "account", "transfer", account_before["assignment"], "2", "2", "--person", other)
            assert account_before["account"] == account_after["account"] and account_before["assignment"] != account_after["assignment"]
            swapped = peer("account-reassigned", credential, [])
            swap_view = wait(lambda: (x if (x := device(snapshot(), identity)) and x["connected"] else None), "original device after account reassignment")
            assert swap_view["journal_namespace"] == namespace
            note("account-reassignment-does-not-transfer-device", swap_view)
            close(swapped)
            # Authentication remains core-owned when a hello self-reports another device.
            forged = peer("forged-hello", {**credential, "device_id": "forged-device"}, [], allow_closed=True)
            wait(lambda: forged["process"].poll() is not None, "forged hello closed")
            close(forged)
            assert snapshot()["devices"] == [identity]
            note("forged-hello-cannot-create-device", snapshot())
            event_peer = peer("unscoped-event", credential, [])
            wait(lambda: device(snapshot(), identity)["connected"], "event peer hello")
            tell(event_peer, {"action": "event", "id": "no-work-event"})
            wait(lambda: event_peer["process"].poll() is not None, "unscoped event refused")
            result = close(event_peer)
            assert result["pending_event"] is True
            note("unscoped-native-event-keeps-original-journal-no-ACK", result)
            revoked = peer("revoke-current", credential, [])
            wait(lambda: device(snapshot(), identity)["connected"], "current peer")
            owner.cli("operator", "personal", "revoke", identity)
            tell(revoked, {"action": "catalog", "instances": [{"id": "revoked"}]})
            wait(lambda: revoked["process"].poll() is not None, "revoked callback refused")
            close(revoked)
            state = wait(lambda: (x if (x := device(snapshot(), identity)) and not x["connected"] else None), "revoked connection offline")
            assert not state["connected"] and not any(x["id"] == "revoked" for x in state["instances"])
            code, _ = http(owner.edge, "GET", "/agents/v1/connect", token=credential["token"], headers=headers)
            assert code in {401, 403}
            note("revoked-device-cannot-publish-or-reconnect", {"http": code, "catalog": state})
        with owner.running():
            assert snapshot()["devices"] == [identity]
            assert not device(snapshot(), identity)["connected"]
            note("cold-restart-retains-namespace-and-offline-membership", snapshot())
        assert not model_requests, model_requests
        wire = owner.trace.read_text(encoding="utf-8")
        for secret in secrets:
            for path in output.rglob("*"):
                if path.is_file() and not {"work", "packages"}.intersection(path.relative_to(output).parts) and path.suffix in {".json", ".txt", ".jsonl"}:
                    assert secret not in path.read_text(encoding="utf-8"), path
            for path in owner.work.glob("catalog/device-catalog.sqlite3*"):
                assert secret.encode() not in path.read_bytes()
        frames = [json.loads(line) for line in wire.splitlines()]
        methods = {x["frame"].get("method") for x in frames}
        assert {"device.connect", "device.check", "device.close"} <= methods
        save("operator-summary.json", {"original": original, "merged": merged, "other": other,
            "account_before": account_before, "account_after": account_after})
        return "device-catalog.json", {"status": "PASS", "card_status": "UNPUBLISHED_CONNECTOR_AUTHORITY_CANDIDATE",
            **owner.evidence(), "connector": {"version": connector_package["version"],
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(), "source_changed": False},
            "original_device": identity, "journal_namespace": namespace, "model_http_calls": 0,
            "cases": cases, "transcript": frames, "secret_material_exported": False,
            "remaining": ["public producer and consumer publication", "public WSS deployment",
                "original Work-scoped native business callbacks belong to following cards"]}
    finally:
        for item in peers:
            if item["process"].poll() is None:
                item["process"].terminate()
                try: item["process"].wait(timeout=5)
                except subprocess.TimeoutExpired: item["process"].kill(); item["process"].wait()
        if tls is not None: tls.close()
        recorder.shutdown(); recorder.server_close()
        save("cases.json", cases)
        save("model-http.json", model_requests)


def run(root, output):
    return "device-catalog.json", {"status": "BLOCKED", "card_status": "AWAITING_PUBLISHED_AUTHORITY_TUPLE",
        "reason": "The real Rust wire4 consumer is a local unpublished candidate; stable producer/consumer publication is pending."}
