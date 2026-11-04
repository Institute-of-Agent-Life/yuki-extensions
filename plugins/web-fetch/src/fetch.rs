use crate::policy;
use html5gum::{Token, Tokenizer};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    env,
    io::{BufRead, BufReader, Read, Write},
    net::IpAddr,
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};
use url::Url;

const MAX_BYTES: usize = 2 * 1024 * 1024;
const MAX_HEADERS: usize = 128 * 1024;
type Result<T> = std::result::Result<T, &'static str>;

#[derive(Default)]
pub(crate) struct Request {
    headers: Vec<(String, String)>,
    body: Option<String>,
}

struct Hop {
    code: u16,
    headers: HashMap<String, String>,
    bytes: Vec<u8>,
    complete: bool,
}

struct Transfer(Child);
impl Drop for Transfer {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn config(out: &mut impl Write, key: &str, value: &str) -> Result<()> {
    if value.chars().any(char::is_control) {
        return Err("invalid_http_parameter");
    }
    let value = value.replace('\\', "\\\\").replace('"', "\\\"");
    writeln!(out, "{key} = \"{value}\"").map_err(|_| "transport_failed")
}

fn transfer(
    url: &Url,
    ip: IpAddr,
    request: &Request,
    timeout: Duration,
    proxy: &str,
    bypass: &str,
) -> Result<Hop> {
    let host = url.host_str().ok_or("invalid_url")?;
    let port = url.port_or_known_default().ok_or("invalid_url")?;
    let addr = match ip {
        IpAddr::V6(v) => format!("[{v}]"),
        IpAddr::V4(v) => v.to_string(),
    };
    let mut command = Command::new("curl");
    command.args([
        "--disable",
        "--silent",
        "--globoff",
        "--proto",
        "=http,https",
        "--suppress-connect-headers",
        "--proxytunnel",
        "--dump-header",
        "-",
        "--config",
        "-",
    ]);
    let mut proc = Transfer(
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| "curl_unavailable")?,
    );
    {
        let mut stdin = proc.0.stdin.take().ok_or("transport_failed")?;
        config(&mut stdin, "url", url.as_str())?;
        config(
            &mut stdin,
            "connect-to",
            &format!("{host}:{port}:{addr}:{port}"),
        )?;
        config(
            &mut stdin,
            "max-time",
            &format!("{:.3}", timeout.as_secs_f64().max(0.001)),
        )?;
        config(&mut stdin, "proxy", proxy)?;
        config(&mut stdin, "noproxy", bypass)?;
        for (key, value) in &request.headers {
            config(&mut stdin, "header", &format!("{key}: {value}"))?;
        }
        if let Some(body) = &request.body {
            config(&mut stdin, "data-raw", body)?;
        }
    }
    let mut stream = BufReader::new(proc.0.stdout.take().ok_or("transport_failed")?);
    let mut total = 0;
    let mut line = || -> Result<String> {
        let mut bytes = Vec::new();
        let got = (&mut stream)
            .take((MAX_HEADERS - total + 1) as u64)
            .read_until(b'\n', &mut bytes)
            .map_err(|_| "transport_failed")?;
        total += got;
        if got == 0 {
            return Err("transport_failed");
        }
        if total > MAX_HEADERS {
            return Err("headers_too_large");
        }
        Ok(String::from_utf8_lossy(&bytes)
            .trim_end_matches(['\r', '\n'])
            .to_string())
    };
    let (code, headers) = loop {
        let status = line()?;
        if !status.starts_with("HTTP/") {
            return Err("invalid_http_response");
        }
        let code = status
            .split_ascii_whitespace()
            .nth(1)
            .and_then(|s| s.parse::<u16>().ok())
            .ok_or("invalid_http_response")?;
        let mut headers = HashMap::new();
        loop {
            let row = line()?;
            if row.is_empty() {
                break;
            }
            let (key, value) = row.split_once(':').ok_or("invalid_http_response")?;
            let key = key.to_ascii_lowercase();
            if headers
                .insert(key.clone(), value.trim().to_string())
                .is_some()
                && key == "location"
            {
                return Err("ambiguous_redirect");
            }
        }
        if !(100..200).contains(&code) {
            break (code, headers);
        }
    };
    let mut bytes = Vec::new();
    stream
        .take((MAX_BYTES + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(|_| "transport_failed")?;
    let complete = bytes.len() <= MAX_BYTES;
    if complete && !proc.0.wait().map_err(|_| "transport_failed")?.success() {
        return Err("transport_failed");
    }
    bytes.truncate(MAX_BYTES);
    Ok(Hop {
        code,
        headers,
        bytes,
        complete,
    })
}

fn text(bytes: &[u8], html: bool) -> String {
    let source = String::from_utf8_lossy(bytes);
    let mut parts = Vec::new();
    if html {
        let mut hidden = Vec::new();
        for token in Tokenizer::new(source.as_ref()).flatten() {
            match token {
                Token::StartTag(t)
                    if matches!(t.name.as_ref(), b"script" | b"style" | b"noscript") =>
                {
                    hidden.push(t.name)
                }
                Token::EndTag(t) if hidden.last() == Some(&t.name) => {
                    hidden.pop();
                }
                Token::String(s) if hidden.is_empty() => {
                    parts.push(String::from_utf8_lossy(&s).into_owned())
                }
                _ => {}
            }
        }
    } else {
        parts.push(source.into_owned());
    }
    parts
        .iter()
        .flat_map(|s| s.lines())
        .map(|s| s.split_whitespace().collect::<Vec<_>>().join(" "))
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join("\n")
}

fn result(source: &Url, url: &Url, hop: Hop) -> Value {
    let mime = hop.headers.get("content-type").map(|s| {
        s.split(';')
            .next()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase()
    });
    let mut data = json!({"source":source.as_str(),"url":url.as_str(),"status":hop.code,
        "content_type":mime,"etag":hop.headers.get("etag"),"observed_bytes":hop.bytes.len(),
        "original_complete":hop.complete,"observed_sha256":format!("{:x}",Sha256::digest(&hop.bytes))});
    if hop.code == 304 {
        data["state"] = "not_modified".into();
        return data;
    }
    if !(200..300).contains(&hop.code) {
        data["state"] = "http_error".into();
        return data;
    }
    if !matches!(
        mime.as_deref(),
        Some("text/plain" | "text/html" | "application/xhtml+xml")
    ) {
        data["state"] = "unsupported_content_type".into();
        return data;
    }
    let content = text(&hop.bytes, mime.as_deref() != Some("text/plain"));
    if content.is_empty() {
        data["state"] = "empty_page".into();
        return data;
    }
    data["text"] = Value::String(content);
    if hop.complete && hop.bytes.len() <= 8192 {
        data["original_hex"] =
            Value::String(hop.bytes.iter().map(|v| format!("{v:02x}")).collect());
    }
    // Respect the negotiated frame budget even with JSON-escaped characters.
    let mut partial = !hop.complete;
    while serde_json::to_vec(&data).expect("JSON value").len() > 58_000 {
        let s = data["text"].as_str().unwrap();
        if s.is_empty() {
            break;
        }
        let mut end = s.len() * 3 / 4;
        while !s.is_char_boundary(end) {
            end -= 1;
        }
        data["text"] = s[..end].into();
        partial = true;
    }
    data["state"] = if partial { "partial" } else { "read" }.into();
    data
}

fn follow(
    source: &str,
    mut request: Request,
    resolve: impl Fn(&Url) -> Result<Vec<IpAddr>>,
    exchange: impl Fn(&Url, IpAddr, &Request, Duration) -> Result<Hop>,
) -> Value {
    let original = match policy::url(source) {
        Ok(url) => url,
        Err(e) => return json!({"state":e}),
    };
    let mut current = original.clone();
    let mut seen: HashMap<String, Vec<IpAddr>> = HashMap::new();
    let deadline = Instant::now() + Duration::from_secs(20);
    for _ in 0..=5 {
        let outcome = (|| -> Result<Hop> {
            let ips = resolve(&current)?;
            let key = current
                .host_str()
                .ok_or("invalid_url")?
                .to_ascii_lowercase();
            if seen.insert(key, ips.clone()).is_some_and(|old| old != ips) {
                return Err("dns_changed");
            }
            let remaining = deadline
                .checked_duration_since(Instant::now())
                .ok_or("deadline")?;
            exchange(&current, ips[0], &request, remaining)
        })();
        let hop = match outcome {
            Ok(value) => value,
            Err(e) => return json!({"source":original.as_str(),"url":current.as_str(),"state":e}),
        };
        if !matches!(hop.code, 301 | 302 | 303 | 307 | 308) {
            return result(&original, &current, hop);
        }
        let next = hop
            .headers
            .get("location")
            .and_then(|raw| current.join(raw).ok())
            .and_then(|v| policy::url(v.as_str()).ok());
        let Some(next) = next else {
            return json!({"source":original.as_str(),"url":current.as_str(),"status":hop.code,"state":"invalid_redirect"});
        };
        if current.origin() != next.origin() {
            request = Request::default();
        }
        current = next;
    }
    json!({"source":original.as_str(),"url":current.as_str(),"state":"redirect_limit"})
}

pub(crate) fn read(source: &str) -> Value {
    follow(
        source,
        Request::default(),
        policy::resolve,
        |url, ip, request, timeout| {
            let keys = if url.scheme() == "https" {
                ["YUKI_WEB_FETCH_HTTPS_PROXY", "https_proxy", "HTTPS_PROXY"]
            } else {
                ["YUKI_WEB_FETCH_HTTP_PROXY", "http_proxy", "HTTP_PROXY"]
            };
            let proxy = keys
                .into_iter()
                .chain(["YUKI_WEB_FETCH_ALL_PROXY", "all_proxy", "ALL_PROXY"])
                .find_map(|key| env::var(key).ok())
                .unwrap_or_default();
            let bypass = env::var("YUKI_WEB_FETCH_NO_PROXY")
                .or_else(|_| env::var("no_proxy"))
                .or_else(|_| env::var("NO_PROXY"))
                .unwrap_or_default();
            transfer(url, ip, request, timeout, &proxy, &bypass)
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::BufReader,
        net::{TcpListener, TcpStream},
        thread,
    };

    struct Seen {
        connect: String,
        head: String,
        body: Vec<u8>,
    }

    fn witness(name: &str, details: &Value) {
        if let Some(dir) = env::var_os("YUKI_UNIT_TEST_EVIDENCE") {
            std::fs::write(
                std::path::Path::new(&dir).join(format!("{name}.json")),
                serde_json::to_vec_pretty(details).unwrap(),
            )
            .unwrap();
        }
    }

    fn record(socket: TcpStream, reply: &str) -> Seen {
        socket.set_nonblocking(false).unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(8)))
            .unwrap();
        let mut input = BufReader::new(socket);
        let headers = |s: &mut BufReader<TcpStream>| {
            let mut h = String::new();
            loop {
                let mut line = String::new();
                assert!(s.read_line(&mut line).unwrap() > 0);
                if line == "\r\n" {
                    break;
                }
                h.push_str(&line);
            }
            h
        };
        let connect = headers(&mut input);
        input
            .get_mut()
            .write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
            .unwrap();
        let head = headers(&mut input);
        let n = head
            .lines()
            .filter_map(|l| l.split_once(':'))
            .find(|(k, _)| k.eq_ignore_ascii_case("Content-Length"))
            .map(|(_, v)| v.trim().parse::<usize>().unwrap())
            .unwrap_or(0);
        let mut body = vec![0; n];
        input.read_exact(&mut body).unwrap();
        input.get_mut().write_all(reply.as_bytes()).unwrap();
        Seen {
            connect,
            head,
            body,
        }
    }

    fn through_proxy(url: &str, request: Request, replies: Vec<String>) -> (Value, Vec<Seen>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let proxy = format!("http://{}", listener.local_addr().unwrap());
        let peer = thread::spawn(move || {
            replies
                .into_iter()
                .map(|reply| {
                    // Bound accept as well as reads, so a transport regression cannot hang CI.
                    listener.set_nonblocking(true).unwrap();
                    let deadline = Instant::now() + Duration::from_secs(8);
                    loop {
                        match listener.accept() {
                            Ok((socket, _)) => break record(socket, &reply),
                            Err(e)
                                if e.kind() == std::io::ErrorKind::WouldBlock
                                    && Instant::now() < deadline =>
                            {
                                thread::sleep(Duration::from_millis(10))
                            }
                            other => panic!("missing proxy connection: {other:?}"),
                        }
                    }
                })
                .collect()
        });
        let data = follow(url, request, policy::resolve, |u, i, r, t| {
            transfer(u, i, r, t, &proxy, "")
        });
        (data, peer.join().unwrap())
    }

    fn redirect(url: &str) -> String {
        format!(
            "HTTP/1.1 307 Temporary Redirect\r\nLocation: {url}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )
    }

    #[test]
    fn cross_origin_never_restores_credentials_or_body() {
        for other in ["93.184.216.35:8100", "93.184.216.34:8200"] {
            let a = "93.184.216.34:8100";
            let url = format!("http://{a}/start");
            let html = "<html><style>hide</style><p>A &amp; B</p><script>secret</script></html>";
            let (data, trace) = through_proxy(
                &url,
                Request {
                    headers: vec![
                        ("Authorization".into(), "Bearer fixture".into()),
                        ("X-Private".into(), "first".into()),
                    ],
                    body: Some("one-body".into()),
                },
                vec![
                    redirect(&format!("http://{other}/second")),
                    redirect(&format!("http://{a}/last")),
                    format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{html}",
                        html.len()
                    ),
                ],
            );
            assert_eq!(data["state"], "read");
            assert_eq!(data["text"], "A & B");
            assert_eq!(trace.len(), 3);
            let facts: Vec<_> = trace
                .iter()
                .map(|hop| {
                    json!({"connect":hop.connect,"headers":hop.head,
                "body":String::from_utf8_lossy(&hop.body)})
                })
                .collect();
            let label = if other.ends_with("8200") {
                "R07-port"
            } else {
                "R07-host"
            };
            witness(label, &json!({"source":url,"hops":facts,"result":data}));
            for (i, hop) in trace.iter().enumerate() {
                let expected = if i == 1 { other } else { a };
                assert!(hop.connect.starts_with(&format!("CONNECT {expected} ")));
                assert!(hop.head.contains(&format!("Host: {expected}")));
                assert_eq!(hop.head.contains("Authorization: Bearer fixture"), i == 0);
                assert_eq!(hop.head.contains("X-Private: first"), i == 0);
                assert_eq!(
                    hop.body,
                    if i == 0 {
                        b"one-body".to_vec()
                    } else {
                        Vec::new()
                    }
                );
            }
        }
    }

    #[test]
    fn denied_redirect_and_not_modified_are_distinct() {
        let url = "http://93.184.216.34:8100/resource";
        let (denied, trace) = through_proxy(
            url,
            Request::default(),
            vec![redirect("http://127.0.0.1/hidden")],
        );
        assert_eq!(denied["state"], "destination_denied");
        assert_eq!(trace.len(), 1);
        let (cached, _) = through_proxy(
            url,
            Request::default(),
            vec![
                "HTTP/1.1 304 Not Modified\r\nETag: fixture-tag\r\nConnection: close\r\n\r\n"
                    .into(),
            ],
        );
        assert_eq!(cached["state"], "not_modified");
        assert_eq!(cached["etag"], "fixture-tag");
        assert!(cached.get("text").is_none());
        witness(
            "R07-denied-and-304",
            &json!({"denied":denied,"not_modified":cached}),
        );
    }

    #[test]
    fn rebinding_fails_before_second_dispatch_and_keeps_source() {
        use std::cell::Cell;
        let count = Cell::new(0);
        let result = follow(
            "http://example.org/path",
            Request::default(),
            |_| {
                let n = count.get();
                count.set(n + 1);
                Ok(vec![
                    if n == 0 {
                        "93.184.216.34"
                    } else {
                        "93.184.216.35"
                    }
                    .parse()
                    .unwrap(),
                ])
            },
            |_, ip, _, _| {
                assert_eq!(ip, "93.184.216.34".parse::<IpAddr>().unwrap());
                Ok(Hop {
                    code: 302,
                    headers: HashMap::from([("location".into(), "/again".into())]),
                    bytes: vec![],
                    complete: true,
                })
            },
        );
        assert_eq!(result["state"], "dns_changed");
        assert_eq!(result["source"], "http://example.org/path");
    }

    #[test]
    fn bounded_result_preserves_source_and_hash_even_when_text_exceeds_frame() {
        let source = Url::parse("https://example.org/large").unwrap();
        let body = "正文".repeat(20000).into_bytes();
        let output = result(
            &source,
            &source,
            Hop {
                code: 200,
                headers: HashMap::from([("content-type".into(), "text/plain".into())]),
                bytes: body.clone(),
                complete: true,
            },
        );
        assert_eq!(output["state"], "partial");
        assert_eq!(
            output["observed_sha256"],
            format!("{:x}", Sha256::digest(&body))
        );
        assert_eq!(output["source"], source.as_str());
        assert!(serde_json::to_vec(&output).unwrap().len() < 65536);
    }

    #[test]
    fn failed_proxy_does_not_make_a_direct_connection() {
        let target = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = target.local_addr().unwrap();
        let refused = TcpListener::bind("127.0.0.1:0").unwrap();
        let proxy = format!("http://{}", refused.local_addr().unwrap());
        drop(refused);
        let url = Url::parse(&format!("http://example.test:{}/page", addr.port())).unwrap();
        let result = transfer(
            &url,
            addr.ip(),
            &Request::default(),
            Duration::from_secs(3),
            &proxy,
            "",
        );
        assert!(result.is_err());
        target.set_nonblocking(true).unwrap();
        assert_eq!(
            target.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
        witness(
            "failed-proxy",
            &json!({"direct_connections":0,"error":result.err()}),
        );
    }
}
