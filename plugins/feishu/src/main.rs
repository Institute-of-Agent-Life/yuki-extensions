mod host;
mod ingress;
mod ws;

use data_encoding::BASE64;
use host::Host;
use native_tls::TlsConnector;
use percent_encoding::percent_decode_str;
use prost::Message as Proto;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::{
    env,
    io::{self, BufRead, BufReader, Read, Write},
    net::{TcpStream, ToSocketAddrs},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket, client_tls_with_config, protocol::WebSocketConfig};
use url::Url;
use ws::{Assembler, Frame};
type Error = Box<dyn std::error::Error>;
trait Stream: Read + Write {}
impl<T: Read + Write> Stream for T {}
type Socket = WebSocket<MaybeTlsStream<Box<dyn Stream>>>;

struct Config {
    app: String,
    secret: String,
    tenant: String,
    domain: String,
    base: Url,
    proxy: Option<Url>,
}
impl Config {
    fn load() -> Result<Self, Error> {
        let domain = env::var("YUKI_FEISHU_DOMAIN")?;
        let official = match domain.as_str() {
            "feishu" => "https://open.feishu.cn",
            "lark" => "https://open.larksuite.com",
            _ => return Err("invalid Feishu/Lark domain".into()),
        };
        let base = Url::parse(&env::var("YUKI_FEISHU_API").unwrap_or_else(|_| official.into()))?;
        if base.as_str() != format!("{official}/")
            && !(base.scheme() == "http"
                && base.host_str() == Some("127.0.0.1")
                && base.port().is_some()
                && base.path() == "/"
                && base.query().is_none()
                && base.fragment().is_none()
                && base.username().is_empty()
                && base.password().is_none())
        {
            return Err("API endpoint outside configured domain".into());
        }
        let app = env::var("YUKI_FEISHU_APP_ID")?;
        let secret = env::var("YUKI_FEISHU_APP_SECRET")?;
        let tenant = env::var("YUKI_FEISHU_TENANT")?;
        if [app.as_str(), secret.as_str(), tenant.as_str()]
            .iter()
            .any(|v| v.trim().is_empty())
        {
            return Err("missing platform identity".into());
        }
        let proxy = env::var("YUKI_FEISHU_PROXY")
            .ok()
            .filter(|v| !v.is_empty())
            .map(|v| Url::parse(&v))
            .transpose()?;
        if proxy.as_ref().is_some_and(|p| {
            !matches!(p.scheme(), "http" | "https")
                || p.host().is_none()
                || p.query().is_some()
                || p.fragment().is_some()
        }) {
            return Err("unsupported configured proxy".into());
        }
        Ok(Self {
            app,
            secret,
            tenant,
            domain,
            base,
            proxy,
        })
    }

    fn endpoint(&self) -> Result<Value, Error> {
        let url = self.base.join("callback/ws/endpoint")?;
        let payload = json!({"AppID":self.app,"AppSecret":self.secret});
        let mut cmd = Command::new("curl");
        cmd.args([
            "--disable",
            "--silent",
            "--max-time",
            "12",
            "--header",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ]);
        // No fallback to another tenant or domain. Proxy credentials stay in the environment.
        if let Some(p) = &self.proxy {
            cmd.env("https_proxy", p.as_str())
                .env("http_proxy", p.as_str())
                .env("no_proxy", "");
        } else {
            cmd.args(["--noproxy", "*"]);
        }
        let mut child = cmd
            .arg(url.as_str())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;
        child
            .stdin
            .take()
            .ok_or("missing pipe")?
            .write_all(payload.to_string().as_bytes())?;
        let out = child.wait_with_output()?;
        if !out.status.success() {
            return Err("endpoint transport unavailable".into());
        }
        let value: Value =
            serde_json::from_slice(&out.stdout).map_err(|_| "invalid endpoint response")?;
        match value["code"].as_i64() {
            Some(0) => Ok(value["data"].clone()),
            Some(1 | 1000040343) => Err("endpoint temporarily unavailable".into()),
            _ => Err("endpoint authentication rejected".into()),
        }
    }

