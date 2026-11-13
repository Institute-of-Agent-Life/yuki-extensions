# EXT-027 source admission and notification recovery

This Rust candidate consumes the immutable CORE-058 cb02f74 package (SDK alpha.10).
It owns only its configuration, observed-source cursor and outbox. The Host owns
identity, target grants, publication, Main admission and physical delivery.

Normal sequence: fetch the configured source → validate the complete bounded
response → initialize a silent baseline or identify new source IDs → durably
append the cursor and complete immutable requests together → publish each saved
request → durably save its publication receipt. A receipt is acceptance; its
individual delivery states remain pending/confirmed/failed/unknown.

Fault sequences established before implementation:

- Kill after the cursor/outbox commit: restart drains that saved outbox before
  another fetch. Kill after Host commit before its ACK: replay the exact original
  event key and target/body, obtaining the original publication.
- Re-fetch the same source IDs (including edited body): no new publication.
  Equal content under two subscription IDs remains two independent observations.
- Network/API/parse failure: record an observation error; do not turn it into an
  empty source or advance the cursor. A saved pending batch remains recoverable.
- Revoke the target: Host rejects new publication. Never use a previous human
  administrator as the background actor or replace the target to evade refusal.
- Unknown physical delivery: retain the original publication and unknown receipt;
  do not create another key, resend its effect or count it as confirmed.
- Change source URL/type under the same ID: reject; preserve the cursor. Pending
  requests retain their original target even when subsequent config changes.
- Truncated journal or a second writer: stop without discarding or repairing data.
- An original private-source erasure stops polling, rewrites the journal
  without the affected receipts, preserves seen keys, and echoes the original
  watermark. A dispatched request with an unknown publication keeps the
  watermark pending until its original outcome is known.

R06 uses bounded Miniflux entries, Bilibili dynamics and live-state snapshots,
with baseline/current cursor and original pending rows. Miniflux is read through
its entries endpoint; this plugin does not initiate another RSS fetch for it.
The first candidate's JSON-source transport and three parsers are verified
separately from legacy RSS/Atom import and formal publication.
