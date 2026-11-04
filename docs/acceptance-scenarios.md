# Acceptance scenarios

Scenarios precede acceptance runs. External services use controlled peers only
where the taskbook permits them; evidence names the peer and actual scope.

## EXT-001

Normal sequence: create two independent test distributions outside the checkout,
each with its own manifest and lock; build wheel and sdist; install each wheel
into a different clean environment; import it without the core; change only
alpha's manifest/version; select and rebuild alpha; compare beta's emitted bytes.
Also build one independent Rust binary using its own Cargo.lock and Rust 1.90.0
toolchain pin, execute the emitted binary, and verify that alpha's change does not
rebuild or change that binary. Record compiler/host versions and output digest.

Fault sequence: inject a neighbouring core dependency, an escaping local path,
a mutable/unpinned Git dependency, a private `yuki` import, or remove the lock.
Validation must reject each before any build. Artifact:
`extension-build-isolation.json` plus `manifest.json`. The fixture distributions
are never catalogued or released as product plugins. The physical Windows host
used for the first Python-only run has no Rust compiler; the added compiler case
runs on actual Windows/macOS/Linux CI machines and must not be skipped.
Real Host consumption remains outside this packaging case.

## EXT-007 independent candidate preparation

Build an independent 0.4.4.dev0 wheel/sdist. Install the pinned historical 0.4.3
wheel and the candidate into separate clean environments with unchanged locked
dependencies. Create two original operations with the old wheel, back up that
fixture journal through SQLite, and open only the copy with the candidate. The
confirmed receipt and unknown original must survive; another device and changed
parameters must be rejected without another operation. The original DB bytes
remain unchanged. Installing and querying an explicitly configured fixture must
not start its canary native daemon. Empty doctor performs no model task.

Run the inherited Connector/drivers suite against the installed candidate, with
the Desktop-stdin and plain-service processes exercised separately. Build the
real portable runtime, relocate it to a Unicode path and verify its own legal
files and inventory. Mutate a wheel by injecting private config and require
rejection before installation. Preserve any red and green reports.

This preparation is selected explicitly with `--preparation`. The formal command additionally replays the pinned producer node with both
installed wheels. Verify every ordered frame, including repeated ACKs and the
reconnect boundary. Change an event sequence and drop an ACK in negative controls.
Compare host-dependent hello facts to the execution platform and both actual
installations.

## EXT-008 original Codex app-server

Observe both directions at the loopback daemon. List/watch, prompt once, steer the
original turn, queue/delete by the original operation, answer the native question
once, interrupt only the named turn and detach the watch while the owner stays
available. Reject an unsupported queue method without a fallback prompt. Drop
the response after the daemon accepts one prompt, reconnect, then recover by
the original client message ID; require a read and exactly one turn/start.
Run discovery against fixture installations only.

## EXT-009 local Claude CLI and SDK

Read the fixture profile's history, reject implicit attachment, and resume only
the selected original session and cwd. Reject an answer naming the wrong native
question before delivering the correct one. End the SDK stream after a peer
file effect and observe the unknown receipt, retained bytes and single prompt.
Keep private profile and project canary contents out of observed SDK messages
and Connector events.

## EXT-010 native ACP v1

Start an actual stdio peer with an empty argument and an argument containing a
space. Require its declared capabilities before loading an original session.
Denying or omitting load cannot create a replacement session. Start a new run
beside the loaded one, answer only its original permission and cancel only the
named execution. Exit the native process with the second prompt pending and
verify both its real exit status and the unknown receipt.

## EXT-019 Desktop static consumer

Verify the Desktop source tree and both OpenAPI hashes at its own backend pin.
Enumerate renderer bridge, IPC, CLI, API calls and DTO references from its
TypeScript syntax trees. Compare the two old contracts independently to the
CORE-002 snapshots. Remove a used endpoint, remove Work.cancel.expected_revision,
change upload bytes to multipart, and substitute an SSE sequence for a business
cursor. Each mutation must fail the same consumer checks as the unmodified input.

## EXT-002 handshake candidate

Verify the producer commit, manifest, sdk-crosswire receipt, archive and all
members before unpacking. Reject a changed archive or a mismatched member.
Build the Rust consumer with its own Cargo.lock, install the Python consumer's
pinned wheel in isolation and run each outside the checkout with the independent
packaged stdio peer. Cross the two initialize requests with the same RPC id.
Unknown optional features and fields must preserve the agreed namespace and
empty grant. Reject an unknown method, unsupported wire version, missing
required feature and a changed manifest without breaking the original session.
Record the actual frames, consumer receipt and binary/package hashes. Report
candidate verification separately from the published-artifact gate.

The formal EXT-002 check downloads the GitHub prerelease assets at the fixed
CORE-031 tag. It verifies the producer receipt, checksum list and archive, then
uses those downloaded SDKs for the same isolated exchanges on every platform.
It distinguishes public distribution from the pre-publication state recorded
when those unchanged bytes were built.

## EXT-003 Telegram ingress

Run an independently compiled Rust plugin against the pinned CORE-032 Windows
candidate. Feed native Bot API updates over loopback with getMe and getUpdates.
For a three-item batch, interrupt the connection at the second admission. The
next poll may acknowledge only the committed prefix. Replay through the real
host and compare original event IDs. Distinguish two bot identities, equal
message IDs in different chats and group topics. Exercise UTF-16 mentions,
captions, reply references, media-only messages, edits and migration data.
Keep host startup, actual submitted frames, receipts and cursor files visible.

## EXT-028 public page read

Resolve and validate every destination on each hop, pin the actual socket to
that address, and carry the original Host/TLS name. Verify that credentials,
request headers and any body never survive an origin change, even on a return
to the first origin. A port change is also an origin change. Reject forbidden
addresses and changed DNS answers, report proxy failures without direct
fallback, keep 304 without inventing content, and preserve source references
on partial/oversize and missing text. A bounded native fixture must exercise
real HTTP exchange and compare the actual Host tool receipt.

## EXT-005 Feishu/Lark gateway

Connect an independently built Rust plugin to the installed Windows host and a
controlled platform endpoint. Verify app/tenant/domain selection, real WebSocket
framing, ping/pong and shuffled, repeated protobuf fragments. A message gets
a platform success ACK only after the host commits its original native event.
Interrupt the first admission before the host can reply, reconnect and replay.
Two apps using the same open_id cannot share receipts. Card/control frames
must not create a human message.

## EXT-020 persistent environment

Validate the original Manager, execd source, supervisor and image inputs
independently of the plugin package. Inspect a real Manager response only
through its bounded socket and project environment readiness without exposing
other runs. Missing Manager affects this tool only. Terminal dispatch also
needs a producer-bound Work, operation and run. Exercise restart, nonzero
exit with retained files, byte cursors and rotation gaps, PTY input/interrupt,
and cancellation of observation in an isolated Linux runtime.

## EXT-040 offline setup

On Windows, verify the clean signed CORE-039 OCI candidate against a separately
pinned source, signer, platform and digest. Generate a direct-only Compose kit
without a connector, QQ, Monty, environment image or Docker socket. Offline doctor
must work without invoking Docker or the network. Repeat installation over
operator comments, secret references and legacy NapCat values and preserve them.
Refuse corrupt inputs, unknown pins, an occupied owner file and unsigned optional
components. Test an actual selected native host when available; distinguish
rendering/doctor, native readiness and a launched Compose deployment.
