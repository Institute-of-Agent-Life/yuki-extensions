# Participation

The Rust plugin can handle the explicit native mention Rule in one approved
group entry. Pass the original entry ID and the selected receiving stage as
the program's arguments. Grant that same entry in `[plugins.participation]`.
An observed human message with an unambiguous native mention of that stage
can continue through the Host's ordinary promotion. Repeated observations
share the original Main input. Plain text names and other native targets do
not satisfy this Rule.

Install the development candidate with this configuration, filling in the
entry and assignment from the same Host.

```toml
[[plugins]]
id = "participation"
namespace = "participation"
program = "/absolute/path/yuki-participation"
args = ["original-group-entry", "original-receiving-stage"]
grants = ["observe.metadata", "participation.source", "participation.promote", "forget.owner"]

[plugins.participation]
entries = ["original-group-entry"]
```

The plugin reads every original mention page under one source version. A
group, identity or generation change is checked by the Host at promotion.
The Rule keeps no source body on disk. It clears matching queued observations
and waits for the active read to finish before acknowledging source erasure.

Optional Jev review runs as a second Rust worker for the same entry with its
own plugin ID and namespace. The Rule can admit a native mention while the
review is still waiting for a response. The review worker reads the original
human focus and its exact reply anchor through the Host. An invitation
promotes the original focus with the anchor's event ID and version. The Host
checks the anchor in the same transaction that admits the focus.

Pass these arguments after the original entry and receiving stage.

```text
--review PYTHON BRIDGE SOURCE_ARCHIVE CHECKPOINT ROUTE RESPONSE_MODEL DISPLAY_NAME
```

Use Python 3.12 or later with `compat/participation-library/replay-requirements.txt`
installed, the packaged `semantic_bridge.py`, and the archive pinned by
`compat/participation-library/source.lock.json`. The checkpoint is a private
SQLite file in an existing directory. Give each review instance its own
checkpoint. Grant the review instance `llm.complete` and `llm.result` in
addition to the grants above. Configure `ROUTE` for Jev `review` on that entry,
with event origin and the pinned response model. Model credentials stay in
the Host. The bridge runs the unchanged participation library against local
messages from the Rust worker.

Restart recovery uses the same original event and review key. Source erasure
removes affected snapshot data before the worker acknowledges the Host.
This development package covers review with a canonical reply anchor.
