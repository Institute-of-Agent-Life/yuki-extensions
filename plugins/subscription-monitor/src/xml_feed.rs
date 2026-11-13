use crate::feed::{Result, digest, item};
use chrono::{DateTime, FixedOffset, SecondsFormat};
use html5gum::{Token, Tokenizer};
use roxmltree::{Document, ExpandedName, NS_XML_URI, Node, ParsingOptions};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use url::Url;

const ATOM: &str = "http://www.w3.org/2005/Atom";
const CONTENT: &str = "http://purl.org/rss/1.0/modules/content/";
const DC: &str = "http://purl.org/dc/elements/1.1/";

pub(crate) fn parse(source: &str, bytes: &[u8], now: &str) -> Result<Vec<Value>> {
    if bytes.len() > 1024 * 1024 {
        return Err("XML feed exceeds 1 MiB".into());
    }
    let base = Url::parse(source)
        .ok()
        .filter(safe_link)
        .ok_or("invalid feed URL")?;
    let body = std::str::from_utf8(bytes)
        .map_err(|_| "XML feed must be UTF-8")?
        .trim_start_matches(['\u{feff}', ' ', '\t', '\r', '\n']);
    let document = Document::parse_with_options(
        body,
        ParsingOptions {
            allow_dtd: false,
            entity_resolver: None,
            nodes_limit: 100_000,
        },
    )
    .map_err(|_| "malformed or unsupported XML feed")?;
    let root = document.root_element();
    let entries = if root.tag_name().namespace().is_none()
        && root.has_tag_name("rss")
        && root
            .attribute("version")
            .is_none_or(|version| version == "2.0")
    {
        rss(root, &base)?
    } else if root.has_tag_name((ATOM, "feed")) {
        atom(root, &base)
    } else {
        return Err("expected RSS 2.0 or Atom feed".into());
    };
    let mut seen = HashSet::new();
    Ok(entries
        .into_iter()
        .filter_map(|entry| {
            let id = entry.identity(source);
            seen.insert(id.clone()).then(|| entry.project(id, now))
        })
        .collect())
}

#[derive(Default)]
struct Entry {
    id: String,
    title: String,
    body: String,
    link: Option<Url>,
    author: String,
    tags: Vec<String>,
    date: String,
}

