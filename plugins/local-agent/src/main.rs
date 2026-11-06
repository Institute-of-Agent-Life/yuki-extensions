mod authority;
mod catalog;
mod rpc;
mod server;
mod wire;

use std::{env, io, path::PathBuf, sync::{Arc, Mutex, atomic::{AtomicUsize, Ordering}}, thread};
use yuki_plugin_sdk::{host::Incoming, read_frame};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let state = PathBuf::from(env::var_os("YUKI_LOCAL_AGENT_STATE").ok_or("missing state directory")?);
    let mut catalog = catalog::Catalog::open(&state)?;
    if env::args().nth(1).as_deref() == Some("--catalog") {
        println!("{}", catalog.snapshot()?); return Ok(());
    }
    catalog.startup()?;
    let catalog = Arc::new(Mutex::new(catalog));
    let core = server::loopback("YUKI_LOCAL_AGENT_CORE")?;
    let listen = server::loopback("YUKI_LOCAL_AGENT_LISTEN")?;
    let socket = Arc::new(tiny_http::Server::http(listen).map_err(|_| "cannot bind local-agent listener")?);
    let mut input = io::stdin().lock();
    let rpc = Arc::new(rpc::handshake(&mut input)?);
    let active = Arc::new(AtomicUsize::new(0));
    let agent = server::http_agent();
    for _ in 0..4 {
        let (s, db, rpc, active, agent) = (socket.clone(), catalog.clone(), rpc.clone(), active.clone(), agent.clone());
        thread::spawn(move || server::serve(&s, core, &db, &agent, &rpc, &active));
    }
    let result: Result<(), Box<dyn std::error::Error>> = (|| {
        while let Some(raw) = read_frame(&mut input)? {
            let incoming = rpc.calls.lock().unwrap().receive(&raw)?;
            match incoming {
                Incoming::Result { id, result, .. } => rpc.result(id, result),
                Incoming::Call { id, .. } => rpc.reject(id),
                Incoming::Notification { .. } => (),
            }
        }
        Ok(())
    })();
    rpc.stopped.store(true, Ordering::Release);
    catalog.lock().unwrap().shutdown();
    result
}
