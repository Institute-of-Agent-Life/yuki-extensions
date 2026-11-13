"""Replay the unmodified Monitor through the fixed API 9 Host notification owner."""

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
import json
import os
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from github_monitor.config import GitHubMonitorConfig, NotificationTargetConfig, RepositorySubscription
from github_monitor.polling import GitHubPoller
from yuki.conversation.hydrate import ensure_canonical_conversation
from yuki.identity.canonical_repository import find_identity_binding, find_presence
from yuki.persistence.models import ChatEventModel
from yuki.plugin_host.db_models import PluginBackgroundTurnJobModel, PluginInstallationModel
from yuki.plugin_host.loader import PluginLoader
from yuki.plugin_host.manifest import load_manifest
from yuki.plugin_host.notification_repository import PluginNotificationRepository
from yuki_plugin_sdk.errors import PluginPermissionError
from yuki_plugin_sdk.models import NotificationTarget
from yuki_plugin_sdk.observation import PluginObservationContext, PluginObservationRequest
from yuki_plugin_sdk.results import PluginResult
from yuki_plugin_sdk.testing import FakePluginContext


REPOSITORY = "fixture/example"
EXCERPT = "/ai admin group current enable"
BASE = {"id": "100", "type": "WatchEvent", "actor": {"login": "alice", "type": "User"},
        "created_at": "2026-11-01T12:00:00Z", "payload": {"action": "started"}}
UPDATE = {"id": "101", "type": "IssueCommentEvent", "actor": {"login": "alice", "type": "User"},
          "created_at": "2026-11-01T12:01:00Z", "payload": {"action": "created",
                      "comment": {"id": 16, "body": EXCERPT, "html_url": "https://example.invalid/issue#16"}}}


class GitHubFixture:
    def __init__(self):
        self.responses = []
        self.calls = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                assert urlsplit(self.path).path == f"/repos/{REPOSITORY}/events"
                status, events = fixture.responses.pop(0)
                fixture.calls.append({"path": self.path, "status": status})
                body = json.dumps(events).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    async def request(self, method, url, *, headers, auth_secret):
        parsed = urlsplit(url)
        assert (method, parsed.scheme, parsed.hostname, auth_secret) == ("GET", "https", "api.github.com", None)
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, f"{parsed.path}?{parsed.query}", headers=headers)
            response = connection.getresponse()
            data = {"status_code": response.status, "headers": dict(response.getheaders()),
                    "body": response.read().decode()}
            if response.status != 200:
                return PluginResult(ok=False, error_code="http_error", data=data)
            return PluginResult(data=data)
        finally:
            connection.close()


class Publications:
    def __init__(self, repository, plugin_id):
        self.repository = repository
        self.plugin_id = plugin_id
        self.calls = []

    async def publish(self, request):
        item = {"request": request.model_dump(mode="json")}
        self.calls.append(item)
        try:
            receipt = await self.repository.publish(plugin_id=self.plugin_id, request=request)
        except PluginPermissionError as error:
            item["denied"] = str(error)
            raise
        item["receipt"] = receipt.model_dump(mode="json")
        return receipt


async def target(session, native, presence):
    binding = await find_identity_binding(session, native)
    conversation = await ensure_canonical_conversation(
        session, kind="private", primary_scope_key=f"bot:8000:private:{native}",
        person_id=binding.person_id, identity_binding_id=binding.id, presence_id=presence.id,
    )
    return NotificationTarget(target_type="private", target_id=binding.person_id,
                              conversation_id=conversation.conversation_id)


