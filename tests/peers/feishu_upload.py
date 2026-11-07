"""Original binary uploads and dependent visible effects, using native loopback REST."""

from email import policy
from email.parser import BytesParser
import hashlib
import json
import struct
import zlib

SCENARIOS = [
    "upload-file",
    "upload-image",
    "upload-private",
    "upload-reply",
    "upload-reply-only",
    "upload-long-caption",
    "upload-caption-rejected",
    "upload-caption-lost",
    "upload-file-rejected",
    "upload-file-lost",
    "upload-lost",
    "upload-missing",
    "upload-rejected",
    "upload-token-rejected",
    "upload-token-recovered",
    "upload-denied",
]


class Upload:
    def __init__(self, scenario):
        self.scenario = scenario
        self.kind = "image" if scenario == "upload-image" else "file"
        self.payload = b"Original selected bytes\0\r\n" + bytes(range(251)) * 97
        if self.kind == "image":

            def chunk(kind, data):
                return (
                    struct.pack(">I", len(data))
                    + kind
                    + data
                    + struct.pack(">I", zlib.crc32(kind + data))
                )

            self.payload = (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(b"\0\x12\x34\x56"))
                + chunk(b"IEND", b"")
            )
        self.name = '原始 "雪".bin'
        self.caption = (
            '雪\n"\\🌨' * 21000
            if scenario == "upload-long-caption"
            else (
                ""
                if scenario in {"upload-image", "upload-reply-only"}
                else "原始附言 caption"
            )
        )
        self.selected = None

    def args(self, operator, models, person):
        prior = json.loads(
            next(
                v["content"]
                for v in reversed(models[-1]["messages"])
                if v.get("role") == "tool"
            )
        )
        self.selected = operator(
            "media",
            "snapshot",
            prior["namespace"],
            person,
            prior["id"],
            "original.bin",
            self.name,
            self.kind,
        )
        # Deliberately omit name. The original filename must survive the normal model entry point.
        return {
            "artifact_id": self.selected["artifact_id"],
            "attachment_kind": self.kind,
            **({"text": self.caption} if self.caption else {}),
        }

    def receive(self, handler, raw, native, domain, token):
        assert handler.path == "/open-apis/im/v1/" + (
            "images" if self.kind == "image" else "files"
        )
        assert handler.headers["Authorization"] == f"Bearer fixture-{domain}-{token}"
        header = (
            "Content-Type: "
            + handler.headers["Content-Type"]
            + "\r\nMIME-Version: 1.0\r\n\r\n"
        ).encode()
        form = BytesParser(policy=policy.default).parsebytes(header + raw)
        assert form.is_multipart() and not form.defects
        fields = {
            p.get_param("name", header="content-disposition"): p
            for p in form.iter_parts()
        }
        field = "image" if self.kind == "image" else "file"
        assert fields[field].get_payload(decode=True) == self.payload
        assert fields[field].get_filename() == self.name
        if self.kind == "image":
            assert set(fields) == {"image_type", "image"}
            assert fields["image_type"].get_content() == "message"
        else:
            assert set(fields) == {"file_type", "file_name", "file"}
            assert fields["file_type"].get_content() == "stream"
            assert fields["file_name"].get_payload(decode=True).decode() == self.name
        native.append(
            {
                "method": "POST",
                "path": handler.path,
                "type": "upload",
                "token": token,
                "kind": self.kind,
                "filename": self.name,
                "sha256": hashlib.sha256(self.payload).hexdigest(),
                "size": len(self.payload),
            }
        )
        if self.scenario == "upload-lost":
            handler.close_connection = True
            return
        if self.scenario in {
            "upload-rejected",
            "upload-token-rejected",
            "upload-token-recovered",
        }:
            return handler.reply(
                {
                    "code": (
                        99991663
                        if self.scenario.startswith("upload-token-")
                        else 230006
                    )
                },
                403,
            )
        return handler.reply(
            {
                "code": 0,
                "data": (
                    {}
                    if self.scenario == "upload-missing"
                    else {field + "_key": "native-original-key"}
                ),
            }
        )

    def visible(self, handler, body, native):
        assert native[0]["type"] == "upload"
        if self.scenario == "upload-token-recovered":
            assert len(native) == 2 and body["msg_type"] == "text"
            assert json.loads(body["content"]) == {"text": self.caption}
            return handler.reply({"code": 0, "data": {"message_id": "om_recovered"}})
        index = len(native) - 1
        caption_count = (
            3 if self.scenario == "upload-long-caption" else int(bool(self.caption))
        )
        if index <= caption_count:
            assert body["msg_type"] == "text"
            assert isinstance(json.loads(body["content"])["text"], str)
            if self.scenario == "upload-caption-rejected":
                return handler.reply({"code": 230006}, 403)
            if self.scenario == "upload-caption-lost":
                handler.close_connection = True
                return
        else:
            assert index == caption_count + 1 and body["msg_type"] == self.kind
            assert json.loads(body["content"]) == {
                self.kind + "_key": "native-original-key"
            }
            if self.scenario == "upload-file-rejected":
                return handler.reply({"code": 230006}, 403)
            if self.scenario == "upload-file-lost":
                handler.close_connection = True
                return
        return handler.reply(
            {"code": 0, "data": {"message_id": "om_sent_" + str(index)}}
        )

    @property
    def expected(self):
        if self.scenario.endswith(("lost", "missing")):
            return "unknown"
        if self.scenario.endswith(("rejected", "denied")):
            return "failed"
        return "confirmed"

    def verify(self, result, native, tokens, frames):
        assert result["state"] == self.expected
        if self.scenario == "upload-denied":
            assert native == tokens == []
            return
        if self.scenario == "upload-token-recovered":
            assert len(native) == len(tokens) == 2
            assert native[0]["token"] == 1 and native[1]["token"] == 2
            assert len(result["result"]["parts"]) == 1
            assert result["result"]["parts"][0]["state"] == "confirmed"
            return
        captions = (
            3 if self.scenario == "upload-long-caption" else int(bool(self.caption))
        )
        expected_count = (
            1
            if self.scenario
            in {
                "upload-lost",
                "upload-missing",
                "upload-rejected",
                "upload-token-rejected",
            }
            else (
                2
                if self.scenario in {"upload-caption-rejected", "upload-caption-lost"}
                else captions + 2
            )
        )
        assert len(native) == expected_count, (self.scenario, native)
        callbacks = [
            v["frame"]
            for v in frames
            if v["direction"] == "from_host"
            and v["frame"].get("method")
            in {"gateway.prepare_part", "gateway.dispatch_part"}
        ]
        assert len(callbacks) == expected_count
        assert callbacks[0]["method"] == "gateway.prepare_part"
        assert callbacks[0]["params"]["arguments"]["part"]["name"] == self.name
        assert len({v["params"]["handle"] for v in callbacks}) == expected_count
        receipts = result["result"]["parts"]
        assert len(receipts) == expected_count, result
        states = [receipt["state"] for receipt in receipts]
        assert states == ["confirmed"] * (expected_count - 1) + [self.expected], states
        if self.expected == "confirmed":
            assert (
                "".join(
                    json.loads(row["body"]["content"])["text"]
                    for row in native[1:]
                    if row["body"]["msg_type"] == "text"
                )
                == self.caption
            )
            assert receipts[0]["result"]["resource"] == {
                "kind": self.kind,
                "key": "native-original-key",
            }


