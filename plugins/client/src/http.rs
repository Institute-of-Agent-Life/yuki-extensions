use crate::{auth, stream};
use serde_json::json;
use std::{
    io::Read,
    net::SocketAddr,
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    thread,
    time::Duration,
};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};
type Problem = (u16, &'static str);

fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .proxy(None)
        .max_redirects(0)
        .http_status_as_error(false)
        .timeout_connect(Some(Duration::from_secs(5)))
        .timeout_recv_response(Some(Duration::from_secs(15)))
        // A quiet upstream cannot retain a disconnected downstream's permit
        // forever. SSE reconnects start with a fresh owner sync and GET cursor.
        .timeout_recv_body(Some(Duration::from_secs(65)))
        .build()
        .into()
}

fn send(
    req: &mut Request,
    core: SocketAddr,
    agent: &ureq::Agent,
) -> Result<ureq::http::Response<ureq::Body>, Problem> {
    auth::check(req)?;
    let mut builder = ureq::http::Request::builder()
        .method(req.method().as_str())
        .uri(format!("http://{core}{}", req.url()));
    for h in req.headers() {
        if [
            "Authorization",
            "Content-Type",
            "Accept",
            "Last-Event-ID",
            "X-Yuki-Entry",
            "X-Yuki-Conversation",
        ]
        .iter()
        .any(|name| h.field.equiv(name))
        {
            builder = builder.header(h.field.as_str().as_str(), h.value.as_str());
        }
    }
    let result = if req.method() == &Method::Post
        && req.url().split('?').next() == Some("/client/v1/uploads")
    {
        let length = req.body_length().ok_or((411, "length_required"))?;
        if length > 64 * 1_048_576 {
            return Err((413, "request_too_large"));
        }
        agent.run(
            builder
                .header("Content-Length", length)
                .body(ureq::SendBody::from_reader(req.as_reader()))
                .map_err(|_| (400, "invalid_request"))?,
        )
    } else if req.method() == &Method::Post {
        let mut bytes = vec![];
        req.as_reader()
            .take(1_048_577)
            .read_to_end(&mut bytes)
            .map_err(|_| (400, "invalid_body"))?;
        if bytes.len() > 1_048_576 {
            return Err((413, "request_too_large"));
        }
        agent.run(
            builder
                .body(bytes.as_slice())
                .map_err(|_| (400, "invalid_request"))?,
        )
    } else {
        agent.run(builder.body(()).map_err(|_| (400, "invalid_request"))?)
    };
    result.map_err(|_| (502, "owner_unavailable"))
}

struct Permit(Arc<AtomicUsize>);
impl Permit {
    fn take(counter: &Arc<AtomicUsize>, limit: usize) -> Option<Self> {
        counter
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < limit).then_some(n + 1)
            })
            .ok()
            .map(|_| Self(counter.clone()))
    }
}
impl Drop for Permit {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

fn reject(req: Request, code: u16, kind: &str) {
    let _ = req.respond(
        Response::from_string(json!({"problem":{"code":kind}}).to_string())
            .with_status_code(StatusCode(code))
            .with_header(Header::from_bytes("Cache-Control", "no-store").unwrap())
            .with_header(Header::from_bytes("Content-Type", "application/json").unwrap()),
    );
}

pub fn serve(server: Server, core: SocketAddr) {
    let ordinary = Arc::new(AtomicUsize::new(0));
    let streams = Arc::new(AtomicUsize::new(0));
    let uploads = Arc::new(AtomicUsize::new(0));
    let agent = agent();
    for mut req in server.incoming_requests() {
        if let Err((code, kind)) = auth::check(&req) {
            reject(req, code, kind);
            continue;
        }
        let is_stream = req.url().split('?').next() == Some("/client/v1/stream");
        let is_upload = req.url().split('?').next() == Some("/client/v1/uploads");
        let (counter, limit) = if is_stream {
            (&streams, 4)
        } else if is_upload {
            (&uploads, 4)
        } else {
            (&ordinary, 8)
        };
        let Some(permit) = Permit::take(counter, limit) else {
            reject(req, 503, "client_busy");
            continue;
        };
        let agent = agent.clone();
        thread::spawn(move || {
            let _permit = permit;
            match send(&mut req, core, &agent) {
                Ok(upstream) => {
                    if is_stream && upstream.status().is_success() {
                        let _ = stream::respond(req, upstream);
                        return;
                    }
                    let status = StatusCode(upstream.status().as_u16());
                    let mut headers =
                        vec![Header::from_bytes("Cache-Control", "no-store").unwrap()];
                    for name in ["Content-Type", "ETag", "Content-Disposition"] {
                        if let Some(value) = upstream
                            .headers()
                            .get(name)
                            .and_then(|v| Header::from_bytes(name, v.as_bytes()).ok())
                        {
                            headers.push(value);
                        }
                    }
                    let length = upstream
                        .headers()
                        .get("Content-Length")
                        .and_then(|v| v.to_str().ok()?.parse::<usize>().ok());
                    let _ = req.respond(Response::new(
                        status,
                        headers,
                        upstream.into_body().into_reader(),
                        length,
                        None,
                    ));
                }
                Err((code, kind)) => {
                    reject(req, code, kind);
                }
            }
        });
    }
}
