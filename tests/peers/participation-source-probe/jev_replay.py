"""A disposable SDK peer for the pinned participation library."""

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx
from yuki_participation.models import EventMention, Scope, ScopedEvent, Snapshot, SourceRef
from yuki_participation.observer import JevObserver
from yuki_plugin_sdk.connection import Binding, Peer, encode, read_frame
from yuki_plugin_sdk.host import Calls


class Session:
    def __init__(self):
        binding = Binding.from_json(json.loads(os.environ["YUKI_PLUGIN_BINDING"]))
        peer = Peer(binding)
        self.write(peer.request(1, binding.offer()))
        raw = read_frame(sys.stdin.buffer)
        peer.receive(raw)
        self.calls = Calls(json.loads(raw)["result"])
        self.next_id = 1
        self.events = []
        self.wire = []

    @staticmethod
    def write(frame):
        sys.stdout.buffer.write(encode(frame))
        sys.stdout.buffer.flush()

    def receive(self):
        raw = read_frame(sys.stdin.buffer)
        if raw is None:
            return None
        frame = json.loads(raw)
        kind, method, payload = self.calls.receive(frame)
        if kind == "notification" and method == "observer.event":
            self.events.append(payload)
        return kind, method, payload

    def request(self, method, params):
        self.next_id += 1
        self.write(self.calls.request(self.next_id, method, params))
        while (frame := self.receive()) is not None:
            kind, name, response = frame
            if kind == "response":
                if name != method or response["id"] != self.next_id:
                    raise RuntimeError("unmatched Host receipt")
                self.wire.append({"method": method, "params": params, "response": response})
                if "result" not in response:
                    raise RuntimeError(str(response["error"]))
                return response["result"]
        raise RuntimeError("Host closed during the replay")


def hydrate(session, event):
    params = {"event": event, "include_origin": True, "include_reply": True, "mention_cursor": 0}
    first = session.request("participation.source", params)
    origin = first["origin"]
    raw = base64.b64decode(first["data"])
    page = first
    while not page["complete"]:
        page = session.request("participation.source",
                               {"event": event, "version": first["version"], "cursor": page["next"]})
        raw += base64.b64decode(page["data"])
    if hashlib.sha256(raw).hexdigest() != first["version"]:
        raise ValueError("original event hash changed")

    mentions = first["mentions"]["items"]
    page = first["mentions"]
    while not page["complete"]:
        response = session.request("participation.source", {
            "event": event, "version": first["version"], "cursor": first["size"],
            "mention_cursor": page["next"],
        })
        page = response["mentions"]
        mentions.extend(page["items"])
    frame = json.loads(raw)
    return origin, first["reply_to"], frame, tuple(EventMention.model_validate(row) for row in mentions)


def scoped(origin, frame, mentions, event, reply=None):
    # Each immutable fixture event is read for the first time. Live version
    # ordinals and admitted units belong to the production plugin checkpoint.
    ref = SourceRef(event_id=f"event:{event}", revision=1)
    return ScopedEvent(
        scope=Scope(conversation_id=origin["entry"], generation=origin["observed_generation"]),
        ref=ref, thread=reply.event_id if reply else ref.event_id,
        author=origin["original_person"], target=origin["original_person"],
        text=frame.get("text") or "".join(
            segment["text"] for segment in frame["segments"] if segment["type"] == "text"
        ),
        at=(frame["occurred"] or frame["observed"]) / 1000,
        mentions=mentions, reply_to=reply, source_order=event,
    )


async def exercise(session, event, config):
    origin, anchor, frame, mentions = hydrate(session, event)
    if anchor is None:
        raise ValueError("fixture has no authorized original reply")
    ancestor = anchor["event"]
    past_origin, _, past_frame, past_mentions = hydrate(session, ancestor)
    earlier = scoped(past_origin, past_frame, past_mentions, ancestor)
    focus = scoped(origin, frame, mentions, event, earlier.ref)
    if origin["entry"] != config["entry"] or len(focus.mentions) != 5:
        raise ValueError("fixture mentions or entry mismatch")
    snapshot = Snapshot(scope=focus.scope, focus=focus, context=(earlier,), sequence=1, issued_at=focus.at)
    observations = []
    receipts = []

    def through_host(request):
        native = json.loads(request.content)
        if native.pop("model") != "jev-request-fixture":
            raise ValueError("pinned library selected the wrong request model")
        params = {"origin": {"event": event}, "sources": [ancestor], "route": "review",
                  "purpose": "review", "call_id": "original-native-review", "jev": native}
        receipt = session.request("llm.complete", params)
        if receipt["state"] != "response" or receipt["erased"]:
            raise ValueError("original response unavailable")
        receipts.append(receipt)
        payload = bytearray()
        offset = 0
        while offset is not None:
            page = session.request("llm.result", {"request": receipt["request"], "offset": offset, "limit": 97})
            payload.extend(base64.b64decode(page["bytes"]))
            offset = page["next_offset"]
        if hashlib.sha256(payload).hexdigest() != page["sha256"]:
            raise ValueError("Jev result changed during paging")
        return httpx.Response(200, content=bytes(payload))

    async with httpx.AsyncClient(transport=httpx.MockTransport(through_host), trust_env=False) as client:
        observer = JevObserver(
            "unused-by-local-transport", identity=lambda: {"display_name": "Yuki", "aliases": ()},
            endpoint="http://127.0.0.1/systemone", request_model="jev-request-fixture",
            response_model="jev-response-fixture", client=client,
        )
        for _ in range(2):
            result = await observer.evaluate(snapshot)
            observations.append({
                "model": result.model_revision, "rubric": result.rubric_revision,
                "answers": {key: value.choice for key, value in result.answers.items()},
                "invalid": result.invalid_dimensions, "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            })
    if receipts[0] != receipts[1] or observations[0] != observations[1]:
        raise ValueError("same-key review changed")
    return {
        "event": event, "origin": origin, "anchor": anchor,
        "focus": focus.model_dump(mode="json"), "receipt": receipts[0],
        "observations": observations, "wire": session.wire,
    }


def main():
    folder = Path(sys.argv[1])
    config = json.loads((folder / "config.json").read_bytes())
    session = Session()
    while session.receive() is not None:
        if not session.events:
            continue
        notice = session.events.pop(0)
        if notice["entry"] != config["entry"] or notice["kind"] != "message":
            continue
        event = notice["event"]
        page = session.request("participation.source", {"event": event, "include_reply": True})
        if page["reply_to"] is None:
            continue
        outcome = asyncio.run(exercise(session, event, config))
        pending = folder / "result.tmp"
        pending.write_text(json.dumps(outcome, indent=2, ensure_ascii=False), encoding="utf-8")
        pending.replace(folder / "result.json")
        break
    # Keep the SDK connection alive until the test owner shuts down.
    for _ in iter(lambda: read_frame(sys.stdin.buffer), None):
        pass


if __name__ == "__main__":
    main()
