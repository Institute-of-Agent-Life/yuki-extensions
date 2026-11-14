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

The pinned library's Jev evaluation and restart receipts are exercised by
the EXT-025 replay peer. The native worker is a development candidate for
the Rule path.