impl Entry {
    fn identity(&self, source: &str) -> String {
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

    fn project(self, id: String, now: &str) -> Value {
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

fn rss(root: Node<'_, '_>, source: &Url) -> Result<Vec<Entry>> {
    let channel = child(root, "channel").ok_or("RSS feed is missing its channel")?;
    let base = xml_base(channel, &xml_base(root, source));
    Ok(channel
        .children()
        .filter(|node| node.has_tag_name("item") && node.tag_name().namespace().is_none())
        .map(|node| {
            let base = xml_base(node, &base);
            let guid = child(node, "guid");
            let id = text(guid);
            let link = resolve(&base, &text(child(node, "link"))).or_else(|| {
                guid.filter(|guid| {
                    guid.attribute("isPermaLink")
                        .unwrap_or("true")
                        .eq_ignore_ascii_case("true")
                })
                .and_then(|_| resolve(&base, &id))
            });
            let author = child(node, "author").or_else(|| child(node, (DC, "creator")));
            Entry {
                id,
                link,
                title: html(&text(child(node, "title"))),
                body: content(
                    child(node, (CONTENT, "encoded")).or_else(|| child(node, "description")),
                    "html",
                ),
                author: html(&text(author)),
                tags: node
                    .children()
                    .filter(|child| {
                        child.has_tag_name("category") && child.tag_name().namespace().is_none()
                    })
                    .map(|tag| text(Some(tag)))
                    .collect(),
                date: text(child(node, "pubDate").or_else(|| child(node, (DC, "date")))),
            }
        })
        .collect())
}

fn atom(root: Node<'_, '_>, source: &Url) -> Vec<Entry> {
    let base = xml_base(root, source);
    root.children()
        .filter(|node| node.has_tag_name((ATOM, "entry")))
        .map(|node| {
            let base = xml_base(node, &base);
            let link = node
                .children()
                .filter(|link| {
                    link.has_tag_name((ATOM, "link"))
                        && link.attribute("rel").is_none_or(|rel| rel == "alternate")
                })
                .filter_map(|link| {
                    resolve(&xml_base(link, &base), link.attribute("href")?).map(|url| {
                        (
                            link.attribute("type")
                                .is_some_and(|mime| mime != "text/html"),
                            url,
                        )
                    })
                })
                .min_by_key(|(other_media, _)| *other_media)
                .map(|(_, link)| link);
            let author = child(node, (ATOM, "author"))
                .and_then(|author| child(author, (ATOM, "name")))
                .or_else(|| {
                    child(root, (ATOM, "author")).and_then(|author| child(author, (ATOM, "name")))
                });
            Entry {
                id: text(child(node, (ATOM, "id"))),
                link,
                title: content(child(node, (ATOM, "title")), "text"),
                body: content(
                    child(node, (ATOM, "content")).or_else(|| child(node, (ATOM, "summary"))),
                    "text",
                ),
                author: plain(&text(author)),
                tags: node
                    .children()
                    .filter(|tag| tag.has_tag_name((ATOM, "category")))
                    .filter_map(|tag| tag.attribute("term").map(str::to_owned))
                    .collect(),
                date: text(
                    child(node, (ATOM, "published")).or_else(|| child(node, (ATOM, "updated"))),
                ),
            }
        })
        .collect()
}

fn child<'a, 'input>(
    node: Node<'a, 'input>,
    tag: impl Into<ExpandedName<'a, 'input>>,
) -> Option<Node<'a, 'input>> {
    let tag = tag.into();
    node.children()
        .find(|child| child.is_element() && child.tag_name() == tag)
}

fn text(node: Option<Node<'_, '_>>) -> String {
    node.into_iter()
        .flat_map(|node| node.descendants())
        .filter(|node| node.is_text())
        .filter_map(|node| node.text())
        .collect()
}

fn xml_base(node: Node<'_, '_>, parent: &Url) -> Url {
    node.attribute((NS_XML_URI, "base"))
        .and_then(|value| resolve(parent, value))
        .unwrap_or_else(|| parent.clone())
}

fn safe_link(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https")
        && url.has_host()
        && url.username().is_empty()
        && url.password().is_none()
        && url.as_str().len() <= 4096
}

fn resolve(base: &Url, raw: &str) -> Option<Url> {
    let raw = raw.trim();
    if raw.is_empty() || raw.len() > 4096 || raw.chars().any(char::is_control) {
        return None;
    }
    base.join(raw).ok().filter(safe_link)
}

fn content(node: Option<Node<'_, '_>>, default_type: &str) -> String {
    let Some(node) = node else {
        return String::new();
    };
    if node.children().any(|child| child.is_element()) {
        return html(&node.document().input_text()[node.range()]);
    }
    let raw = text(Some(node));
    if node.attribute("type").unwrap_or(default_type) == "text" {
        plain(&raw)
    } else {
        html(&raw)
    }
}

fn plain(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn html(input: &str) -> String {
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

#[cfg(test)]
mod tests {
    use super::*;

    const SOURCE: &str = "https://example.com/feeds/main.xml";
    const NOW: &str = "2026-11-13T00:00:00Z";

    #[test]
    fn rss_keeps_first_identity_and_uses_original_html_and_date() {
        let input = br#"<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
            <channel><item><guid isPermaLink="false">new</guid><title>News &amp; updates</title>
            <link>../posts/new</link><pubDate>Tue, 22 Sep 2026 14:00:00 +0800</pubDate>
            <description>short</description><content:encoded><![CDATA[<p>Hello <b>world</b></p>
            <script>quiet()</script><style>body{}</style><p>Next &amp; last.</p>]]></content:encoded>
            <author>Editor</author><category>news</category><category>news</category></item>
            <item><guid>new</guid><title>Conflicting duplicate</title></item>
            <item><guid>https://example.com/older</guid><title>Older</title></item>
            </channel></rss>"#;
        let entries = parse(SOURCE, input, NOW).unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0]["id"], "new");
        assert_eq!(entries[0]["title"], "News & updates");
        assert_eq!(entries[0]["body"], "Hello world Next & last.");
        assert_eq!(entries[0]["url"], "https://example.com/posts/new");
        assert_eq!(entries[0]["published_at"], "2026-09-22T06:00:00Z");
        assert_eq!(entries[0]["author"], "Editor");
        assert_eq!(entries[0]["tags"], json!(["news"]));
        assert_eq!(entries[1]["url"], "https://example.com/older");
    }

    #[test]
    fn atom_resolves_nested_base_and_distinguishes_text_from_xhtml() {
        let input = br#"<feed xmlns="http://www.w3.org/2005/Atom" xml:base="../">
            <author><name>Team</name></author><entry xml:base="posts/">
            <id>tag:example.com,2026:post-1</id><title>&lt;b&gt;Literal&lt;/b&gt;</title>
            <link rel="self" href="https://api.example.com/1"/>
            <link rel="alternate" type="text/plain" href="1.txt"/>
            <link rel="alternate" type="text/html" href="1"/>
            <content type="xhtml"><x:div xmlns:x="http://www.w3.org/1999/xhtml">
            <x:p>First</x:p><x:p>Second</x:p></x:div></content>
            <updated>2026-09-22T10:01:02+08:00</updated><category term="release"/>
            </entry></feed>"#;
        let entries = parse(SOURCE, input, NOW).unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0]["id"], "tag:example.com,2026:post-1");
        assert_eq!(entries[0]["title"], "<b>Literal</b>");
        assert_eq!(entries[0]["body"], "First Second");
        assert_eq!(entries[0]["url"], "https://example.com/posts/1");
        assert_eq!(entries[0]["published_at"], "2026-09-22T02:01:02Z");
        assert_eq!(entries[0]["author"], "Team");
        assert_eq!(entries[0]["tags"], json!(["release"]));
    }

    #[test]
    fn missing_dates_and_links_preserve_identity_and_unknown_source_time() {
        let a = "x".repeat(4100) + "a";
        let b = "x".repeat(4100) + "b";
        let body = format!(
            r#"<rss><channel>
            <item><link>../post</link><title>Linked</title></item>
            <item><link>ftp://example.com/post</link><description>{a}</description>
              <pubDate>2026-09-22T06:00:00</pubDate></item>
            <item><link>https://someone@example.com/post</link><description>{b}</description></item>
            </channel></rss>"#
        );
        let first = parse(SOURCE, body.as_bytes(), NOW).unwrap();
        let later = parse(SOURCE, body.as_bytes(), "2026-11-14T00:00:00Z").unwrap();
        assert_eq!(first[0]["id"], "https://example.com/post");
        assert_eq!(first[1]["body"], first[2]["body"]);
        assert_ne!(first[1]["id"], first[2]["id"]);
        for index in 1..3 {
            assert_eq!(first[index]["url"], "");
            assert_eq!(first[index]["published_at"], Value::Null);
            assert_eq!(first[index]["occurred_at"], NOW);
            assert_eq!(first[index]["id"], later[index]["id"]);
        }
    }

    #[test]
    fn rejects_incomplete_or_unsupported_documents_and_keeps_large_valid_feeds() {
        for invalid in [
            "<!DOCTYPE rss><rss><channel/></rss>",
            "<rss><channel>",
            "<rss version=\"1.0\"><channel/></rss>",
            "<feed/>",
            "<html><body>Not a feed</body></html>",
        ] {
            assert!(parse(SOURCE, invalid.as_bytes(), NOW).is_err(), "{invalid}");
        }
        assert!(parse(SOURCE, &vec![b' '; 1024 * 1024 + 1], NOW).is_err());
        let body = (0..201)
            .map(|id| format!("<item><guid isPermaLink=\"false\">item-{id}</guid></item>"))
            .collect::<String>();
        let body = format!("<rss><channel>{body}</channel></rss>");
        let entries = parse(SOURCE, body.as_bytes(), NOW).unwrap();
        assert_eq!(entries.len(), 201);
        assert_eq!(entries.last().unwrap()["id"], "item-200");
    }
}
