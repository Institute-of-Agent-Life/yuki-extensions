use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    process::{Command, Stdio},
};

const BODY_LIMIT: usize = 1024 * 1024;
const HEADER_LIMIT: usize = 64 * 1024;
const FEED_ACCEPT: &str =
    "application/feed+json, application/atom+xml, application/rss+xml, application/xml, text/xml";

pub struct FeedResponse {
    pub body: Vec<u8>,
    pub validators: Value,
}

fn etag(value: &str) -> Option<&str> {
    let opaque = value
        .strip_prefix("W/")
        .unwrap_or(value)
        .strip_prefix('"')?
        .strip_suffix('"')?;
    (value.len() <= 2000 && opaque.bytes().all(|b| matches!(b, b'!' | b'#'..=b'~')))
        .then_some(value)
}

fn modified(value: &str) -> Option<&str> {
    (value.len() <= 40
        && value.bytes().all(|b| matches!(b, b' '..=b'~'))
        && chrono::DateTime::parse_from_rfc2822(value).is_ok())
    .then_some(value)
}

fn header<'a>(block: &'a [u8], name: &[u8]) -> Option<&'a str> {
    let mut lines = block
        .split(|&b| b == b'\n')
        .filter_map(|line| {
            let pos = line.iter().position(|&b| b == b':')?;
            Some((&line[..pos], &line[pos + 1..]))
        })
        .filter(|(key, _)| key.eq_ignore_ascii_case(name));
    let (_, value) = lines.next()?;
    if lines.next().is_some() {
        return None;
    }
    std::str::from_utf8(value.trim_ascii()).ok()
}

fn quoted(input: &mut impl Write, name: &str, value: &str) -> Result<(), String> {
    writeln!(
        input,
        "{name} = \"{}\"",
        value.replace('\\', "\\\\").replace('"', "\\\"")
    )
    .map_err(|_| "curl input failed".into())
}

