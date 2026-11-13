use crate::feed::{digest, item};
use chrono::{DateTime, FixedOffset, SecondsFormat};
use html5gum::{Token, Tokenizer};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use url::Url;

#[derive(Default)]
pub(crate) struct Entry {
    pub(crate) id: String,
    pub(crate) title: String,
    pub(crate) body: String,
    pub(crate) link: Option<Url>,
    pub(crate) author: String,
    pub(crate) tags: Vec<String>,
    pub(crate) date: String,
}

impl Entry {
    pub(crate) fn identity(&self, source: &str) -> String {
        let original = self.id.trim();
        if original.is_empty() {
            return self
                .link
                .as_ref()
                .map(ToString::to_string)
                .unwrap_or_else(|| {
                    format!(
                        "sha256:{}",
                        digest(&json!([source, self.title, self.body, self.author]))
                    )
                });
        }
        if original.chars().count() > 1024 {
            format!("sha256:{:x}", Sha256::digest(original.as_bytes()))
        } else {
            original.to_owned()
        }
    }

    pub(crate) fn project(self, id: String, now: &str) -> Value {
        let published = instant(self.date.trim())
            .map(|value| value.to_utc().to_rfc3339_opts(SecondsFormat::AutoSi, true));
        let mut projected = item(
            id,
            &self.title,
            &self.body,
            self.link.as_ref().map_or("", Url::as_str),
            published.as_deref().unwrap_or(now).to_owned(),
        );
        projected["published_at"] = json!(published);
        projected["author"] = json!(self.author.chars().take(300).collect::<String>());
        let mut seen = HashSet::new();
        projected["tags"] = json!(
            self.tags
                .into_iter()
                .map(|tag| { plain(&tag).chars().take(100).collect::<String>() })
                .filter(|tag| !tag.is_empty() && seen.insert(tag.clone()))
                .take(32)
                .collect::<Vec<_>>()
        );
        projected
    }
}

pub(crate) fn instant(value: &str) -> Option<DateTime<FixedOffset>> {
    DateTime::parse_from_rfc3339(value)
        .or_else(|_| DateTime::parse_from_rfc2822(value))
        .ok()
}

pub(crate) fn safe_link(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https")
        && url.has_host()
        && url.username().is_empty()
        && url.password().is_none()
        && url.as_str().len() <= 4096
}

pub(crate) fn resolve(base: &Url, raw: &str) -> Option<Url> {
    let raw = raw.trim();
    if raw.is_empty() || raw.len() > 4096 || raw.chars().any(char::is_control) {
        return None;
    }
    base.join(raw).ok().filter(safe_link)
}

pub(crate) fn plain(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub(crate) fn html(input: &str) -> String {
    let mut visible = String::new();
    let mut hidden = Vec::new();
    for token in Tokenizer::new(input).flatten() {
        match token {
            Token::StartTag(tag) => {
                let name = tag
                    .name
                    .rsplit(|byte| *byte == b':')
                    .next()
                    .unwrap_or_default();
                if matches!(name, b"script" | b"style" | b"noscript") {
                    hidden.push(tag.name);
                } else if hidden.is_empty()
                    && matches!(
                        name,
                        b"p" | b"div"
                            | b"br"
                            | b"li"
                            | b"ul"
                            | b"ol"
                            | b"blockquote"
                            | b"h1"
                            | b"h2"
                            | b"h3"
                            | b"tr"
                            | b"td"
                    )
                {
                    visible.push(' ');
                }
            }
            Token::EndTag(tag) => {
                if hidden.last() == Some(&tag.name) {
                    hidden.pop();
                } else if hidden.is_empty()
                    && matches!(
                        tag.name
                            .rsplit(|byte| *byte == b':')
                            .next()
                            .unwrap_or_default(),
                        b"p" | b"div" | b"li" | b"blockquote" | b"tr" | b"td"
                    )
                {
                    visible.push(' ');
                }
            }
            Token::String(text) if hidden.is_empty() => {
                visible.push_str(&String::from_utf8_lossy(&text))
            }
            _ => (),
        }
    }
    plain(&visible)
}
