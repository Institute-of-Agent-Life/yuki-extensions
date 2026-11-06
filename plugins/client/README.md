# Client9 original personal entries

Set YUKI_CLIENT_CORE and YUKI_CLIENT_LISTEN to distinct loopback addresses and
start the plugin through the Host. The Rust service uses the packaged SDK
handshake and forwards pairing, messages, receipts, home, history, uploads,
attachment downloads and SSE to the configured owner. X-Yuki-Entry and
X-Yuki-Conversation pass through unchanged. The owner alone authenticates,
resolves original scopes, normalizes UUIDs/ordered attachments and commits
events. The plugin stores no credentials, request ledger or Person records.

CORE-033 c616cf35e442 / SDK alpha.12 is an unpublished fixed candidate, locked
under compat/core-033-client. Duplicate authority headers are rejected; invalid
selection is never silently replaced by a default. Upload bytes stream to the
owner (declared Content-Length, at most 64 MiB); JSON bodies retain the 1 MiB
limit. The owner supplies download ETags and content disposition.

Four SSE sessions, four uploads and eight ordinary requests have separate
limits. SSE bytes flush without a local queue, generated cursor or replay.
The upstream response lifetime is bounded to 65 seconds so a quiet abandoned
connection eventually releases its permit. Reconnect using a fresh sync and
GET events after the original durable event; an SSE id is connection-local.

Use EXT-015 --preparation for the Windows consumer scenarios. The optional
fixture flag YUKI_CLIENT_SOCIAL_PROBE=1 retains the strict Social publication
assertion. ACP public setup, the local Main-to-Social route, complete H24,
H27/H28 and publication remain separately tracked. HTTP ACK and SSE observation
do not establish human read confirmation.
