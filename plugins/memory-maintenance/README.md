# Memory maintenance candidate

This independent Rust plugin consumes the pinned, unpublished CORE-035 alpha.8
Host. Install an explicit maintenance policy in the Host and point
`YUKI_MEMORY_MAINTENANCE_JOBS` at an existing private operator-owned directory.
Do not expose that directory to models, chat users or unrelated processes.

To scan one authorized page, atomically rename a UTF-8 JSON file to `scan-1.job`:

```json
{"action":"scan","scope":"own","purpose":"quality"}
```

The plugin writes `scan-1.result`. Each report retains the original audit
fingerprint and fact revisions. `fact` and `after` select a specific fact/page.
The page is bounded; it does not claim to summarize the whole database. Missing
semantic profile identities remain distinct from pending or unknown attempts.
No scan requests a model or writes a core fact.

For explicit FTS repair, submit `action=apply` with the same scope, purpose,
selector, original fingerprint, stable `operation` and `approved` fact IDs.
For semantic reembedding, submit `action=reembed` with scope, purpose, operation,
route, full semantic profile identity, fact and its original revision. The Host
owns authorization, profile identity, accounting, source checks and idempotency.
The plugin never substitutes a fresh fingerprint after an old approval fails.

A `.started` marker is flushed before dispatch. Restart skips these jobs,
including jobs with no result. Inspect the original operation and resolve its
state before explicitly submitting recovery with the same operation. Changing
an operation to retry an unknown paid attempt is unsupported.

The plugin reads no core database. It implements no timer or model-triggered
maintenance. Its forget handler stops processing and returns
`metadata_erasure_contract_pending`; it does not acknowledge unproved erasure or
delete unrelated operator jobs. The candidate did not send an automatic callback
after this metadata-only audit/reembed flow. The producer's retention/dependency
contract is required before this integration can be accepted.

The candidate's audit does not expose the complete legacy SQL quality findings.
Full EXT-036 parity and formal release remain pending; this executable reports
that gap instead of treating missing findings as healthy data.

The tested maintenance scope uses `actor`, `entry`, `methods`, `purposes`,
`write_subject={kind="person",person="<original Person UUID>"}` and the allowed
`embedding_routes` under `[plugins.maintenance.scopes.<scope>]`. A model route
under `[plugins.maintenance.embedding_routes.<route>]` specifies
`provider={openai_compatible={}}`, `model`, `base_url` and `dimensions`. Use the
actual Person and entry created by the core; UUIDs are not bearer credentials.
The executable test `tests/cases/EXT-036.py` contains the complete loopback fixture.

## Review a rebuild batch

Use `plugin-rebuild.toml` and a dedicated private operator job directory for
rebuild. Its `args` select the rebuild worker and its `erasure_args` let the Host
start that worker in cleanup-only mode when a stopped instance has pending
erasure. The default `plugin.toml` grants the existing quality operations.

Grant `maintenance.history.page`, `maintenance.evidence`,
`maintenance.extract.preview`, `maintenance.extract.apply`,
`maintenance.content`, `llm.complete`, `llm.result` and `forget.owner`.
The Host uses the two `llm.*` grants to authorize the preview's auxiliary
request and read its original structured result. The named maintenance scope
lists the five `maintenance.*` methods for the original Person, entry and
`rebuild` purpose. Install its exact write subject and an auxiliary route with
the same entry, purpose and `maintenance` origin. See the complete policy in
`tests/cases/EXT-034.py`.

Submit an explicit selection as a new `.job` file:

```json
{"action":"rebuild.preview","batch":"november","plan":{"scope":"own","route":"extract","mode":"text_json","sources":[{"event":41,"role":"primary"},{"event":42,"role":"context"}]}}
```

The worker resolves source versions before requesting a Host dry-run. The
result contains the original preview ID and content descriptor.
`rebuild.read` accepts `batch` and `offset` and returns one base64-encoded
page. Use the Host's `next_offset` and `sha256` to read and verify the full
review content before approval.

Submit a reviewed subset under its own operation key:

```json
{"action":"rebuild.apply","batch":"november","preview":"<original preview ID>","operation":"approved-first","approved":[0]}
```

Unselected ordinals remain in review. To recover a crash after dispatch, submit
the same preview, operation and subset in a new job file. The worker persists
the intent first and retrieves the original Core receipt. `rebuild.status`
reports the pending intent and the confirmed ordinals. `rebuild.pause`, `rebuild.resume` and
`rebuild.cancel` accept the batch ID. Pause and cancel take effect between
operator jobs. Cancel closes the batch to further effects.

The rebuild-only worker stops on a Host forget request, removes affected
inbox jobs and results, and invalidates their journals. It preserves fixed
started markers so an old job name stays fenced after erasure. If a journal or
admissible inbox job cannot be classified, the worker clears the sources it can identify
and leaves the Host obligation open. Resolve the unreadable file locally and
restart the worker to settle the original watermark. The separate quality mode
retains its pending-erasure response. Protect the private job directory from
concurrent external writes during cleanup.

The native product fixture uses the local CORE-035 and CORE-050 archives for
the running system, pinned in `tests/fixtures/EXT-034`. Set
`YUKI_CORE035_CANDIDATE` and `YUKI_CORE050_CANDIDATE` to those archives.
Run `python ci/check.py EXT-034 --preparation --out artifacts/EXT-034/product-macos-02`.
The current product build uses its existing alpha.8 SDK pin and negotiates the
rebuild methods against the alpha.21 Host. Publication and additional platform
qualification remain pending.
