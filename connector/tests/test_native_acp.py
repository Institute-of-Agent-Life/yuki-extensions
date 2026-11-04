import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from yuki_agent_connector.config import Instance
from yuki_agent_connector.drivers import DriverError, acp


@pytest.mark.parametrize("mode", ["absent", "reject", "supported"])
async def test_negotiated_load_and_targeted_control(tmp_path, monkeypatch, mode, record_property):
    script = Path(__file__).parent / "peers/acp/native_v1.py"
    args = [str(script), "argument with space", ""]
    events = []
    permission = asyncio.Event()
    processes = []
    spawn = acp.spawn_agent_process

    @asynccontextmanager
    async def observed(*arguments, **options):
        async with spawn(*arguments, **options) as pair:
            processes.append(pair[1])
            yield pair

    monkeypatch.setattr(acp, "spawn_agent_process", observed)

    async def emit(kind, value):
        events.append({"kind": kind, **value})
        if kind == "permission":
            permission.set()

    driver = acp.ACPDriver(Instance("original", "acp", "peer", sys.executable, args=args,
        cwd=str(tmp_path), env={"PEER_LOAD_MODE": mode}), emit)
    await asyncio.wait_for(driver.start(), 8)
    prompt = {"id": "load-original", "action": "prompt", "session_id": "stored",
              "arguments": {"resume": True, "prompt": "original run"}}
    receipts = {}
    try:
        if mode != "supported":
            with pytest.raises(DriverError) as refused:
                await driver.execute(prompt)
            receipts["refused"] = refused.value.code
            expected = "unsupported_action" if mode == "absent" else "native_session_error"
            assert refused.value.code == expected
            assert not refused.value.uncertain and not driver.sessions
        else:
            first = await asyncio.wait_for(driver.execute(prompt), 6)
            second = await asyncio.wait_for(driver.execute({
                "action": "prompt", "id": "start-second", "arguments": {"prompt": "second run"},
            }), 6)
            assert first["session_id"] == "stored" and second["session_id"] == "second"
            await asyncio.wait_for(permission.wait(), 6)
            q = next(e for e in events if e["kind"] == "permission")
            receipts["answer"] = await driver.execute({
                "id": "answer", "action": "respond", "session_id": "second",
                "execution_id": second["execution_id"], "arguments": {
                    "connection_id": driver.owner,
                    "permission_id": q["payload"]["native_request_id"], "option_id": "once",
                },
            })
            cancel = {"id": "cancel", "action": "cancel", "session_id": "stored",
                      "execution_id": second["execution_id"], "arguments": {}}
            with pytest.raises(DriverError) as wrong:
                await driver.execute(cancel)
            assert wrong.value.code == "execution_mismatch"
            cancel["execution_id"] = first["execution_id"]
            receipts["cancel"] = await driver.execute(cancel)
            await asyncio.wait_for(driver.sessions["stored"].task, 6)
            assert driver.sessions["stored"].status == "cancelled"
            assert not driver.sessions["second"].task.done()
            (tmp_path / "exit-now").touch()
            listed = await asyncio.wait_for(driver.execute({"id": "list", "action": "list"}), 6)
            assert listed["sessions"][0]["id"] == "stored"
            await asyncio.wait_for(driver.worker, 6)
            assert processes[0].returncode == 23
            assert driver.sessions["second"].status == "unknown"
            assert any(e.get("status") == "unavailable" for e in events)
            receipts.update({"first": first, "second": second})
    finally:
        await asyncio.wait_for(driver.stop(), 6)

    trace = [json.loads(line) for line in (tmp_path / "native.jsonl").read_text().splitlines()]
    assert trace[0]["argv"] == args[1:] and Path(trace[0]["cwd"]) == tmp_path
    calls = [e["from_driver"] for e in trace if "from_driver" in e]
    methods = [call.get("method") for call in calls]
    if mode == "supported":
        assert methods.count("session/new") == methods.count("session/load") == 1
        assert methods.count("session/prompt") == 2
        assert [c["params"]["sessionId"] for c in calls if c.get("method") == "session/cancel"
                ] == ["stored"]
        reply, = [c for c in calls if c.get("id") == 100000]
        assert reply["result"]["outcome"]["optionId"] == "once"
    else:
        assert methods.count("session/load") == (mode == "reject")
        assert "session/new" not in methods and "session/prompt" not in methods
    assert processes[0].returncode is not None
    record_property("witness", {"mode": mode, "trace": trace, "receipts": receipts,
                                "events": events, "exit_code": processes[0].returncode})
