# Shared character candidate

This independent Rust plugin reads and updates the shared role and SOUL through
the pinned CORE-037 alpha.11 control protocol. Install `plugin.toml` grants and
the `character_manage` tool in the Host. The plugin keeps no character store.
The core owns permanent identity, active files, authority and mutation receipts.

Read actions are `public`, `identity`, `read` and `soul`. Writes are `update`,
`save_soul` and `reload_soul`; their `body` is the original fixed Admin DTO,
including the caller's explicit request_id and expected_revision where required.
Empty SOUL content is passed unchanged. Read the current core result to learn
which revision is active. A completed save and an explicit reload have separate
requests and results.

The plugin forwards the actual Host-issued handle. It cannot choose an actor,
role, new revision or substitute request ID. It dispatches once and never retries
automatically. If a reply is lost, inspect the original core operation and keep
the original mutation identity; do not issue a replacement ID to guess success.

Full EXT-038 is pending the public immutable-avatar and per-platform application
bridge, historical-data disposition and formal publication. No avatar action is
invented, no platform success is assumed, and no legacy private store is imported
by this shared-role candidate. Tests explicitly distinguish this candidate from
full `character-application` acceptance.
