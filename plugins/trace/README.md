# Trace query candidate

This independent Rust plugin queries one page of the original core timeline.
It consumes unpublished CORE-037 `1e7b89362b6f` and SDK alpha.11. Install the
plugin's declared grants and `trace_query` tool in the Host. The complete
isolated installation is exercised by `tests/cases/EXT-037.py`.

```json
{"kind":"event","identity":"1","after":0,"limit":20,"content":false}
```

`kind` selects an original event, turn or Work. `identity` is its original core
ID. Metadata is the default; requesting payload requires an explicit boolean
and the Host's separate content permission. Every call uses the actual
Host-issued tool handle. The plugin cannot supply another actor or role. The
Host rechecks current authority and sources; rejected reads return an error.
Pages are bounded to 20 rows, and cursor values are returned by the core.

The candidate keeps no private database, result cache or background writer.
It does not subscribe to body events. It reads no core database and performs
no model, tool-effect, usage or authorization reconstruction. Missing trace
rows do not establish whether a business effect or paid request completed.

Full EXT-037 remains pending: opt-in subscriptions, a bounded private store,
drop counters, delayed-writer erasure and versioned export need the producer's
public source-retention and current-scope contract. The control intake did not
receive an automatic forget callback after reading a trace page. That
observation is not a claim that metadata-only reads must register a store.
The candidate does not claim cleanup ownership or acknowledge an unperformed
private-store erasure. It must not be presented as full-card acceptance.