def upload_pages(send, read, namespace, domain, app, tenant, entered, closed):
    """Drop selected bytes before forget ACK, ignore late pages, and join an active upload."""
    import base64

    payload = b"original-upload-page" * 2000
    digest = hashlib.sha256(payload).hexdigest()
    media = {"artifact_id": "original-upload-version", "version": digest}
    origin = {
        "namespace": namespace,
        "platform": domain,
        "stage": "original-stage",
        "deployment": "original-deployment",
        "identity": {"application": app, "tenant": tenant},
    }

    def prepare(ident, original=origin):
        send(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "gateway.prepare_part",
                "params": {
                    "handle": "handle-" + ident,
                    "arguments": {
                        "part_ordinal": 0,
                        "purpose": "deliver",
                        "media": media,
                        "preparation_origin": original,
                        "part": {
                            "preparation": True,
                            "kind": "file",
                            "name": "original.bin",
                            "media": media,
                        },
                    },
                },
            }
        )

    def page(frame):
        assert frame["method"] == "media.open"
        params = frame["params"]
        assert params["length"] == 16384
        offset = params["offset"]
        piece = payload[offset : offset + params["length"]]
        send(
            {
                "jsonrpc": "2.0",
                "id": frame["id"],
                "result": {
                    "offset": offset,
                    "total": len(payload),
                    "mime": "application/octet-stream",
                    "version": digest,
                    "bytes": base64.b64encode(piece).decode(),
                    "done": offset + len(piece) == len(payload),
                },
            }
        )

    def forget(ident):
        send(
            {
                "jsonrpc": "2.0",
                "id": ident,
                "method": "forget.request",
                "params": {"key": ident, "watermark": 19, "sources": [12]},
            }
        )

    for field, value in [
        ("namespace", "another"),
        ("platform", "telegram"),
        ("identity", {"application": "another", "tenant": tenant}),
    ]:
        prepare("wrong-" + field, {**origin, field: value})
        frame = read()
        assert frame["id"] == "wrong-" + field and frame["result"]["state"] == "failed"
    prepare("old-upload")
    page(read())
    old = read()
    assert old["params"]["offset"] == 16384
    forget("erase-upload-pages")
    rejected, ack = read(), read()
    assert rejected["id"] == "old-upload" and rejected["result"]["state"] == "failed"
    assert ack["id"] == "erase-upload-pages" and ack["result"]["watermark"] == 19
    prepare("fresh-upload")
    fresh = read()
    assert fresh["params"]["offset"] == 0
    page(old)
    pages = 0
    while True:
        assert (
            fresh["params"]["handle"] == "handle-fresh-upload"
            and fresh["params"]["offset"] == pages * 16384
        )
        page(fresh)
        pages += 1
        if pages * 16384 >= len(payload):
            break
        fresh = read()
    assert entered.wait(6), "native upload was not dispatched"
    forget("erase-upload-http")
    pending, ack = read(), read()
    assert pending["id"] == "fresh-upload" and pending["result"]["state"] == "unknown"
    assert (
        ack["id"] == "erase-upload-http" and ack["result"]["key"] == "erase-upload-http"
    )
    assert closed.wait(1), "upload pipe still open after forget ACK"
    prepare("revoked-upload")
    request = read()
    send(
        {
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {"code": -32000, "message": "original selection revoked"},
        }
    )
    frame = read()
    assert frame["id"] == "revoked-upload" and frame["result"]["state"] == "failed"
    return {
        "status": "PASS",
        "pages": pages,
        "late_page_ignored": True,
        "cleared_before_ack": True,
        "upload_cancelled_and_joined": True,
        "revoked_selection_requests": 0,
        "wrong_origin_requests": 0,
    }
