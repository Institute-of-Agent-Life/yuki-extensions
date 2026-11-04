# Client9 personal entry

Set YUKI_CLIENT_CORE and YUKI_CLIENT_LISTEN to distinct loopback addresses and
start the plugin through the Host. The Rust service uses the packaged SDK
handshake and forwards implicit-entry chat pairing, messages, receipts and
history to the configured owner. The owner alone issues credentials and commits
events. The plugin stores no credentials, request ledger or Person records.

The pinned CORE-033 development build ignores explicit entry and conversation
selectors. Requests with either header currently receive 503 before dispatch.
The owner's stream route currently returns 404. Attachment, ACP, merged-entry
and Social publication acceptance remain open.
