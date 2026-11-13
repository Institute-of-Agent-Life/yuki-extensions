use crate::feed::Result;
use crate::feed_entry::{Entry, html, plain, resolve, safe_link};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use url::Url;

type Object = Map<String, Value>;

fn string<'a>(row: &'a Object, field: &str) -> Result<&'a str> {
    match row.get(field) {
        Some(value) => value
            .as_str()
            .ok_or_else(|| format!("invalid JSON Feed {field}")),
        None => Ok(""),
    }
}

fn authors(row: &Object) -> Result<String> {
    let name = |author: &Value| {
        string(
            author.as_object().ok_or("invalid JSON Feed author")?,
            "name",
        )
        .map(str::to_owned)
    };
    if let Some(value) = row.get("authors").filter(|value| !value.is_null()) {
        let list = value.as_array().ok_or("invalid JSON Feed authors")?;
        let names = list.iter().map(name).collect::<Result<Vec<_>>>()?;
        Ok(names.join(", "))
    } else {
        row.get("author")
            .filter(|value| !value.is_null())
            .map_or_else(|| Ok(String::new()), name)
    }
}

pub(crate) fn parse(source: &str, raw: &Value, now: &str) -> Result<Vec<Value>> {
    let feed = raw.as_object().ok_or("expected JSON Feed object")?;
    if !matches!(
        string(feed, "version")?,
        "https://jsonfeed.org/version/1" | "https://jsonfeed.org/version/1.1"
    ) {
        return Err("expected JSON Feed version 1 or 1.1".into());
    }
    if feed.contains_key("next_url") {
        return Err("paged feed requires complete capture".into());
    }
    let base = Url::parse(source)
        .ok()
        .filter(safe_link)
        .ok_or("invalid feed URL")?;
    let items = raw["items"].as_array().ok_or("missing JSON Feed items")?;
    let mut seen = HashSet::new();
    let mut entries = Vec::new();
    for item in items {
        let item = item.as_object().ok_or("invalid JSON Feed item")?;
        let body = if item.contains_key("content_text") {
            plain(string(item, "content_text")?)
        } else if item.contains_key("content_html") {
            html(string(item, "content_html")?)
        } else {
            return Err("missing JSON Feed content".into());
        };
        let author = if item.contains_key("authors") || item.contains_key("author") {
            authors(item)?
        } else {
            authors(feed)?
        };
        let tags = match item.get("tags") {
            None => Vec::new(),
            Some(value) => value
                .as_array()
                .ok_or("invalid JSON Feed tags")?
                .iter()
                .map(|tag| {
                    tag.as_str()
                        .map(str::to_owned)
                        .ok_or_else(|| "invalid JSON Feed tag".into())
                })
                .collect::<Result<Vec<_>>>()?,
        };
        let published = string(item, "date_published")?;
        let entry = Entry {
            id: string(item, "id")?.to_owned(),
            title: plain(string(item, "title")?),
            body,
            link: resolve(&base, string(item, "url")?),
            author: plain(&author),
            tags,
            date: if published.is_empty() {
                string(item, "date_modified")?
            } else {
                published
            }
            .to_owned(),
        };
        // Existing journals were keyed on the exact explicit ID.
        let id = if entry.id.is_empty() && entry.link.is_none() {
            let fields = [source, &entry.title, &entry.body, &entry.author]
                .map(|field| Value::String(field.to_owned()).to_string());
            // Match the original v4 content identity's JSON array separators.
            format!(
                "sha256:{:x}",
                Sha256::digest(format!("[{}]", fields.join(", ")).as_bytes())
            )
        } else if entry.id.is_empty() {
            entry.identity(source)
        } else {
            entry.id.clone()
        };
        if seen.insert(id.clone()) {
            entries.push(entry.project(id, now));
        }
    }
    Ok(entries)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const SOURCE: &str = "https://example.org/feeds/release.json";
    const NOW: &str = "2026-11-13T00:00:00Z";

    #[test]
    fn reads_v4_entry_projection_for_both_versions() {
        for version in ["1", "1.1"] {
            let feed = json!({
                "version": format!("https://jsonfeed.org/version/{version}"),
                "author": {"name":"Old Name"}, "authors":[{"name":"Team"}],
                "items":[
                    {"id":"2", "content_text":"literal <b>text</b>", "url":"../2",
                        "date_published":"2026-09-22T14:00:00+08:00", "tags":["update","update"]},
                    {"id":"2", "content_text":"different body"},
                    {"id":"1", "title":"Old", "content_html":"<p>Hi<br>there</p><style>hidden</style>",
                        "author":{"name":"Writer"},"date_modified":"2026-09-22T06:00:00"},
                    {"content_text":"Keep  <b>字</b>","url":"https://user@example.org/path"},
                    {"content_text":"Linked","url":"../entry"},
                ]
            });
            let entries = parse(SOURCE, &feed, NOW).unwrap();
            assert_eq!(entries.len(), 4);
            assert_eq!(entries[0]["body"], "literal <b>text</b>");
            assert_eq!(entries[0]["author"], "Team");
            assert_eq!(entries[0]["tags"], json!(["update"]));
            assert_eq!(entries[0]["published_at"], "2026-09-22T06:00:00Z");
            assert_eq!(entries[0]["url"], "https://example.org/2");
            assert_eq!(entries[1]["body"], "Hi there");
            assert_eq!(entries[1]["author"], "Writer");
            assert_eq!(entries[1]["published_at"], Value::Null);
            assert_eq!(entries[1]["occurred_at"], NOW);
            assert_eq!(entries[2]["url"], "");
            assert_eq!(
                entries[2]["id"],
                "sha256:9f4e2fd7c13de082003d90b6fee9dd73308b8a39c0ba84a2d1ee67e5e1f4fd83"
            );
            assert_eq!(entries[3]["id"], "https://example.org/entry");
        }
    }

    #[test]
    fn refuses_incomplete_or_malformed_snapshots() {
        let feed = |items| json!({"version":"https://jsonfeed.org/version/1.1","items":items});
        for item in [
            json!("no"),
            json!({"title":"no body"}),
            json!({"content_text":null}),
            json!({"content_text":"x","tags":[1]}),
        ] {
            assert!(parse(SOURCE, &feed(json!([item])), NOW).is_err());
        }
        let mut paged = feed(json!([]));
        paged["next_url"] = json!("https://example.org/second-page");
        assert!(parse(SOURCE, &paged, NOW).is_err());
        assert!(parse(SOURCE, &json!({"version":"other","items":[]}), NOW).is_err());
    }
}
