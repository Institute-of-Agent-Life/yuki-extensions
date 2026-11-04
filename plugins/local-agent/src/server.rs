use crate::catalog::Catalog;
use serde_json::{Value, json};
use std::{io::Read, net::SocketAddr, sync::Mutex, time::Duration};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};

pub fn loopback(name: &str) -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let addr: SocketAddr = std::env::var(name)?.parse()?;
    if !addr.ip().is_loopback() || addr.port() == 0 {
        return Err("expected a configured loopback port".into());
    }
    Ok(addr)
}

fn reply(req: Request, code: u16, body: Vec<u8>) {
    let _ = req.respond(
        Response::from_data(body)
            .with_status_code(StatusCode(code))
            .with_header(Header::from_bytes("Content-Type", "application/json").unwrap())
            .with_header(Header::from_bytes("Cache-Control", "no-store").unwrap()),
    );
}
fn problem(req: Request, code: u16, key: &str) {
    reply(
        req,
        code,
        json!({"problem":{"code":key}}).to_string().into_bytes(),
    )
}

pub fn serve(server: &Server, core: SocketAddr, db: &Mutex<Catalog>, agent: &ureq::Agent) {
    for mut req in server.incoming_requests() {
        if req.method() == &Method::Get && req.url() == "/agents/v1/connect" {
            // CORE-033 authenticates an original Work. An idle wire4 hello supplies no such proof.
            let bearer = req.headers().iter().any(|h| {
                h.field.equiv("Authorization")
                    && h.value
                        .as_str()
                        .strip_prefix("Bearer ")
                        .is_some_and(|v| !v.is_empty())
            });
            if bearer {
                problem(req, 503, "connector_device_authority_unavailable");
            } else {
                problem(req, 401, "unauthenticated");
            }
            continue;
        }
        if req.method() != &Method::Post || req.url() != "/agents/v1/pair" {
            problem(req, 404, "not_found");
            continue;
        }
        let mut body = Vec::new();
        if req.as_reader().take(16385).read_to_end(&mut body).is_err() || body.len() > 16384 {
            problem(req, 413, "invalid_pair_request");
            continue;
        }
        let result = agent
            .post(format!("http://{core}/agents/v1/pair"))
            .header("Content-Type", "application/json")
            .send(&body[..]);
        let Ok(mut owner) = result else {
            problem(req, 502, "core_unavailable");
            continue;
        };
        let status = owner.status().as_u16();
        let Ok(body) = owner.body_mut().with_config().limit(65536).read_to_vec() else {
            problem(req, 502, "invalid_core_response");
            continue;
        };
        if status == 200 {
            let Ok(value) = serde_json::from_slice::<Value>(&body) else {
                problem(req, 502, "invalid_core_response");
                continue;
            };
            let receipt = value.get("data").unwrap_or(&value);
            let (Some(device), Some(token)) = (
                receipt["device_id"].as_str().filter(|s| !s.is_empty()),
                receipt["token"].as_str().filter(|s| !s.is_empty()),
            ) else {
                problem(req, 502, "invalid_core_response");
                continue;
            };
            // The one-time code has already been consumed. Preserve the original credential even if local storage fails.
            if db.lock().unwrap().paired(device).is_err() {
                eprintln!("could not persist paired device in local catalog");
            }
            reply(
                req,
                status,
                json!({"device_id":device,"token":token})
                    .to_string()
                    .into_bytes(),
            );
        } else {
            reply(req, status, body);
        }
    }
}

pub fn http_agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .proxy(None)
        .max_redirects(0)
        .http_status_as_error(false)
        .timeout_global(Some(Duration::from_secs(10)))
        .build()
        .into()
}
