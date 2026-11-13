# Rust subscription monitor candidate

Independently built `yuki-subscription-monitor` consumes the pinned CORE-058
notification protocol. Set `YUKI_SUBSCRIPTION_HOME` to an operator-owned directory
containing `subscriptions.json`. It stores only its own locked append journal
there; keep the directory and pending requests when upgrading or rolling back.
No source response can change a target or create an administrator grant.

```json
{"poll_seconds":30,"subscriptions":[{"id":"news","kind":"miniflux","url":"https://miniflux.example/v1/entries?limit=100","enabled":true,"targets":[{"target_type":"group","target_id":"original-space","conversation_id":"original-entry"}],"ask_agent":true,"condition":"Notify only a confirmed release","initial_sync":"baseline"}]}
```

Supported source snapshots: Miniflux entries, JSON Feed, Bilibili dynamics and
live-state responses. The first fetch establishes a silent baseline; explicit
`initial_sync=replay_recent` admits at most `replay_recent_limit` (default 3,
maximum 20). Existing pending requests drain first. The Miniflux reader walks
up to 20 pages in descending entry ID order using `before_entry_id` (Miniflux
2.0.9 or later). Keep collection filters such as `status` in the configured URL.
Use `limit` to select a page size of up to 100 and select a narrower collection
if it exceeds the page budget. The worker checks remaining counts and ID order
before admitting the collection. Incomplete pages, HTTP errors and malformed
responses preserve the previous cursor. RSS/Atom parsing and legacy KV migration
remain open.
HTTPS uses system curl with certificate validation, a 10-second bound, a 1 MiB
limit and no redirects. An explicit loopback HTTP service supports local Miniflux
and offline recordings. `token_env` optionally names a Host-approved environment
variable for Miniflux's X-Auth-Token; credentials stay out of argv and evidence.

Install the notification policy and the three requested grants from
`plugin.toml`. Register `subscription_admin` as a Host tool with actions `grant_target`,
`revoke_target`, `status`. The first two forward only the original Host call
handle and operation key. The Host checks the actual administrator and receiving
entry. A background poller cannot manufacture that call lineage.

`ask_agent=true` is the default: source text stays external data and the condition
is an intent, never a system prompt. Main may remain quiet. Explicit direct mode
sends the bounded summary through the same notification service. A publication
receipt is separate from physical confirmed/unknown delivery.

The journal holds cursor and complete requests in one synced record before any
publish. A lost ACK replays the exact immutable request; no new event key is
created for retry. An incomplete journal or a second writer stops processing.
The 100 MiB quota fails closed and retains state; it does not evict dedup markers.
For a Host erasure request, the worker stops polling and removes matching
publication receipts from the journal and its historical rows. It keeps seen
keys so the same feed item stays fenced. An unresolved publication leaves the
original watermark pending. The cleanup entry does not poll feeds.

This is an unpublished candidate. Windows real Host evidence, supported methods
and remaining full-card requirements are tracked under `artifacts/EXT-027`.
