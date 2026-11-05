# Participation input diagnostic

This is a Rust SDK diagnostic consumer, not an official participation plugin.
It records the actual `observer.event` and `participation.source` pages from the
pinned CORE-036 candidate. It neither promotes events nor purchases models.
`YUKI_PARTICIPATION_PROBE` selects a new isolated fixture output directory.

The Host requires `forget.owner` and an explicit receiving stage even for this
source-read probe. The probe deliberately refuses erasure acknowledgements; it
must only run on disposable synthetic owners. It is not a privacy implementation.

The physical Windows build used the checked-in alpha.7 SDK crate and Cargo.lock,
with a separately vendored registry. Its source and executable digests, actual
wire and missing canonical input fields are in
`artifacts/EXT-025/source-intake-01/`. The original participation library is
pinned in `compat/participation-library/source.lock.json`. No algorithm has been
rewritten or substituted by this probe.
