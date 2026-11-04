from __future__ import annotations

import asyncio
import json

import pytest
from test_codex_driver import command
from websockets.asyncio.server import serve

from yuki_agent_connector.config import Instance
from yuki_agent_connector.drivers import DriverError
from yuki_agent_connector.drivers.codex import CodexDriver


@pytest.mark.parametrize("fault", ["unsupported_queue", "lost_prompt_reply"])
async def test_original_owner_fault(fault):
    calls = []
    events = []
    connected = asyncio.Event()
    original = None

    async def emit(kind, value):
        events.append((kind, value))
        if kind == "connection" and value["status"] == "available":
            connected.set()

    async def peer(socket):
        nonlocal original
        async for raw in socket:
            call = json.loads(raw)
            calls.append(call)
            if "id" not in call:
                continue
            method = call["method"]
            response = {"id": call["id"], "result": {}}
            if method == "thread/queue/add":
                response = {"id": call["id"], "error": {"code": -32601, "message": "No queue"}}
            elif method in {"thread/read", "thread/resume"}:
                response["result"] = {"thread": {"id": "thread", "status": {"type": "idle"}}}
            elif method == "turn/start":
                original = call["params"]["clientUserMessageId"]
                await socket.close()
                return
            elif method == "thread/turns/list":
                response["result"] = {"data": [{
                    "id": "original-turn", "status": "completed",
                    "items": [{"type": "userMessage", "clientId": original}],
                }]}
            await socket.send(json.dumps(response))

    async with serve(peer, "127.0.0.1", 0) as server:
        endpoint = f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"
        driver = CodexDriver(Instance("original-device", "codex", "native", "unused",
                                      endpoint=endpoint), emit)
        await driver.start()
        try:
            if fault == "unsupported_queue":
                with pytest.raises(DriverError) as error:
                    await driver.execute(command("queue", identity="queued-once", prompt="later"))
                assert error.value.code == "unsupported_action" and not error.value.uncertain
                assert error.value.details["code"] == -32601
                assert "queued-once" not in driver.queue_operations
                assert "queued-once" not in driver.queue_sessions
                assert [c["method"] for c in calls].count("thread/queue/add") == 1
                assert not any(c["method"] == "turn/start" for c in calls)
            else:
                prompt = command("prompt", identity="prompt-once", prompt="fixture request")
                with pytest.raises(DriverError) as error:
                    await driver.execute(prompt)
                assert error.value.uncertain and original == "prompt-once"
                await asyncio.wait_for(connected.wait(), 8)
                await driver.recover(prompt, {"status": "unknown"})
                completion = next(value for kind, value in events if kind == "completed")
                assert completion["execution_id"] == "original-turn"
                assert completion["operation_id"] == original
                assert completion["session_id"] == "thread"
                methods = [call["method"] for call in calls]
                assert methods.count("turn/start") == 1 and methods[-1] == "thread/turns/list"
        finally:
            await driver.stop()