    fn validate_ws(&self, value: &str) -> Result<Url, Error> {
        let url = Url::parse(value).map_err(|_| "invalid WebSocket endpoint")?;
        let name = url.host_str().ok_or("missing WebSocket host")?;
        let suffix = if self.domain == "feishu" {
            ".feishu.cn"
        } else {
            ".larksuite.com"
        };
        let test = self.base.scheme() == "http" && url.scheme() == "ws" && name == "127.0.0.1";
        if !(test
            || self.base.scheme() == "https" && url.scheme() == "wss" && name.ends_with(suffix))
            || !url.username().is_empty()
            || url.password().is_some()
            || url.fragment().is_some()
        {
            return Err("foreign WebSocket endpoint".into());
        }
        Ok(url)
    }
}

fn tcp(host: &str, port: u16) -> Result<TcpStream, Error> {
    for addr in (host, port).to_socket_addrs()? {
        if let Ok(socket) = TcpStream::connect_timeout(&addr, Duration::from_secs(8)) {
            socket.set_read_timeout(Some(Duration::from_secs(8)))?;
            socket.set_write_timeout(Some(Duration::from_secs(8)))?;
            return Ok(socket);
        }
    }
    Err("network unavailable".into())
}

fn websocket(cfg: &Config, url: &Url) -> Result<Socket, Error> {
    let target = url.host_str().ok_or("missing host")?;
    let port = url.port_or_known_default().ok_or("missing port")?;
    let (stream, timer): (Box<dyn Stream>, TcpStream) = if let Some(proxy) = &cfg.proxy {
        let ph = proxy.host_str().ok_or("missing proxy")?;
        let socket = tcp(
            ph,
            proxy.port_or_known_default().ok_or("missing proxy port")?,
        )?;
        let timer = socket.try_clone()?;
        let mut stream: Box<dyn Stream> = if proxy.scheme() == "https" {
            Box::new(
                TlsConnector::new()?
                    .connect(ph, socket)
                    .map_err(|_| "proxy TLS failed")?,
            )
        } else {
            Box::new(socket)
        };
        write!(
            stream,
            "CONNECT {target}:{port} HTTP/1.1\r\nHost: {target}:{port}\r\n"
        )?;
        if !proxy.username().is_empty() {
            let user = percent_decode_str(proxy.username()).decode_utf8()?;
            let pass = percent_decode_str(proxy.password().unwrap_or("")).decode_utf8()?;
            write!(
                stream,
                "Proxy-Authorization: Basic {}\r\n",
                BASE64.encode(format!("{user}:{pass}").as_bytes())
            )?;
        }
        stream.write_all(b"\r\n")?;
        stream.flush()?;
        let mut reader = BufReader::new(&mut stream);
        let mut bytes = Vec::new();
        loop {
            let n = (&mut reader)
                .take(16_385 - bytes.len() as u64)
                .read_until(b'\n', &mut bytes)?;
            if n == 0 || bytes.len() > 16384 {
                return Err("proxy CONNECT failed".into());
            }
            if bytes.ends_with(b"\r\n\r\n") {
                break;
            }
        }
        if bytes.split(|b| *b == b' ').nth(1) != Some(b"200".as_slice()) {
            return Err("proxy CONNECT refused".into());
        }
        (stream, timer)
    } else {
        let socket = tcp(target, port)?;
        let timer = socket.try_clone()?;
        (Box::new(socket), timer)
    };
    let config = WebSocketConfig::default()
        .max_message_size(Some(2 * 1024 * 1024))
        .max_frame_size(Some(2 * 1024 * 1024));
    let (ws, _) =
        client_tls_with_config(url.as_str(), stream, Some(config), None).map_err(|e| {
            if let tungstenite::HandshakeError::Failure(tungstenite::Error::Http(response)) = e {
                let status = response
                    .headers()
                    .get("handshake-status")
                    .and_then(|v| v.to_str().ok());
                let auth = response
                    .headers()
                    .get("handshake-autherrcode")
                    .and_then(|v| v.to_str().ok());
                if status == Some("403") || (status == Some("514") && auth == Some("1000040350")) {
                    return "endpoint authentication rejected";
                }
            }
            "WebSocket handshake failed"
        })?;
    timer.set_read_timeout(Some(Duration::from_millis(500)))?;
    Ok(ws)
}

