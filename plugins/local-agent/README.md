# Local-agent connector endpoint

This standalone Rust service forwards the original /agents/v1/pair exchange and
accepts the original Python Connector's wire4 hello and catalog. CORE-033
c85a00b121d0 / SDK alpha.12 authenticates the original credential, supplies the
device identity and stable journal namespace, and checks each received frame.
Each reconnect receives a new core epoch. Old catalog and close callbacks
cannot overwrite the replacement connection. Empty snapshots retain the device.

Set YUKI_LOCAL_AGENT_CORE and YUKI_LOCAL_AGENT_LISTEN to distinct loopback socket
addresses, YUKI_LOCAL_AGENT_STATE to a private absolute directory, and
YUKI_LOCAL_AGENT_INSTALLATION to the approved plugin installation ID (which may
differ from its SDK namespace). The installation needs device.connections.
External ingress must terminate TLS. The --catalog command reads the plugin's
inventory. Credentials, proofs and handles remain outside its database; only
the private exchange receives the original Bearer.

This is an unpublished candidate. The 300-second handle is checked at frame
boundaries. After 240 seconds the next frame closes the connection for
reauthentication; the original Connector's standard 20-second WebSocket ping
reaches that boundary before expiry. A reconnect uses its original credential
and journal. An old stream never renews itself over a replacement. Native event/response
frames require the original Work authority delivered separately; they are
closed without ACK here, leaving the Connector's durable event pending.