fn request(
    config: &Value,
    url: &str,
    feed_headers: Option<[Option<&str>; 2]>,
) -> Result<Vec<u8>, String> {
    if !(url.starts_with("https://") || url.starts_with("http://127.0.0.1:"))
        || url.chars().any(char::is_control)
        || url.contains('@')
    {
        return Err("source endpoint requires HTTPS or explicit local service".into());
    }
    let mut command = Command::new("curl");
    command.args([
        "--disable",
        "--silent",
        "--fail",
        "--globoff",
        "--proto",
        "=http,https",
        "--max-time",
        "10",
        "--max-filesize",
        "1048576",
    ]);
    if feed_headers.is_some() {
        command.args([
            "--include",
            "--suppress-connect-headers",
            "--write-out",
            "\\n%{http_code} %{size_download}",
        ]);
    }
    let mut child = command
        .args(["--config", "-"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "curl unavailable")?;
    let result = (|| {
        let mut input = child.stdin.take().ok_or("curl pipe missing")?;
        quoted(&mut input, "url", url)?;
        if let Some(name) = config["token_env"].as_str() {
            let token = std::env::var(name).map_err(|_| "source credential unavailable")?;
            if token.chars().any(char::is_control) {
                return Err("invalid source credential".to_owned());
            }
            quoted(&mut input, "header", &format!("X-Auth-Token: {token}"))?;
        }
        if let Some([etag, modified]) = feed_headers {
            quoted(&mut input, "header", &format!("Accept: {FEED_ACCEPT}"))?;
            if let Some(tag) = etag {
                quoted(&mut input, "header", &format!("If-None-Match: {tag}"))?;
            }
            if let Some(date) = modified {
                quoted(&mut input, "header", &format!("If-Modified-Since: {date}"))?;
            }
        }
        drop(input);
        let limit = BODY_LIMIT + feed_headers.map_or(0, |_| HEADER_LIMIT);
        let mut raw = Vec::new();
        child
            .stdout
            .take()
            .ok_or("curl output missing")?
            .take((limit + 1) as u64)
            .read_to_end(&mut raw)
            .map_err(|_| "source read failed")?;
        if raw.len() > limit {
            return Err("source response too large".into());
        }
        if !child.wait().map_err(|_| "curl wait failed")?.success() {
            return Err("source HTTP observation failed".into());
        }
        Ok(raw)
    })();
    let _ = child.kill();
    let _ = child.wait();
    result
}

pub fn body(config: &Value, url: &str) -> Result<Vec<u8>, String> {
    request(config, url, None)
}

fn decode_feed(raw: &[u8], conditional: bool) -> Result<Option<FeedResponse>, String> {
    const INVALID: &str = "invalid feed HTTP response";
    // Curl appends the final status and body byte count after any trailers.
    let end = raw.iter().rposition(|&b| b == b'\n').ok_or(INVALID)?;
    let mut response = &raw[..end];
    let record = &raw[end + 1..];
    let (status, size) = std::str::from_utf8(record)
        .map_err(|_| INVALID)?
        .split_once(' ')
        .ok_or(INVALID)?;
    let size: usize = size.parse().map_err(|_| INVALID)?;
    if size > BODY_LIMIT {
        return Err("source response too large".into());
    }
    let headers = loop {
        let end = response
            .windows(4)
            .position(|b| b == b"\r\n\r\n")
            .ok_or(INVALID)?;
        let (headers, rest) = response.split_at(end);
        response = &rest[4..];
        let code = headers
            .split(|&b| b == b'\r')
            .next()
            .and_then(|line| line.strip_prefix(b"HTTP/"))
            .and_then(|line| line.split(|&b| b == b' ').nth(1))
            .ok_or(INVALID)?;
        if code == status.as_bytes() {
            break headers;
        }
        if code.len() != 3 || code[0] != b'1' {
            return Err(INVALID.into());
        }
    };
    let body = response.get(..size).ok_or(INVALID)?;
    if raw.len() - size > HEADER_LIMIT {
        return Err("source response too large".into());
    }
    match status {
        "304" if conditional && response.is_empty() => Ok(None),
        "304" => Err("unexpected not-modified feed response".into()),
        "200" => Ok(Some(FeedResponse {
            body: body.to_vec(),
            validators: json!({
                "etag":header(headers,b"etag").and_then(etag),
                "last_modified":header(headers,b"last-modified").and_then(modified)
            }),
        })),
        _ => Err("unexpected feed HTTP status".into()),
    }
}

pub fn feed(config: &Value, url: &str, validators: &Value) -> Result<Option<FeedResponse>, String> {
    let headers = [
        validators["etag"].as_str().and_then(etag),
        validators["last_modified"].as_str().and_then(modified),
    ];
    let raw = request(config, url, Some(headers))?;
    decode_feed(&raw, headers.iter().any(Option::is_some))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn final_headers_and_body_exclude_informational_headers_and_trailers() {
        let raw = b"HTTP/1.1 103 Early Hints\r\nETag: \"early\"\r\n\r\n\
                    HTTP/2 200\r\nETAG: W/\"current\"\r\nLast-Modified: Sun, 04 Jan 2026 00:00:00 GMT\r\n\
                    X-Other: \xff\r\n\r\nfeedETag: \"trailer\"\r\n\n200 4";
        let result = decode_feed(raw, false).unwrap().unwrap();
        assert_eq!(result.body, b"feed");
        assert_eq!(result.validators["etag"], "W/\"current\"");
        assert_eq!(
            result.validators["last_modified"],
            "Sun, 04 Jan 2026 00:00:00 GMT"
        );
    }

    #[test]
    fn missing_or_unsafe_validators_do_not_become_conditional_headers() {
        let raw = b"HTTP/1.0 200 OK\r\nETag: \"a\"\r\netag: \"b\"\r\n\
                    Last-Modified: not a date\r\n\r\nfeed\n200 4";
        let result = decode_feed(raw, false).unwrap().unwrap();
        assert_eq!(result.validators, json!({"etag":null,"last_modified":null}));
        assert_eq!(etag("*"), None);
        assert_eq!(etag("\"new\"\r\nX-Custom: foo"), None);
    }

    #[test]
    fn only_an_empty_conditional_304_and_a_complete_200_are_observations() {
        let untouched = b"HTTP/1.1 304 Not Modified\r\n\r\n\n304 0";
        assert!(decode_feed(untouched, true).unwrap().is_none());
        assert!(decode_feed(untouched, false).is_err());
        assert!(decode_feed(b"HTTP/1.1 304 Not Modified\r\n\r\nbody\n304 4", true).is_err());
        assert!(decode_feed(b"HTTP/1.1 206 Partial Content\r\n\r\nbody\n206 4", true).is_err());
        assert!(decode_feed(b"HTTP/1.1 200 OK\r\n\r\nbody\n200 5", true).is_err());
    }
}
