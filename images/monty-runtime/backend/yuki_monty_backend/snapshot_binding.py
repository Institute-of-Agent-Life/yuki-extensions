"""Original pure snapshot boundary matching; storage remains with the public Host."""
from __future__ import annotations
import hashlib
import json
from typing import Any
from yuki_monty_backend.driver_types import EngineCall

def call_digest(call: EngineCall) -> str:
    """Matches a re-announced call to the saved boundary; never a business identity."""
    encoded = json.dumps(
        [call.function_name, list(call.args), call.kwargs],
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def matches_saved(saved: dict[str, Any], announced: EngineCall) -> bool:
    if saved.get("kind") != announced.kind:
        return False
    if announced.kind == "future":
        return sorted(saved.get("pending_call_ids", ())) == sorted(announced.pending_call_ids)
    return (
        saved.get("engine_call_id") == announced.engine_call_id
        and saved.get("function_name") == announced.function_name
        and saved.get("args_digest") == call_digest(announced)
    )


