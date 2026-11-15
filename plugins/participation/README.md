# Participation

The Rust plugin can handle the explicit native mention Rule in one approved
group entry. Pass the original entry ID and the selected receiving stage as
the program's arguments. Grant that same entry in `[plugins.participation]`.
An observed human message with an unambiguous native mention of that stage
can continue through the Host's ordinary promotion. Repeated observations
share the original Main input. Plain text names and other native targets do
not satisfy this Rule.

Install the worker with this configuration, filling in the
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

Use Python 3.12 or later, the packaged `semantic_bridge.py`, and the original
library archive pinned by `source.lock.json`. Install the locked Python
dependencies with `python -m pip install --require-hashes -r review-requirements.txt`.
In a source checkout these locks are under `compat/participation-library/`.
The checkpoint is a private
SQLite file in an existing directory. Give each review instance its own
checkpoint. Grant the review instance `participation.feedback`, `llm.complete`
and `llm.result` in addition to the grants above. Configure `ROUTE` for Jev `review` on that entry,
with event origin and the pinned response model. Model credentials stay in
the Host. The bridge runs the unchanged participation library against local
messages from the Rust worker.

A human reply to the same person's admitted message can continue before
Jev returns. The pinned library checks the existing relationship and the
original Main response's participation intent. The later Jev decision
shares the same Main input. A `quiet` report closes that relationship's
fast continuation.

A reply to Yuki's confirmed delivery can also continue the original
person's relationship. The worker matches its logical send and producer
event against Host feedback for the original admission.

An unquoted human input can use a single established relationship in the
same entry and generation. The Host verifies the original context versions
before admission. A native quote whose source has disappeared cannot use
the unquoted path.

Restart recovery uses the same original event and review key. Source erasure
removes affected snapshot data before the worker acknowledges the Host.

The 0.1.0-alpha.8 preview offers the opt-in intrinsic timer on the alpha.36 Host
contract. Append `--owner semantic` to the review arguments. The timer needs
`participation.sources` and `participation.self_propose` in addition to the
existing feedback and source grants. Install the original receiving stage
under `[plugins.participation.self_scenes]` for the same group entry.
`--owner legacy` and `--owner off` keep the ordinary review worker and leave
the timer inactive.

The Rust worker samples the pinned library every two seconds after successful
activation of the scene. It reads the current conversation generation and
sends a proposal with that generation and its original key. The intrinsic
proposal carries an empty set of human sources. The private snapshot stores
the proposal before dispatch. After restart, the worker queries the original
key and applies the authorized execution and its confirmed delivery, stop,
or no-reply feedback. Confirmed delivery uses the timestamp from the Host's
original physical receipt. The clock resumes at the current time. This preview
uses the intrinsic selector. Conversation-sourced SELF opportunities and the
official Host and plugin release remain separate acceptance work.
