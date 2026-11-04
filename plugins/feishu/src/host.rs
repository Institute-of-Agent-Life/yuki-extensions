use crate::Error;
use serde_json::{Value, json};
use std::{
    env,
    io::{self, Write},
    sync::mpsc::{self, Receiver, TryRecvError},
    thread,
};
use yuki_plugin_sdk::{
    Binding, Id, Peer, Received,
    host::{Calls, Incoming},
    read_frame,
};

pub struct Host {
    input: Receiver<io::Result<Vec<u8>>>,
    calls: Calls,
    sequence: i64,
}
fn send(v: &Value) -> Result<(), Error> {
    let mut w = io::stdout().lock();
    writeln!(w, "{v}")?;
    Ok(w.flush()?)
}
impl Host {
    pub fn connect() -> Result<Self, Error> {
        let (tx, rx) = mpsc::sync_channel(8);
        thread::spawn(move || {
            let mut r = io::stdin().lock();
            loop {
                match read_frame(&mut r) {
                    Ok(Some(raw)) => {
                        if tx.send(Ok(raw)).is_err() {
                            break;
                        }
                    }
                    Ok(None) => break,
                    Err(e) => {
                        let _ = tx.send(Err(e));
                        break;
                    }
                }
            }
        });
        let binding: Binding = serde_json::from_str(&env::var("YUKI_PLUGIN_BINDING")?)?;
        let offer = binding.offer();
        let mut peer = Peer::new(binding)?;
        send(&peer.request(Id::Number(1), offer)?)?;
        loop {
            let raw = rx.recv()??;
            match peer.receive(&raw)? {
                Received::Reply(v) => send(&v)?,
                Received::Response { result: Ok(_), .. } => {
                    let msg: Value = serde_json::from_slice(&raw)?;
                    return Ok(Self {
                        input: rx,
                        calls: Calls::negotiated(&msg["result"])?,
                        sequence: 1,
                    });
                }
                Received::Response { result: Err(_), .. } => {
                    return Err("initialize refused".into());
                }
                Received::Notification => {}
            }
        }
    }
    fn other(incoming: Incoming) -> Result<(), Error> {
        match incoming {
            Incoming::Notification { .. } => Ok(()),
            Incoming::Call { id, .. } => send(
                &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}),
            ),
            _ => Err("unexpected host result".into()),
        }
    }
    pub fn poll(&mut self) -> Result<Vec<(Id, bool)>, Error> {
        let mut results = Vec::new();
        loop {
            match self.input.try_recv() {
                Err(TryRecvError::Empty) => return Ok(results),
                Err(TryRecvError::Disconnected) => return Err("host disconnected".into()),
                Ok(raw) => match self.calls.receive(&raw?)? {
                    Incoming::Result { id, result, .. } => {
                        let durable = result.is_ok_and(|v| {
                            (v["event"].as_u64().is_some_and(|n| n > 0) || v["erased"] == true)
                                && v["accepted"].is_boolean()
                        });
                        results.push((id, durable));
                    }
                    other => Self::other(other)?,
                },
            }
        }
    }
    pub fn submit(&mut self, params: Value) -> Result<Id, Error> {
        self.sequence = self.sequence.checked_add(1).ok_or("RPC id overflow")?;
        let id = Id::Number(self.sequence);
        send(&self.calls.request(id.clone(), "gateway.inbound", params)?)?;
        Ok(id)
    }
}