struct Timing {
    ping: u64,
    retry: u64,
    attempts: i64,
    nonce: u64,
}
impl Timing {
    fn update(&mut self, config: &Value) {
        if let Some(n) = config["PingInterval"].as_u64() {
            self.ping = n.clamp(1, 3600);
        }
        if let Some(n) = config["ReconnectInterval"].as_u64() {
            self.retry = n.clamp(1, 3600);
        }
        if let Some(n) = config["ReconnectCount"].as_i64() {
            self.attempts = n.max(-1);
        }
        if let Some(n) = config["ReconnectNonce"].as_u64() {
            self.nonce = n.min(3600);
        }
    }
}
fn connection(
    cfg: &Config,
    host: &mut Host,
    timing: &mut Timing,
    attempts: &mut i64,
) -> Result<(), Error> {
    let data = cfg.endpoint()?;
    timing.update(&data["ClientConfig"]);
    let url = cfg.validate_ws(data["URL"].as_str().ok_or("missing WebSocket URL")?)?;
    let service = url
        .query_pairs()
        .find(|(k, _)| k == "service_id")
        .ok_or("missing service id")?
        .1
        .parse()?;
    let mut ws = websocket(cfg, &url)?;
    *attempts = 0;
    let mut fragments = Assembler::default();
    let mut pending = HashMap::<_, (Frame, Instant)>::new();
    let mut next_ping = Instant::now();
    loop {
        for (id, durable) in host.poll()? {
            if let Some((frame, start)) = pending.remove(&id) {
                ws.send(Message::Binary(
                    frame
                        .ack(if durable { 200 } else { 500 }, start.elapsed())
                        .encode_to_vec()
                        .into(),
                ))?;
            }
        }
        if Instant::now() >= next_ping {
            ws.send(Message::Binary(Frame::ping(service).encode_to_vec().into()))?;
            next_ping = Instant::now() + Duration::from_secs(timing.ping);
        }
        let raw = match ws.read() {
            Ok(Message::Binary(raw)) => raw,
            Ok(Message::Close(_)) => return Err("native peer closed".into()),
            Ok(_) => {
                ws.flush()?;
                continue;
            }
            Err(tungstenite::Error::Io(e))
                if matches!(
                    e.kind(),
                    io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
                ) =>
            {
                continue;
            }
            Err(_) => return Err("native stream disconnected".into()),
        };
        let frame = Frame::decode(raw)?;
        if frame.service != service {
            return Err("wrong native service".into());
        }
        let ty = frame.header("type");
        if frame.method == 0 {
            if ty == Some("pong") {
                if let Some(data) = frame.payload.as_ref().filter(|data| !data.is_empty()) {
                    timing.update(&serde_json::from_slice(data)?);
                }
                next_ping = Instant::now() + Duration::from_secs(timing.ping);
            }
            continue;
        }
        if frame.method != 1 || !matches!(ty, Some("event" | "card")) {
            continue;
        }
        let start = Instant::now();
        let Some(bytes) = fragments.payload(&frame, start)? else {
            continue;
        };
        let submission = (|| -> Result<Option<_>, Error> {
            if ty == Some("event") {
                let event = serde_json::from_slice(&bytes)?;
                if let Some(params) = ingress::normalize(&event, &cfg.app, &cfg.tenant)? {
                    if pending.len() >= 32 {
                        return Err("pending admission capacity".into());
                    }
                    return Ok(Some(host.submit(params)?));
                }
            }
            Ok(None)
        })();
        match submission {
            Ok(Some(id)) => {
                pending.insert(id, (frame, start));
            }
            outcome => ws.send(Message::Binary(
                frame
                    .ack(if outcome.is_ok() { 200 } else { 500 }, start.elapsed())
                    .encode_to_vec()
                    .into(),
            ))?,
        }
    }
}

fn main() -> Result<(), Error> {
    let mut host = Host::connect()?;
    let cfg = Config::load()?;
    let mut timing = Timing {
        ping: 120,
        retry: 120,
        attempts: -1,
        nonce: 30,
    };
    let mut attempts = 0;
    loop {
        if let Err(err) = connection(&cfg, &mut host, &mut timing, &mut attempts) {
            host.poll()?;
            if err.to_string() == "endpoint authentication rejected" {
                return Err("endpoint authentication rejected".into());
            }
            attempts += 1;
            if timing.attempts >= 0 && attempts > timing.attempts {
                return Err("native reconnect exhausted".into());
            }
            let seed = SystemTime::now().duration_since(UNIX_EPOCH)?.subsec_nanos() as u64;
            let delay = timing.retry
                + if attempts == 1 {
                    seed % (timing.nonce + 1)
                } else {
                    0
                };
            let until = Instant::now() + Duration::from_secs(delay);
            while Instant::now() < until {
                host.poll()?;
                thread::sleep(Duration::from_millis(250));
            }
        }
    }
}
