mod catalog;
mod server;
use serde_json::{Value, json};
use std::{
    env,
    io::{self, Write},
    path::PathBuf,
    sync::{Arc, Mutex},
    thread,
};
use yuki_plugin_sdk::{
    Binding, Id, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};
type Error = Box<dyn std::error::Error>;
fn send(value: &Value) -> Result<(), Error> {
    let mut w = io::stdout().lock();
    writeln!(w, "{value}")?;
    Ok(w.flush()?)
}

fn main() -> Result<(), Error> {
    let state =
        PathBuf::from(env::var_os("YUKI_LOCAL_AGENT_STATE").ok_or("missing state directory")?);
    if env::args().nth(1).as_deref() == Some("--catalog") {
        println!(
            "{}",
            json!({"devices":catalog::Catalog::open(&state)?.devices()?})
        );
        return Ok(());
    }
    let catalog = Arc::new(Mutex::new(catalog::Catalog::open(&state)?));
    let core = server::loopback("YUKI_LOCAL_AGENT_CORE")?;
    let listen = server::loopback("YUKI_LOCAL_AGENT_LISTEN")?;
    let socket =
        Arc::new(tiny_http::Server::http(listen).map_err(|_| "cannot bind local-agent listener")?);
    let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
    let offer = binding.offer();
    let mut peer = Peer::new(binding)?;
    let mut input = io::stdin().lock();
    send(&peer.request(Id::Number(1), offer)?)?;
    let mut calls = loop {
        let raw = read_frame(&mut input)?.ok_or("host disconnected")?;
        match peer.receive(&raw)? {
            Received::Reply(v) => send(&v)?,
            Received::Response { result: Ok(_), .. } => {
                break Calls::negotiated(&serde_json::from_slice::<Value>(&raw)?["result"])?;
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => (),
        }
    };
    let agent = server::http_agent();
    for _ in 0..4 {
        let s = socket.clone();
        let db = catalog.clone();
        let agent = agent.clone();
        thread::spawn(move || server::serve(&s, core, &db, &agent));
    }
    while let Some(raw) = read_frame(&mut input)? {
        if let Incoming::Call { id, .. } = calls.receive(&raw)? {
            send(
                &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}),
            )?;
        }
    }
    Ok(())
}
