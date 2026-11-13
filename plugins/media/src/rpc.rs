use serde_json::{Value, json};
use std::{
    collections::HashMap,
    io::{self, BufRead, Write},
    sync::{
        Mutex,
        atomic::{AtomicBool, AtomicI64, Ordering},
        mpsc,
    },
    time::Duration,
};
use yuki_plugin_sdk::{Binding, Id, Peer, Received, host::Calls, read_frame};
pub type Result<T> = std::result::Result<T, String>;
type Reply = std::result::Result<Value, String>;

pub struct Rpc {
    pub calls: Mutex<Calls>,
    pub pending: Mutex<HashMap<Id, mpsc::Sender<Reply>>>,
    output: Mutex<io::Stdout>,
    next: AtomicI64,
}

pub fn handshake(input: &mut impl BufRead) -> Result<Rpc> {
    let binding: Binding =
        serde_json::from_str(&std::env::var("YUKI_PLUGIN_BINDING").map_err(|_| "binding missing")?)
            .map_err(|_| "binding invalid")?;
    let offer = binding.offer();
    let mut peer = Peer::new(binding).map_err(|_| "binding refused")?;
    let mut out = io::stdout();
    writeln!(
        out,
        "{}",
        peer.request(Id::Number(1), offer)
            .map_err(|_| "offer refused")?
    )
    .map_err(|_| "host disconnected")?;
    out.flush().map_err(|_| "host disconnected")?;
    loop {
        let raw = read_frame(input)
            .map_err(|_| "invalid frame")?
            .ok_or("host disconnected")?;
        match peer.receive(&raw).map_err(|_| "invalid handshake")? {
            Received::Reply(v) => {
                writeln!(out, "{v}").map_err(|_| "host disconnected")?;
                out.flush().map_err(|_| "host disconnected")?;
            }
            Received::Response { result: Ok(_), .. } => {
                let v: Value = serde_json::from_slice(&raw).map_err(|_| "invalid handshake")?;
                return Ok(Rpc {
                    calls: Mutex::new(
                        Calls::negotiated(&v["result"]).map_err(|_| "negotiation failed")?,
                    ),
                    pending: Mutex::new(HashMap::new()),
                    output: Mutex::new(out),
                    next: AtomicI64::new(10),
                });
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => (),
        }
    }
}
impl Rpc {
    pub fn send(&self, v: &Value) -> Result<()> {
        let mut out = self.output.lock().map_err(|_| "output unavailable")?;
        writeln!(out, "{v}")
            .and_then(|_| out.flush())
            .map_err(|_| "host disconnected".into())
    }
    pub fn reply(&self, id: Id, result: Value) {
        let _ = self.send(&json!({"jsonrpc":"2.0","id":id,"result":result}));
    }
    pub fn call(&self, method: &str, params: Value, cancel: &AtomicBool) -> Result<Value> {
        if cancel.load(Ordering::Acquire) {
            return Err("cancelled".into());
        }
        let id = Id::Number(self.next.fetch_add(1, Ordering::Relaxed));
        let (tx, rx) = mpsc::channel();
        let frame = self
            .calls
            .lock()
            .unwrap()
            .request(id.clone(), method, params)
            .map_err(|_| "method unavailable")?;
        self.pending.lock().unwrap().insert(id.clone(), tx);
        if self.send(&frame).is_err() {
            self.pending.lock().unwrap().remove(&id);
            return Err("host disconnected".into());
        }
        let wait = if method == "llm.complete" { 35 } else { 10 };
        let deadline = std::time::Instant::now() + Duration::from_secs(wait);
        loop {
            match rx.recv_timeout(Duration::from_millis(25)) {
                Ok(v) => return v,
                Err(mpsc::RecvTimeoutError::Disconnected) => return Err("host disconnected".into()),
                Err(mpsc::RecvTimeoutError::Timeout) => (),
            }
            if cancel.load(Ordering::Acquire) || std::time::Instant::now() >= deadline {
                self.pending.lock().unwrap().remove(&id);
                return Err("scope check interrupted".into());
            }
        }
    }
}
