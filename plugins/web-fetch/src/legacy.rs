use crate::{fetch, policy};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use url::{Host, Position, Url};

const DEFAULT_QUESTION: &str = "读取用户指定的网页";

pub(crate) struct Request {
    transport_url: Url,
    source_url: String,
    question: String,
}

impl Request {
    pub(crate) fn parse(arguments: &Value) -> Result<Self, &'static str> {
        let input = arguments["url"].as_str().ok_or("invalid_url")?.trim();
        let (_, location) = input.split_once("://").ok_or("invalid_url")?;
        let authority_end = location.find(['/', '?', '#']).unwrap_or(location.len());
        let (authority, tail) = location.split_at(authority_end);
        if authority.is_empty() || authority.contains(['@', '\\']) {
            return Err("invalid_url");
        }
        let mut transport_url = policy::url(input).map_err(|_| "invalid_url")?;
        match transport_url.host().ok_or("invalid_url")? {
            Host::Domain(domain) => {
                let domain = domain.trim_end_matches('.');
                if !domain.contains('.')
                    || [
                        ".localhost",
                        ".local",
                        ".internal",
                        ".lan",
                        ".home",
                        ".docker",
                    ]
                    .iter()
                    .any(|suffix| domain.ends_with(suffix))
                {
                    return Err("private_url");
                }
                let domain = domain.to_owned();
                transport_url
                    .set_host(Some(&domain))
                    .map_err(|_| "invalid_url")?;
            }
            Host::Ipv4(address) if !policy::public(address.into()) => return Err("private_url"),
            Host::Ipv6(address) if !policy::public(address.into()) => return Err("private_url"),
            _ => {}
        }
        let question = match &arguments["question"] {
            Value::Null => DEFAULT_QUESTION,
            Value::String(value) if value.is_empty() => DEFAULT_QUESTION,
            Value::String(value) => value,
            _ => return Err("invalid_question"),
        }
        .split(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
        .filter(|word| !word.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        if question.is_empty() {
            return Err("invalid_question");
        }

        // v4 keys the source on the original path and query, before HTTP encoding.
        let tail = tail
            .split('#')
            .next()
            .unwrap_or("")
            .replace(['\t', '\r', '\n'], "");
        let (path, query) = tail.split_once('?').unwrap_or((&tail, ""));
        let mut source_url = transport_url[..Position::BeforePath].to_owned();
        source_url.push_str(if path.is_empty() { "/" } else { path });
        if !query.is_empty() {
            source_url.push('?');
            source_url.push_str(query);
        }
        Ok(Self {
            transport_url,
            source_url,
            question,
        })
    }

    pub(crate) fn read(&self) -> Value {
        let text = match fetch::read_text(&self.transport_url) {
            Ok(text) => text,
            Err(error) => return json!({"ok":false,"error":error}),
        };
        let domain = self
            .transport_url
            .host_str()
            .expect("public URL host")
            .trim_matches(['[', ']']);
        let key = format!("{}\x1f{}", self.source_url, self.question);
        let digest = format!("{:x}", Sha256::digest(key.as_bytes()));
        json!({"ok":true,"data":{
            "query":self.question,
            "partial_failure":false,
            "sources":[{
                "source_id": &digest[..24],
                "title":domain,
                "url":self.source_url,
                "domain":domain,
                "snippet":text,
                "relevant_content":text,
                "published_at":null,
                "provider_score":null,
            }],
        }})
    }
}
