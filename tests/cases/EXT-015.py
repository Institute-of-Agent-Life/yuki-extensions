"""Witness committed Client9 receipts through the actual Rust plugin and personal Host."""

import json
import uuid

from personal_preview import Owner, http


def prepare(root, output):
    owner = Owner(root, output, "client", [])
    transcript = []
    secrets = []

    def call(method, path, status, body=None, token=None, headers=None):
        actual, response = http(owner.edge, method, path, body, token, headers)
        transcript.append({"method": method, "path": path, "status": actual})
        if actual != status:
            raise AssertionError(
                f"{method} {path}: expected {status}, received {actual}"
            )
        return response.get("data", response)

    def pair(person, label):
        code = owner.issue(person, "chat")
        credentials = call(
            "POST", "/client/v1/pair", 200, {"code": code, "device_label": label}
        )
        secrets.extend((code, credentials["token"]))
        denial = call(
            "POST", "/client/v1/pair", 401, {"code": code, "device_label": label}
        )
        assert "token" not in denial
        return credentials

    with owner.running():
        people = [str(uuid.uuid4()), str(uuid.uuid4())]
        for person in people:
            owner.cli("operator", "person", "create", person)
        phone, desktop, visitor = (
            pair(people[0], "phone"),
            pair(people[0], "desktop"),
            pair(people[1], "visitor"),
        )
        assert len({d["device_id"] for d in (phone, desktop, visitor)}) == 3
        me, other, foreign = [
            call("GET", "/client/v1/me", 200, token=d["token"])
            for d in (phone, desktop, visitor)
        ]
        fields = (
            "binding_id",
            "conversation_id",
            "request_person_id",
            "request_conversation_id",
        )
        assert all(me[k] == other[k] and me[k] != foreign[k] for k in fields)
        assert (
            me["request_person_id"] == people[0]
            and foreign["request_person_id"] == people[1]
        )
        call("GET", "/client/v1/me", 401)
        uuid_key = str(uuid.uuid4())
        body = {"text": "Windows Client9 收件", "request_id": uuid_key}
        first = call("POST", "/client/v1/messages", 200, body, phone["token"])
        replay = call(
            "POST",
            "/client/v1/messages",
            200,
            dict(reversed(tuple(body.items()))),
            desktop["token"],
        )
        assert (
            first["replay"] is False
            and replay["replay"] is True
            and first["event_id"] == replay["event_id"]
        )
        conflict = call(
            "POST",
            "/client/v1/messages",
            409,
            {**body, "text": "changed"},
            desktop["token"],
        )
        assert conflict["problem"]["code"] == "request_conflict"
        request_path = "/client/v1/requests/" + uuid_key
        receipt = call("GET", request_path, 200, token=desktop["token"])
        assert (
            receipt["found"]
            and receipt["status"] == "accepted"
            and receipt["event_id"] == first["event_id"]
        )
        assert call("GET", request_path, 200, token=visitor["token"])["found"] is False
        foreign_event = call("POST", "/client/v1/messages", 200, body, visitor["token"])
        assert (
            foreign_event["conversation_id"]
            == foreign["conversation_id"]
            != first["conversation_id"]
        )
        events_path = "/client/v1/conversations/" + me["conversation_id"] + "/events"
        page = call("GET", events_path, 200, token=desktop["token"])
        assert [event["event_id"] for event in page["items"]] == [first["event_id"]]
        for header, value in (
            ("X-Yuki-Entry", foreign["binding_id"]),
            ("X-Yuki-Conversation", foreign["conversation_id"]),
        ):
            failure = call(
                "GET", request_path, 503, token=phone["token"], headers={header: value}
            )
            assert failure["problem"]["code"] == "owner_selection_unavailable"
        rejected_id = str(uuid.uuid4())
        call(
            "POST",
            "/client/v1/messages",
            503,
            {"request_id": rejected_id, "text": "do not reroute"},
            phone["token"],
            {"X-Yuki-Entry": foreign["binding_id"]},
        )
        assert not call(
            "GET", "/client/v1/requests/" + rejected_id, 200, token=phone["token"]
        )["found"]
        call("GET", "/client/v1/stream", 404, token=phone["token"])
        call("GET", "/admin/v1/health", 404, token=phone["token"])
        call("GET", "/client/v1/%2e%2e/admin", 404, token=phone["token"])
        for change in (
            {"attachments": ["first", "second"]},
            {"attachments": ["second", "first"]},
            {"agent_target": {"intent": "prompt", "device_id": phone["device_id"]}},
        ):
            rejection = call(
                "POST", "/client/v1/messages", 503, {**body, **change}, desktop["token"]
            )
            assert rejection["problem"]["code"] == "unavailable"
        merged = owner.cli("operator", "person", "merge", people[0], people[1])
        assert merged["original"] == people[0] and merged["root"] == people[1]
        after = []
        for d, original in ((phone, me), (visitor, foreign)):
            view = call("GET", "/client/v1/me", 200, token=d["token"])
            assert view["person_id"] == people[1] and all(
                view[k] == original[k] for k in fields
            )
            original_receipt = call("GET", request_path, 200, token=d["token"])
            assert original_receipt["conversation_id"] == original["conversation_id"]
            after.append({k: view[k] for k in (*fields, "person_id")})
        status, selected = http(
            owner.address,
            "GET",
            "/client/v1/me",
            token=phone["token"],
            headers={"X-Yuki-Entry": foreign["binding_id"]},
        )
        assert (
            status == 200
            and selected["data"]["binding_id"]
            == me["binding_id"]
            != foreign["binding_id"]
        )
        owner.cli("operator", "personal", "revoke", desktop["device_id"])
        call("GET", "/client/v1/me", 401, token=desktop["token"])
        call("GET", "/client/v1/me", 200, token=phone["token"])
        evidence = {
            "merged_original_entries": after,
            "direct_owner_explicit_selection": {
                "status": status,
                "requested_binding": foreign["binding_id"],
                "returned_binding": selected["data"]["binding_id"],
            },
            "revoked_device_denied": 401,
            "attachments_and_agent_target": "503 unavailable; original receipt retained",
            "request_id": uuid_key,
            "original_entry": {k: me[k] for k in fields},
            "separate_entry": {k: foreign[k] for k in fields},
            "device_ids": [d["device_id"] for d in (phone, desktop)],
            "first": first,
            "replay": replay,
            "changed_text": conflict,
            "receipt": receipt,
            "event_count": len(page["items"]),
            "foreign_event": foreign_event,
            "explicit_entry_and_conversation": "503 before dispatch; no receipt created",
            "unwitnessed": [
                "post-merge entry selection",
                "disabled entry vs revoked device",
                "ordered attachment / agent_target / operation conflicts",
                "ACP conversation selection",
                "Social Outbound SSE",
            ],
        }
    with owner.running():
        recovered = call("GET", request_path, 200, token=phone["token"])
        assert recovered == receipt
    for secret in secrets:
        assert (
            secret not in owner.trace.read_text()
            and secret not in (output / "host.txt").read_text()
        )
    return "original-uuid-entry.json", {
        "status": "PASS",
        "card_status": "PARTIAL_IMPLICIT_CHAT_ON_UNPUBLISHED_CANDIDATE",
        **owner.evidence(),
        "http_transcript": transcript,
        "cases": {"H24": evidence},
        "after_restart": recovered,
    }


def run(root, output):
    return "original-uuid-entry.json", {
        "status": "BLOCKED",
        "card_status": "AWAITING_ENTRY_SELECTION_AND_SOCIAL_PUBLICATION",
        "reason": "CORE-033 candidate ignores explicit entry/conversation selectors. Social Outbound SSE and merged-entry scopes require owner evidence.",
    }
