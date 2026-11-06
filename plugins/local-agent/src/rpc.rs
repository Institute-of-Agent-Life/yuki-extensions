//! Independent SDK transport; proof and handle values are never logged.
use serde_json::{Value, json};
use std::{collections::HashMap, io::{self, BufRead, Write}, sync::{Mutex, mpsc,
    atomic::{AtomicBool, AtomicI64, Ordering}}, time::{Duration, Instant}};
use yuki_plugin_sdk::{Binding, Id, Peer, Received, host::Calls, read_frame};

#[derive(Debug)]
pub enum Error { Denied, Unavailable }
pub struct Rpc {
    pub calls: Mutex<Calls>,
    pub pending: Mutex<HashMap<Id, mpsc::Sender<Result<Value, Error>>>>,
    pub stopped: AtomicBool,
    pub installation: String,
    output: Mutex<io::Stdout>,
    next: AtomicI64,
}
pub fn handshake(input: &mut impl BufRead) -> Result<Rpc, Box<dyn std::error::Error>> {
    let binding: Binding = serde_json::from_str(&std::env::var("YUKI_PLUGIN_BINDING")?)?;
    // The SDK namespace may differ from the approved installation ID. The
    // private exchange requires the latter; the Host still owns its authority.
    let installation = std::env::var("YUKI_LOCAL_AGENT_INSTALLATION")?;
    if installation.is_empty() { return Err("missing installation ID".into()); }
    let offer = binding.offer();
    let mut peer = Peer::new(binding).map_err(|_| "binding refused")?;
    let mut out = io::stdout();
    writeln!(out, "{}", peer.request(Id::Number(1), offer).map_err(|_| "offer refused")?)?;
    out.flush()?;
    loop {
        let raw = read_frame(input)?.ok_or("host disconnected")?;
        match peer.receive(&raw).map_err(|_| "invalid handshake")? {
            Received::Reply(value) => { writeln!(out, "{value}")?; out.flush()?; }
            Received::Response { result: Ok(_), .. } => {
                let value: Value = serde_json::from_slice(&raw)?;
                return Ok(Rpc { calls: Mutex::new(Calls::negotiated(&value["result"])?),
                    pending: Mutex::new(HashMap::new()), stopped: AtomicBool::new(false),
                    installation, output: Mutex::new(out), next: AtomicI64::new(10) });
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => (),
        }
    }
}
impl Rpc {
    pub fn send(&self, value: &Value) -> Result<(), Error> {
        let mut out = self.output.lock().map_err(|_| Error::Unavailable)?;
        writeln!(out, "{value}").and_then(|_| out.flush()).map_err(|_| Error::Unavailable)
    }
    pub fn call(&self, method: &str, params: Value) -> Result<Value, Error> {
        if self.stopped.load(Ordering::Acquire) { return Err(Error::Unavailable); }
        let id = Id::Number(self.next.fetch_add(1, Ordering::Relaxed));
        let frame = self.calls.lock().unwrap().request(id.clone(), method, params)
            .map_err(|_| Error::Unavailable)?;
        let (tx, rx) = mpsc::channel();
        self.pending.lock().unwrap().insert(id.clone(), tx);
        if self.send(&frame).is_err() {
            self.pending.lock().unwrap().remove(&id); return Err(Error::Unavailable);
        }
        let until = Instant::now() + Duration::from_secs(10);
        loop {
            match rx.recv_timeout(Duration::from_millis(50)) {
                Ok(value) => return value,
                Err(mpsc::RecvTimeoutError::Disconnected) => return Err(Error::Unavailable),
                Err(mpsc::RecvTimeoutError::Timeout) => (),
            }
            if self.stopped.load(Ordering::Acquire) || Instant::now() >= until {
                self.pending.lock().unwrap().remove(&id); return Err(Error::Unavailable);
            }
        }
    }
    pub fn result(&self, id: Id, result: Result<Value, Value>) {
        if let Some(tx) = self.pending.lock().unwrap().remove(&id) {
            let _ = tx.send(result.map_err(|v| if v["code"] == -32003 { Error::Denied } else { Error::Unavailable }));
        }
    }
    pub fn reject(&self, id: Id) {
        let _ = self.send(&json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"device catalog only"}}));
    }
}
