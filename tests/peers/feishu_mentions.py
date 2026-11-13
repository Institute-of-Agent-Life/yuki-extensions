"""Check source-bound native mentions through the real gateway and original receipts."""

import base64
import hashlib
import html
import json

SCENARIOS = [
    "mention-group",
    "mention-private",
    "mention-topic",
    "mention-exact",
    "mention-xml",
    "mention-long-name",
    "mention-literal",
    "mention-parts",
    "mention-lost",
    "mention-rejected",
    "mention-caption",
]


class Mentions:
    def __init__(self, scenario):
        self.scenario = scenario
        self.label = (
            "雪<&\"'"
            if scenario in {"mention-xml", "mention-caption"}
            else "雪" * 128 if scenario == "mention-long-name" else "小雪"
        )
        self.text = "原文 @" + self.label + " 完成"
        self.rendered = self.text.replace(
            "@" + self.label,
            '<at user_id="ou_original">' + html.escape("@" + self.label) + "</at>",
        )
        if scenario in {"mention-parts", "mention-lost", "mention-rejected"}:
            self.text = ("@" + self.label + " ") * 11000
            self.rendered = ('<at user_id="ou_original">@小雪</at> ') * 11000
        if scenario == "mention-literal":
            self.text = (
                r"\@小雪 @未知 https://example.test/@小雪 user@example.test @小雪"
            )
            self.rendered = '@小雪 @未知 https://example.test/@小雪 user@example.test <at user_id="ou_original">@小雪</at>'

    def account(self, original):
        if self.scenario == "mention-exact":
            self.text = "原文 @{account:" + original["account"] + "} 完成"

    def event(self, packet):
        message = packet["event"]["message"]
        message["content"] = json.dumps(
            {"text": "@_user_1 @_user_2 send original text"}
        )
        message["mentions"].append(
            {"key": "@_user_2", "id": {"open_id": "ou_original"}, "name": self.label}
        )

    @property
    def expected(self):
        return {"mention-lost": "unknown", "mention-rejected": "failed"}.get(
            self.scenario, "confirmed"
        )

    def verify(self, result, native, frames):
        assert result["state"] == self.expected
        visible = [
            row for row in native if row.get("body", {}).get("msg_type") == "text"
        ]
        received = "".join(
            json.loads(row["body"]["content"])["text"] for row in visible
        )
        if self.expected == "confirmed":
            assert received == self.rendered, (len(received), len(self.rendered))
        else:
            assert len(visible) == 2 and self.rendered.startswith(received)
            assert [part["state"] for part in result["result"]["parts"]] == [
                "confirmed",
                self.expected,
            ]
        requests = {
            row["frame"]["id"]: row["frame"]
            for row in frames
            if row["direction"] == "from_plugin"
            and row["frame"].get("method") == "gateway.read_mentions"
        }
        assert requests, "consumer never read the original annotations"
        replies = {
            row["frame"]["id"]: row["frame"]["result"]
            for row in frames
            if row["direction"] == "from_host"
            and row["frame"].get("id") in requests
            and "result" in row["frame"]
        }
        streams = {}
        for ident, request in requests.items():
            page = replies[ident]
            handle = request["params"]["handle"]
            stream = streams.setdefault(handle, bytearray())
            assert page["offset"] == request["params"]["offset"] == len(stream)
            piece = base64.b64decode(page["bytes"], validate=True)
            assert 0 < len(piece) <= 12288
            stream.extend(piece)
            if page["done"]:
                assert len(stream) == page["total"]
                assert hashlib.sha256(stream).hexdigest() == page["sha256"]
                annotations = json.loads(stream)
                assert annotations and all(
                    m["native"] == "ou_original" for m in annotations
                )
        return {
            "annotation_pages": len(requests),
            "original_handles": len(streams),
            "native_text_sha256": hashlib.sha256(received.encode()).hexdigest(),
        }


def annotation_pages(send, read, app):
    """Forget both sequential readers and reject malformed original annotations."""
    text = "@小雪 " * 200
    content = text.encode()
    annotations = [
        {
            "start": index * 8,
            "end": index * 8 + 7,
            "account": "original-account",
            "native": "ou_original",
            "label": "小雪",
            "assignment": "original-stage",
            "source": 12,
        }
        for index in range(200)
    ]
    original = json.dumps(
        annotations, ensure_ascii=False, separators=(",", ":")
    ).encode()

    def descriptor(data):
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def plan(ident, data=original, bot=app):
        send(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "gateway.plan_send",
                "params": {
                    "handle": "handle-" + ident,
                    "arguments": {
                        "route": {
                            "bot": bot,
                            "chat": "oc_original",
                            "scope": "group",
                            "topic": None,
                        },
                        "message": {},
                        "text_source": descriptor(content),
                        "mentions_source": descriptor(data),
                    },
                },
            }
        )

    def page(request, data=None, change=None):
        assert request["method"] in {"gateway.read_text", "gateway.read_mentions"}
        if data is None:
            data = content if request["method"] == "gateway.read_text" else original
        offset = request["params"]["offset"]
        assert request["params"]["length"] == 12288
        piece = data[offset : offset + 12288]
        value = {
            "offset": offset,
            "total": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": base64.b64encode(piece).decode(),
            "done": offset + len(piece) == len(data),
        }
        value.update(change or {})
        send({"jsonrpc": "2.0", "id": request["id"], "result": value})

    plan("forgotten-mentions")
    text_request = read()
    assert text_request["method"] == "gateway.read_text"
    page(text_request)
    old = read()
    assert old["method"] == "gateway.read_mentions" and old["params"]["offset"] == 0
    send(
        {
            "jsonrpc": "2.0",
            "id": "forget-mentions",
            "method": "forget.request",
            "params": {"key": "original-mentions", "watermark": 19, "sources": [12]},
        }
    )
    cancelled, forgotten = read(), read()
    assert cancelled["id"] == "forgotten-mentions" and "error" in cancelled
    assert (
        forgotten["id"] == "forget-mentions" and forgotten["result"]["watermark"] == 19
    )
    plan("fresh-mentions")
    fresh = read()
    page(old)
    page(fresh)
    pages = 0
    while True:
        frame = read()
        if frame.get("method") == "gateway.read_mentions":
            assert frame["params"]["offset"] == pages * 12288
            assert frame["params"]["handle"] == "handle-fresh-mentions"
            page(frame)
            pages += 1
        else:
            assert frame["id"] == "fresh-mentions" and "result" in frame
            assert frame["result"]["parts"] == [
                {
                    "text_range": {
                        "start": 0,
                        "length": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                }
            ]
            break
    assert pages > 1
    faults = ["digest", "offset", "overlap", "outside", "wrong-app"]
    for fault in faults:
        invalid = json.loads(original)
        if fault == "overlap":
            invalid[1]["start"] = 1
        if fault == "outside":
            invalid[-1]["end"] = len(content) + 1
        data = json.dumps(invalid, ensure_ascii=False, separators=(",", ":")).encode()
        plan(fault, data, "foreign" if fault == "wrong-app" else app)
        page(read())
        while True:
            frame = read()
            if frame.get("method") == "gateway.read_mentions":
                change = (
                    {"sha256": "0" * 64}
                    if fault == "digest"
                    else {"offset": 1} if fault == "offset" else None
                )
                page(frame, data, change)
            else:
                assert frame["id"] == fault and "error" in frame, frame
                break
    return {
        "status": "PASS",
        "pages": pages,
        "faults": faults,
        "sequential_readers": ["text", "mentions"],
        "forget_cancelled": True,
        "late_original_page_ignored": True,
        "native_effects": 0,
    }
