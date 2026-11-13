# Memory maintenance candidate

This Rust plugin uses SDK alpha.8. Integrity reports require the CORE-035 Host
pinned in `compat/core-035-integrity/source.lock.json`. Install an explicit
maintenance policy in the Host and point
`YUKI_MEMORY_MAINTENANCE_JOBS` at an existing private operator-owned directory.
Do not expose that directory to models, chat users or unrelated processes.

To scan one authorized page, atomically rename a UTF-8 JSON file to `scan-1.job`:

```json
{"action":"scan","scope":"own","purpose":"quality","integrity":true}
```

The plugin writes `scan-1.result`. Each report retains the original audit
fingerprint and fact revisions. `fact` and `after` select a fact or page. Each
integrity result includes FTS status, missing evidence, checked and invalid event
evidence counts, and the coverage and last attempt for each authorized vector
profile. `action=audit` and `action=stats` request integrity by default. Statistics
apply to the returned page. Omit `integrity` on a `scan` job to use the original
audit response with an older Host. Scans leave core data and model counters intact.

For explicit FTS repair, submit `action=apply` with the same scope, purpose,
selector, integrity flag, original fingerprint, stable `operation` and
`approved` fact IDs.
For semantic reembedding, submit `action=reembed` with scope, purpose, operation,
route, full semantic profile identity, fact and its original revision. The Host
owns authorization, profile identity, accounting, source checks and idempotency.
The plugin never substitutes a fresh fingerprint after an old approval fails.

A `.started` marker is flushed before dispatch. Restart skips these jobs,
including jobs with no result. Inspect the original operation and resolve its
state before explicitly submitting recovery with the same operation. Changing
an operation to retry an unknown paid attempt is unsupported.

The plugin reads no core database. The operator submits each maintenance job
explicitly. Use `plugin-retained.toml` with a Host supporting `retain` and a
fresh private job directory to bind new reports to their original sources.
The plugin saves the report and its opaque erasure references in the same
atomic write. On a forget request it stops processing, removes the affected
reports and their original jobs, and retains their started markers. An
unreadable or unclassified report keeps the obligation pending. The operator
can start the worker again through the Host after the original watermark is
acknowledged. Previously saved reports require their original classification
before they can be included in this installation.

The tested maintenance scope uses `actor`, `entry`, `methods`, `purposes`,
`write_subject={kind="person",person="<original Person UUID>"}` and the allowed
`embedding_routes` under `[plugins.maintenance.scopes.<scope>]`. A model route
under `[plugins.maintenance.embedding_routes.<route>]` specifies
`provider="openai_compatible"`, `model`, `base_url` and `dimensions`. Use the
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
