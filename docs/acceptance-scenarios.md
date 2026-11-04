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
