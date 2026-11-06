use crate::catalog::Catalog;
use crate::{authority, rpc::Rpc, wire};
use serde_json::{Value, json};
use std::{io::Read, net::SocketAddr, sync::{Arc, Mutex, atomic::{AtomicUsize, Ordering}}, time::Duration, thread};
use tiny_http::{Header, Method, Request, Response, Server, StatusCode};
use tungstenite::{Message, WebSocket, handshake::server::create_response,
    protocol::{Role, WebSocketConfig, CloseFrame, frame::coding::CloseCode}};

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

struct Permit(Arc<AtomicUsize>);
impl Drop for Permit { fn drop(&mut self) { self.0.fetch_sub(1, Ordering::AcqRel); } }

fn connect(req: Request, core: SocketAddr, db: &Mutex<Catalog>, agent: &ureq::Agent, rpc: &Rpc) {
    let headers: Vec<_> = req.headers().iter().filter(|h| h.field.equiv("Authorization")).collect();
    if headers.len() != 1 {
        let status = if headers.is_empty() { 401 } else { 400 };
        problem(req, status, "unauthenticated"); return;
    }
    let bearer = headers[0].value.as_str().to_owned();
    if bearer.strip_prefix("Bearer ").is_none_or(|s| s.is_empty() || s.len() > 4096) {
        problem(req, 401, "unauthenticated"); return;
    }
    let mut upgrade = tungstenite::http::Request::builder().method("GET").uri(req.url());
    for header in req.headers() { upgrade = upgrade.header(header.field.as_str().as_str(), header.value.as_str()); }
    let Some(handshake) = upgrade.body(()).ok().and_then(|r| create_response(&r).ok()) else {
        problem(req, 400, "invalid_websocket_upgrade"); return;
    };
    let authority = match authority::Connection::open(rpc, agent, core, &bearer) {
        Ok(v) => v, Err((status, code)) => { problem(req, status, code); return; }
    };
    if !db.lock().unwrap().attach(&authority.device, &authority.namespace, authority.epoch).unwrap_or(false) {
        authority.close(rpc); problem(req, 409, "connection_superseded"); return;
    }
    let accept = handshake.headers().get("Sec-WebSocket-Accept").unwrap().as_bytes();
    let stream = req.upgrade("websocket", Response::empty(101).with_header(Header::from_bytes("Sec-WebSocket-Accept", accept).unwrap()));
    let mut config = WebSocketConfig::default();
    config.max_message_size = Some(16 * 1024 * 1024);
    config.max_frame_size = Some(16 * 1024 * 1024);
    let mut socket = WebSocket::from_raw_socket(stream, Role::Server, Some(config));
    let mut hello = true;
    let result: Result<(), &'static str> = (|| {
        loop {
            let frame = socket.read().map_err(|_| "connector_disconnected")?;
            if rpc.stopped.load(Ordering::Acquire) || authority.check(rpc).is_err() { return Err("credential_revoked"); }
            if authority.renewal_due() { return Err("connector_reauthentication_required"); }
            match frame {
                Message::Text(text) => {
                    let value: Value = serde_json::from_str(&text).map_err(|_| "invalid_connector_message")?;
                    if !hello && value["type"] == "ping" {
                        socket.send(Message::Text(json!({"type":"pong"}).to_string().into())).map_err(|_| "connector_disconnected")?;
                        continue;
                    }
                    if !hello && value["type"] != "catalog" { return Err("native_work_authority_unavailable"); }
                    let snapshot = wire::snapshot(&value, &authority.device, hello)?;
                    if !db.lock().unwrap().replace(&authority.device, authority.epoch, &snapshot.capabilities, &snapshot.instances).map_err(|_| "catalog_unavailable")? {
                        return Err("connection_superseded");
                    }
                    if !hello { socket.send(Message::Text(json!({"type":"catalog_ack"}).to_string().into())).map_err(|_| "connector_disconnected")?; }
                    hello = false;
                }
                Message::Ping(data) => { socket.send(Message::Pong(data)).map_err(|_| "connector_disconnected")?; }
                Message::Pong(_) => (),
                Message::Close(_) => return Ok(()),
                _ => return Err("invalid_connector_message"),
            }
        }
    })();
    if let Err(reason) = result {
        // The original Connector reserves 1008 for authorization loss and
        // stops its owners. A scheduled reauthentication must reconnect.
        let code = if reason == "connector_reauthentication_required" { CloseCode::Away } else { CloseCode::Policy };
        let _ = socket.close(Some(CloseFrame { code, reason: reason.into() }));
    } else { let _ = socket.flush(); }
    authority.close(rpc);
    let _ = db.lock().unwrap().disconnect(&authority.device, authority.epoch);
}

pub fn serve(server: &Server, core: SocketAddr, db: &Arc<Mutex<Catalog>>, agent: &ureq::Agent, rpc: &Arc<Rpc>, active: &Arc<AtomicUsize>) {
    for mut req in server.incoming_requests() {
        if req.method() == &Method::Get && req.url() == "/agents/v1/connect" {
            if active.fetch_update(Ordering::AcqRel, Ordering::Acquire, |n| if n < 16 { Some(n+1) } else { None }).is_err() {
                problem(req, 503, "connection_limit"); continue;
            }
            let (db, agent, rpc, active) = (db.clone(), agent.clone(), rpc.clone(), active.clone());
            thread::spawn(move || { let _permit = Permit(active); connect(req, core, &db, &agent, &rpc); });
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
