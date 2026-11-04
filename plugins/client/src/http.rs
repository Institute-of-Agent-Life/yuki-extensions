use crate::auth;
use serde_json::json;
use std::{io::Read, net::SocketAddr, time::Duration};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};
type Problem = (u16, &'static str);

pub fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .proxy(None)
        .max_redirects(0)
        .http_status_as_error(false)
        .timeout_connect(Some(Duration::from_secs(5)))
        .timeout_recv_response(Some(Duration::from_secs(15)))
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
        if ["Authorization", "Content-Type", "Accept", "Last-Event-ID"]
            .iter()
            .any(|name| h.field.equiv(name))
        {
            builder = builder.header(h.field.as_str().as_str(), h.value.as_str());
        }
    }
    let result = if req.method() == &Method::Post {
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

pub fn serve(server: &Server, core: SocketAddr, agent: &ureq::Agent) {
    for mut req in server.incoming_requests() {
        match send(&mut req, core, agent) {
            Ok(upstream) => {
                let status = StatusCode(upstream.status().as_u16());
                let mut headers = vec![Header::from_bytes("Cache-Control", "no-store").unwrap()];
                if let Some(value) = upstream
                    .headers()
                    .get("Content-Type")
                    .and_then(|v| Header::from_bytes("Content-Type", v.as_bytes()).ok())
                {
                    headers.push(value);
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
                let body = json!({"problem":{"code":kind}}).to_string();
                let _ = req.respond(
                    Response::from_string(body)
                        .with_status_code(StatusCode(code))
                        .with_header(Header::from_bytes("Cache-Control", "no-store").unwrap())
                        .with_header(
                            Header::from_bytes("Content-Type", "application/json").unwrap(),
                        ),
                );
            }
        }
    }
}
