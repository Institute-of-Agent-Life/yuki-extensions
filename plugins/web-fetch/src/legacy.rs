use crate::{fetch, policy};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};
use url::{Host, Position, Url};

const DEFAULT_QUESTION: &str = "读取用户指定的网页";
const CACHE_AGE: Duration = Duration::from_secs(600);
const CACHE_ENTRIES: usize = 128;
const CACHE_RESULT_BYTES: usize = 32_768;

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

    fn key(&self) -> [u8; 32] {
        let mut digest = Sha256::new();
        digest.update(self.source_url.len().to_le_bytes());
        digest.update(&self.source_url);
        digest.update(&self.question);
        digest.finalize().into()
    }

    fn project(&self, text: &str) -> Value {
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

    pub(crate) fn read(&self, cache: &mut Cache) -> (Value, Option<String>) {
        if let Some(text) = cache.get(self.key(), Instant::now()) {
            return (self.project(text), None);
        }
        match fetch::read_text(&self.transport_url) {
            Ok(text) => (self.project(&text), Some(text)),
            Err(error) => (json!({"ok":false,"error":error}), None),
        }
    }

    pub(crate) fn remember(&self, cache: &mut Cache, result: &Value, text: String) {
        if result.to_string().len() <= CACHE_RESULT_BYTES {
            cache.insert(self.key(), text, Instant::now());
        }
    }
}

struct CachedPage {
    key: [u8; 32],
    expires: Instant,
    text: String,
}

#[derive(Default)]
pub(crate) struct Cache(VecDeque<CachedPage>);

impl Cache {
    fn get(&mut self, key: [u8; 32], now: Instant) -> Option<&str> {
        self.expire(now);
        self.0
            .iter()
            .find(|page| page.key == key)
            .map(|page| page.text.as_str())
    }

    fn insert(&mut self, key: [u8; 32], text: String, now: Instant) {
        self.expire(now);
        self.0.retain(|page| page.key != key);
        if self.0.len() == CACHE_ENTRIES {
            self.0.pop_front();
        }
        self.0.push_back(CachedPage {
            key,
            expires: now + CACHE_AGE,
            text,
        });
    }

    fn expire(&mut self, now: Instant) {
        while self.0.front().is_some_and(|page| page.expires <= now) {
            self.0.pop_front();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_bounds_are_fixed_from_the_original_read() {
        let mut cache = Cache::default();
        let now = Instant::now();
        let content = "original";
        for number in 0..=CACHE_ENTRIES {
            cache.insert([number as u8; 32], content.into(), now);
        }
        assert!(cache.get([0; 32], now).is_none());
        let key = [1; 32];
        assert_eq!(
            cache.get(key, now + CACHE_AGE - Duration::from_secs(1)),
            Some(content)
        );
        assert!(cache.get(key, now + CACHE_AGE).is_none());
        let request = Request::parse(&json!({"url":"https://example.com"})).unwrap();
        let large = "x".repeat(CACHE_RESULT_BYTES);
        request.remember(&mut cache, &request.project(&large), large);
        assert!(cache.get(request.key(), Instant::now()).is_none());
    }
}
