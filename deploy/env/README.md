# Persistent environment backend source

`manager-source.zip` packages original Manager modules, the process supervisor,
the execd image recipe, license and Linux service inputs from Yuki commit
`329ca7c487414d2f54ddd98ff4727446ed2446cd`. Every member's Git blob and SHA-256
are in `plugins/env/backend/source.lock.json`. Rebuild the archive using
`python deploy/env/pack-source.py PATH_TO_HISTORICAL_CHECKOUT NEW_OUTPUT`.
An installed plugin needs only its verified SDK and the configured Manager socket.

The independently distributed environment image uses OpenSandbox execd commit
`441042c288a3eacbe93b36236a9baf6f6254ad4d`. Only the Linux host Manager receives
Docker access; it enforces the gVisor runtime, bounded storage and network guards.
The lock records the original image recipe. A release image digest and verified
runsc binary must come from the selected deployment. No image has been published
or installed by this preparation.
