# Auxiliary media diagnostic peer

This is a Rust SDK test peer, not an installed media plugin. It reads one byte
from the original media handle, then sends one text-only request and one selected
media request through the same configured route. Its result labels these calls
as diagnostic data. It produces no transcript and has no send, command or
promotion grants. Run only against disposable fixture owners: forget requests
are explicitly refused, so this peer cannot establish privacy acceptance.

The immutable SDK is in `compat/core-050/`. Windows intake evidence records the
actual peer binary, source files, Host and SDK hashes. The configured loopback
provider is a deterministic HTTP peer, not a speech model.
