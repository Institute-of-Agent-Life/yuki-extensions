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
