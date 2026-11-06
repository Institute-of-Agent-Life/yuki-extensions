"""Private codec adapter for the Rust plugin; the original native worker runs the VM.

No Host identity, budget, persistence, permissions or business dispatch is implemented here.
"""
import asyncio
import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

from yuki_monty_backend.driver_types import EngineAnswer, HostCounters
from yuki_monty_backend.engine_monty import MontyEngine, PinnedWorker
from yuki_monty_backend.limits import CodeModeLimits
from yuki_monty_backend.snapshot_binding import call_digest
from make_contract import build_contract


ROOT = Path("/opt/yuki-monty")
MAX_FRAME = 20 * 1024 * 1024


def emit(value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    if len(data) > MAX_FRAME:
        raise ValueError("codec_frame_too_large")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def answer(value):
    if value["kind"] == "future":
        return EngineAnswer.future()
    if value["kind"] == "error":
        return EngineAnswer.error(value["message"], value.get("error_type", "RuntimeError"))
    if value["kind"] == "value":
        return EngineAnswer.ok(value["value"])
    raise ValueError("codec_answer_invalid")


def result(run, outcome):
    record = {"outcome": asdict(outcome), "counters": run.counters.as_dict()}
    if outcome.status == "suspended":
        snapshot = run.dump()
        call = outcome.call
        record.update(
            snapshot=base64.b64encode(snapshot).decode(),
            snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
            saved={
                "kind": call.kind,
                "feed_index": call.feed_index,
                "engine_call_id": call.engine_call_id,
                "function_name": call.function_name,
                "args_digest": call_digest(call),
                "pending_call_ids": sorted(call.pending_call_ids),
            },
        )
    return record


async def main():
    if sys.version_info[:2] != (3, 12):
        raise ValueError("codec_python_abi_mismatch")
    artifacts = json.loads((ROOT / "artifacts.json").read_text())
    worker = PinnedWorker(
        ROOT / "monty", artifacts["worker"]["sha256"],
        ROOT / "monty-isolated", artifacts["launcher"]["sha256"],
    )
    limits = CodeModeLimits()
    contract = json.loads((ROOT / "runtime-contract.json").read_text())
    if contract != build_contract():
        raise ValueError("codec_contract_digest_mismatch")
    reader = asyncio.StreamReader(limit=MAX_FRAME + 1)
    transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer
    )
    requests = asyncio.Queue(maxsize=1)
    disconnected = asyncio.Event()

    async def read_requests():
        try:
            while raw := await reader.readline():
                if len(raw) > MAX_FRAME or not raw.endswith(b"\n"):
                    raise ValueError("codec_frame_too_large_or_truncated")
                await requests.put(json.loads(raw))
        finally:
            disconnected.set()

    receiver = asyncio.create_task(read_requests())
    closed = asyncio.create_task(disconnected.wait())
    active = None
    async with MontyEngine(worker, limits) as engine:
        run = None
        emit({"ready": True, "contract": contract})

        async def advance(request):
            nonlocal run
            operation = request["op"]
            if operation in ("start", "restore"):
                if run is not None:
                    raise ValueError("codec_run_already_started")
                manifest = request["manifest"]
                if not isinstance(manifest, list) or any(not isinstance(x, str) for x in manifest):
                    raise ValueError("codec_manifest_invalid")
                run = engine.run(frozenset(manifest))
                if operation == "start":
                    outcome = await run.start(request["code"], request.get("inputs", {}))
                else:
                    dump = base64.b64decode(request["snapshot"], validate=True)
                    if hashlib.sha256(dump).hexdigest() != request["snapshot_sha256"]:
                        raise ValueError("codec_snapshot_digest_mismatch")
                    outcome = await run.restore(dump, request["saved"], HostCounters.from_dict(request["counters"]))
            elif operation == "answer" and run is not None:
                outcome = await run.answer(request["engine_call_id"], answer(request["answer"]))
            elif operation == "settle" and run is not None:
                outcome = await run.settle({int(k): answer(v) for k, v in request["answers"].items()})
            else:
                raise ValueError("codec_operation_invalid")
            return result(run, outcome)

        try:
            while not disconnected.is_set():
                active = asyncio.create_task(requests.get())
                await asyncio.wait((active, closed), return_when=asyncio.FIRST_COMPLETED)
                if closed.done():
                    break
                request = await active
                active = asyncio.create_task(advance(request))
                await asyncio.wait((active, closed), return_when=asyncio.FIRST_COMPLETED)
                if closed.done():
                    break
                emit(await active)
            if receiver.done() and not receiver.cancelled() and receiver.exception():
                raise receiver.exception()
        finally:
            if active is not None:
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
            if run is not None:
                await run.terminate()
            receiver.cancel()
            closed.cancel()
            await asyncio.gather(receiver, closed, return_exceptions=True)
            transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        emit({"error": type(error).__name__, "message": str(error)[:2000]})
        raise SystemExit(1)
