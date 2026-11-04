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
