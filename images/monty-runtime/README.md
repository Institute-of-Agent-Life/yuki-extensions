# Monty runtime candidate

Independent Linux amd64 OCI build for EXT-023. The official Code plugin is Rust;
this image retains the original native Rust Monty worker and its CPython 3.12
codec/backend. It contains no Host, identity store, business dispatcher or tool
budget implementation. The direct installation has no dependency on this image.

The worker source is `3f9d6ef413fb951e5b80113b7088d535bd028fcb`, with the original
string-cache patch and fixed Linux bubblewrap launcher from Yuki baseline
`329ca7c487414d2f54ddd98ff4727446ed2446cd`. The original build and notice-export
scripts are unchanged. Backend adaptations rename imports and retain only pure
snapshot position matching; they do not import the old database or core modules.
`baseline.lock.json` and `backend-adaptation.lock.json` identify these bytes.

`scripts/prepare_inputs.py` verifies these files and supplies exact Git objects to
the original builder. Build this directory with Docker after preparing inputs.
The three base images are pinned Linux amd64 manifests in `base-images.lock.json`.
The release build uses Rust 1.96.0 with LTO disabled and 16 codegen units, so the
original source compiles within the HJW WSL 4 GiB allocation. Runtime limits and
isolation are unchanged. This build produces its own binary digests; it does not
claim byte identity with a previous build.

The resulting image includes the built worker, launcher, binding wheel,
target-specific dependency notices and a runtime contract derived from the actual
bytes. The private stdin/stdout bridge only drives the original manual
start/answer/dump/restore API. It accepts a frozen script-name projection, runs no
business tools, and terminates the VM on input disconnect. A missing or mismatched
runtime must make Code unavailable.

Run only with the checked-in enforced AppArmor and seccomp profiles, UID/GID
10001, no capabilities, no network, a read-only root, bounded tmpfs, PID and memory
limits, and no host data mounts. As specified by the original security README, bwrap
sets NoNewPrivs=1 inside the worker after the fixed launcher transition; adding
container-wide no-new-privileges would prevent that transition. The worker
NoNewPrivs assertion remains required. Install the profile through an explicitly
authorized operator step. Do not disable an isolation check to make a test pass.

The acceptance sequence is: verify actual image/worker/launcher/codec inputs;
observe a suspended native worker's namespaces, UID, capabilities, LSM and limits;
resume its result; enforce an infinite-loop limit; cancel a blocked feed; kill
its Python owner and confirm all original descendants terminate; restore a native
snapshot in a fresh isolated worker; reject corrupt snapshots and incompatible
contracts. Core parent identity, ordinal and durable recovery are checked through
the real Rust plugin separately. Environment and image checks alone do not mark
EXT-023 or EXT-024 accepted.

Native CI enables CPython fatal-signal tracebacks and retains attached output
and Docker logs for a blocked-feed disconnect.
It also exports the exact built image and copies its runtime contract before
validation, including when validation fails. A failure artifact remains marked
FAIL and unpublished; retaining it only enables reproduction of that exact build.
Export errors retain the original validation traceback and keep the gate failed.
