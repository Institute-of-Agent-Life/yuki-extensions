# Local-agent connector endpoint

This standalone Rust service forwards the original /agents/v1/pair exchange
to the configured CORE-033 owner. Its own SQLite catalog records returned device
IDs, including devices with no instances. It never stores pairing codes or
bearer tokens. Set YUKI_LOCAL_AGENT_CORE and YUKI_LOCAL_AGENT_LISTEN to distinct
loopback socket addresses and YUKI_LOCAL_AGENT_STATE to a private absolute
directory. External ingress must terminate TLS. The local --catalog command
reads the plugin-owned inventory.

The current producer preview's device.auth consumes a proof scoped to a Work.
The wire4 connection opens independently of any Work. A hello cannot establish
its sender's authority; this build rejects the upgrade until the producer
supplies an authenticated device identity and revocation check. Existing
device registrations and journals remain with their original owners.
