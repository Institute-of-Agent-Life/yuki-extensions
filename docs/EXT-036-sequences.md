# EXT-036 normal and failure sequences

Consume CORE-035 clean source `0cdd9dffe07c` and SDK alpha.8 as an unpublished
candidate. The operator places a bounded JSON request in the installed plugin's
private job directory. Only audit, fingerprint-confirmed FTS repair and selected
semantic reembedding are accepted. No model, chat message or timer creates jobs.

The integrity replay uses a newer pinned CORE-035 Host with the same method
revision. Legacy `scan` jobs retain their existing shape. `audit` and `stats`
request integrity by default. For an integrity scan, the operator can also
submit `scan` with `"integrity":true`. The Host returns lexical status, evidence
counts and coverage with the latest attempt state for each authorized profile.

1. Audit a real authorized fact page. Retain the original fingerprint, revisions,
   evidence counts and semantic profile identities; report zero paid calls.
   Repeat the scan and inspect the isolated database to confirm it leaves
   the index, evidence, attempts and apply receipts intact.
2. Explicitly approve a subset with that page's fingerprint and selector. Pass
   the original operation and integrity flag to core. Verify that only the
   selected lexical row changes. Recheck changed sources through core.
3. Select one fact revision and installed semantic profile for reembedding.
   Retain done/pending/unknown and available usage from the original receipt.
   A new model with the same dimensions is still a different profile.
4. Mark a job started before any call. An interrupted job is not automatically
   retried after restart. Explicit resubmission retains its original operation.
5. Reject unknown scope, foreign fact, changed fingerprint/revision, uninstalled
   profile and an omitted operation. Never manufacture missing source evidence.
6. A forget callback stops work and refuses ACK while the metadata dependency
   contract is missing. Unrelated operator jobs must not be deleted speculatively.
   The audit/reembed consumer received no automatic callback or pending obligation
   in candidate-04/05. This remains unaccepted pending the producer's metadata
   retention contract. No synthetic operator acquire substitutes for registration.

Native replay uses the packaged Host, actual Rust plugin and public operator
commands. Only the test harness corrupts fixture rows in an isolated, stopped
owner. Controlled HTTP embedding responses exercise request accounting.

Windows candidate-06 passed the implemented audit, selected FTS apply, restart,
same-count revision/fingerprint rejection, distinct same-dimension embeddings,
unknown-attempt replay and post-erasure reembed refusal. Candidate-01 records the
missing `write_subject` configuration; candidate-04 preserves the unmet automatic
callback assertion. Metadata erasure and the published tuple remain pending.
