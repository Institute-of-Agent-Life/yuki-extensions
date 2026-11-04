import asyncio
import hashlib
import json
import sys
from importlib.metadata import version

import pytest
from claude_agent_sdk import ClaudeSDKClient
from test_claude_driver import NativeTransport

from yuki_agent_connector.config import Instance
from yuki_agent_connector.drivers import DriverError, claude


async def test_explicit_resume_question_and_owner_eof(tmp_path, monkeypatch, record_property):
    identity = "00000000-0000-4000-8000-000000000003"
    profile = tmp_path / "profile"
    project = tmp_path / "original project"
    project.mkdir()
    history = profile / "projects" / "fixture"
    history.mkdir(parents=True)
    session_file = history / f"{identity}.jsonl"
    session_file.write_text(json.dumps({"customTitle": "fixture", "cwd": str(project)}) + "\n")
    canary = "fixture-private-data-never-transmit"
    for private in [profile / ".credentials.json", project / ".env"]:
        private.write_text(canary)

    transport = NativeTransport()
    options_used = []
    events = []
    question = asyncio.Event()
    effect = project / "peer-result.txt"

    def client(*, options):
        options_used.append(options)
        return ClaudeSDKClient(options=options, transport=transport)

    async def emit(kind, payload):
        events.append({"kind": kind, **payload})
        if kind == "question":
            question.set()

    monkeypatch.setattr(claude, "ClaudeSDKClient", client)
    driver = claude.ClaudeDriver(Instance("original", "claude", "fixture", sys.executable,
        cwd=str(tmp_path), env={"CLAUDE_CONFIG_DIR": str(profile)}), emit)
    await driver.start()
    command = {"id": "original-op", "action": "prompt", "session_id": identity,
               "arguments": {"prompt": "fixture work"}}
    try:
        listed = await driver.execute({"id": "read", "action": "list", "arguments": {}})
        entry, = listed["sessions"]
        assert entry["id"] == identity and entry["live_attach"] is False
        with pytest.raises(DriverError) as denied:
            await driver.execute(command)
        assert denied.value.code == "explicit_resume_required" and not options_used
        command["arguments"]["resume"] = True
        started = await asyncio.wait_for(driver.execute(command), 8)
        options, = options_used
        assert options.resume == identity and options.cwd == str(project)
        assert options.cli_path == sys.executable
        await transport.incoming.put({
            "type": "control_request", "request_id": "native-control", "request": {
                "subtype": "can_use_tool", "tool_name": "AskUserQuestion",
                "tool_use_id": "native-question", "input": {"questions": [{"question": "Go?"}]},
            },
        })
        await asyncio.wait_for(question.wait(), 5)
        arguments = {"connection_id": events[-1]["payload"]["connection_id"],
                     "permission_id": "other-question",
                     "response": {"behavior": "allow", "answers": {"Go?": "yes"}}}
        answer = {"id": "answer", "action": "respond", "session_id": identity,
                  "execution_id": started["execution_id"], "arguments": arguments}
        with pytest.raises(DriverError) as wrong:
            await driver.execute(answer)
        assert wrong.value.code == "request_resolved" and not transport.response.is_set()
        arguments["permission_id"] = "native-question"
        accepted = await driver.execute(answer)
        assert accepted["response_submitted"]
        await asyncio.wait_for(transport.response.wait(), 5)
        reply, = (m for m in transport.writes if m["type"] == "control_response")
        assert reply["response"]["request_id"] == "native-control"
        assert reply["response"]["response"]["updatedInput"]["answers"] == {"Go?": "yes"}
        # Native peer makes its local effect before the stream drops.
        effect.write_bytes(b"native peer output")
        await transport.incoming.put(None)
        await asyncio.wait_for(driver.sessions[identity].task, 8)
        assert any(e["payload"].get("reason") == "native_sdk_connection_lost"
                   and e["payload"]["status"] == "unknown" for e in events)
    finally:
        await driver.stop()
    assert transport.closed and effect.read_bytes() == b"native peer output"
    assert len([m for m in transport.writes if m["type"] == "user"]) == 1
    assert canary not in json.dumps([events, transport.writes, listed])
    record_property("witness", {
        "sdk": version("claude-agent-sdk"), "cli_path": options.cli_path,
        "original_session": identity, "original_cwd": options.cwd, "instance": driver.spec.id,
        "readonly_entry": entry, "denied_implicit_attach": denied.value.code,
        "wrong_question": wrong.value.code, "correct_answer": accepted,
        "writes": transport.writes, "events": events, "closed": transport.closed,
        "retained_file_sha256": hashlib.sha256(effect.read_bytes()).hexdigest(),
        "private_canaries_checked": [".credentials.json", ".env"],
    })
