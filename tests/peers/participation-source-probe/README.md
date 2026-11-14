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

`jev_replay.py` exercises the pinned participation library through the installed
SDK and Rust Host. It reads a confirmed OneBot delivery as original SELF
context, retains literal names as text, and sends the library's native Jev
request through `llm.complete`. The positive fixture submits an ordinary native
mention promotion before Jev reviews the same focus. They share one
accepted Main input. The peer reopens its private library checkpoint after a
Host restart and reads the original model result and usage. All endpoints and
participants in this diagnostic are fixtures.

Run `python -B ci/check.py EXT-025 --preparation --out <new-directory>` from the
extension root with `PYTHONPATH=ci`. Set `YUKI_PARTICIPATION_SOURCE` to the pinned
archive, `YUKI_CORE050_CANDIDATE` to the matching platform ZIP, and
`YUKI_CORE050_MANIFEST` to its producer verification manifest. Install the
hash-locked replay requirements in an isolated Python 3.12 environment.