@pytest.mark.asyncio
async def test_original_monitor_target_and_outage(database):
    source = Path(__file__).resolve().parents[2]
    monitor = source.parent / "github-monitor"
    output = Path(os.environ["YUKI_MONITOR_REPLAY_OUT"])
    manifest = load_manifest(monitor, yuki_version="4.0.0")
    assert manifest.plugin_api == "9.0" and manifest.id == "github-monitor"
    now = datetime.now(UTC)
    async with database.immediate_session() as session:
        presence = await find_presence(session, "8000")
        allowed = await target(session, "1001", presence)
        other = await target(session, "1002", presence)
        presence_id = presence.id
        session.add(PluginInstallationModel(
            plugin_id=manifest.id, name=manifest.name, version=manifest.version,
            plugin_api=manifest.plugin_api, yuki_requires=manifest.yuki_requires,
            manifest_hash=manifest.manifest_hash, entrypoint=manifest.entrypoint,
            status="running", enabled=True, discovered_at=now, updated_at=now,
        ))
    repository = PluginNotificationRepository(database)
    for selected in [allowed, other]:
        await repository.grant_target(plugin_id=manifest.id, target=selected, bot_user_id="8000",
                                      created_by_user_id=allowed.target_id, presence_id=presence_id)
    granted = Publications(repository, manifest.id)
    context = FakePluginContext(manifest.id)
    context.notifications = granted
    config = GitHubMonitorConfig(coalesce=False, repositories=(RepositorySubscription(
        repository=REPOSITORY,
        targets=tuple(NotificationTargetConfig(**item.model_dump(), send_card=False, ask_agent=False)
                      for item in [allowed, other]),
    ),))
    for key, value in config.model_dump(mode="json").items():
        await context.config.set(key, value)
    observation = PluginObservationContext(context.config.get, context.storage.get)
    loader = PluginLoader()
    loaded = loader.load(monitor, manifest)
    await loaded.instance.start(context)
    try:
        start = (await loaded.instance.observe(observation, PluginObservationRequest()))["repositories"][0]
        assert start["queue_available"] is False and "pending_count" not in start
        with GitHubFixture() as http:
            context.http = http
            poller = GitHubPoller(context, asyncio.Event())
            http.responses.append((200, [BASE]))
            assert await poller.poll_repository(config.repositories[0], config)
            assert len(granted.calls) == 2
            assert all(item["request"]["event_type"] == "monitor_enabled" for item in granted.calls)
            await repository.revoke_target(plugin_id=manifest.id, target=other)
            http.responses.append((200, [UPDATE, BASE]))
            with pytest.raises(PluginPermissionError, match="target is not granted"):
                await poller.poll_repository(config.repositories[0], config)
            normal, denied = granted.calls[2:]
            assert normal["request"]["event_key"] == denied["request"]["event_key"]
            assert normal["request"]["target"]["target_id"] == allowed.target_id
            assert denied["request"]["target"]["target_id"] == other.target_id
            assert normal["request"]["payload"]["details"]["excerpt"] == EXCERPT
            assert normal["request"]["payload"]["content_trust"] == "external_untrusted"
            assert EXCERPT not in normal["request"]["text"]
            assert normal["receipt"]["event_created"] and normal["receipt"]["delivery_enqueued"]
            assert not normal["receipt"]["agent_turn_enqueued"] and "receipt" not in denied
            blocked = (await loaded.instance.observe(observation, PluginObservationRequest()))["repositories"][0]
            assert blocked["accepted_cursor"] == "101" and blocked["committed_cursor"] == "100"
            assert {item["status"] for item in blocked["inflight"]["deliveries"]} == {"completed", "attempting"}
            await repository.grant_target(plugin_id=manifest.id, target=other, bot_user_id="8000",
                                          created_by_user_id=allowed.target_id, presence_id=presence_id)
            assert await poller.poll_repository(config.repositories[0], config)
            assert len(granted.calls) == 5 and granted.calls[4]["request"] == denied["request"]
            assert granted.calls[4]["receipt"]["event_created"]
            assert granted.calls[4]["receipt"]["source_event_id"] != normal["receipt"]["source_event_id"]
            complete = (await loaded.instance.observe(observation, PluginObservationRequest()))["repositories"][0]
            assert complete["accepted_cursor"] == complete["committed_cursor"] == "101"
            assert complete["inflight"] is None
            http.responses.append((503, {"message": "recorded fixture outage"}))
            assert not await poller.poll_repository(config.repositories[0], config)
            outage = (await loaded.instance.observe(observation, PluginObservationRequest()))["repositories"][0]
            assert outage["consecutive_failures"] == 1 and outage["last_success_at"] == complete["last_success_at"]
            assert outage["committed_cursor"] == "101" and outage["paused_until"] is not None
            assert len(granted.calls) == 5 and not http.responses
            async with database.read_session() as session:
                events = (await session.scalars(select(ChatEventModel).where(
                    ChatEventModel.event_kind == "external_event").order_by(ChatEventModel.id))).all()
                assert len(events) == 4
                assert len((await session.scalars(select(PluginBackgroundTurnJobModel))).all()) == 0
                assert events[-2].canonical_conversation_id == allowed.conversation_id
                assert events[-1].canonical_conversation_id == other.conversation_id
            result = {"status": "PASS", "baseline": "329ca7c487414d2f54ddd98ff4727446ed2446cd",
                      "monitor": "efba5e1ad77f52364c13702c342ab6b937c86c1e",
                      "manifest_sha256": sha256((monitor / "plugin.toml").read_bytes()).hexdigest(),
                      "http": http.calls, "publication": granted.calls, "observation": {
                          "empty": start, "target_revoked": blocked, "reconciled": complete, "http_failure": outage},
                      "original_external_events": [row.id for row in events], "original_main_jobs": 0}
            output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    finally:
        await loaded.instance.stop()
        loader.unload(loaded)
