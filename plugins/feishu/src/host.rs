use crate::{Config, Error, rest};
use serde_json::{Value, json};
use std::{
    env,
    io::{self, Write},
    sync::mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TryRecvError},
    thread,
    time::Duration,
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
    identity: Option<Value>,
    media: Option<SyncSender<(Id, Value)>>,
    responses: Receiver<Value>,
}
fn send(v: &Value) -> Result<(), Error> {
    let mut w = io::stdout().lock();
    writeln!(w, "{v}")?;
    Ok(w.flush()?)
}
impl Host {
    pub fn connect(cfg: &Config) -> Result<Self, Error> {
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
        let ns = binding.namespace.clone();
        let granted = binding.grants.iter().any(|g| g == "gateway.media");
        let offer = binding.offer();
        let mut peer = Peer::new(binding)?;
        send(&peer.request(Id::Number(1), offer)?)?;
        loop {
            let raw = rx.recv()??;
            match peer.receive(&raw)? {
                Received::Reply(v) => send(&v)?,
                Received::Response { result: Ok(_), .. } => {
                    let msg: Value = serde_json::from_slice(&raw)?;
                    let enabled = granted
                        && msg["result"]["method_revisions"]
                            .as_array()
                            .is_some_and(|ms| {
                                ms.iter()
                                    .any(|m| m["name"] == "gateway.media" && m["revision"] == 1)
                            });
                    let (jobs, rx_jobs) = mpsc::sync_channel::<(Id, Value)>(1);
                    let (tx_results, responses) = mpsc::sync_channel(2);
                    if enabled {
                        let cfg = cfg.clone();
                        thread::spawn(move || {
                            let mut client = rest::Client::default();
                            loop {
                                match rx_jobs.recv_timeout(Duration::from_secs(1)) {
                                    Ok((id, p)) => {
                                        let msg = match client.chunk(&cfg, &ns, p) {
                                            Ok(v) => json!({"jsonrpc":"2.0","id":id,"result":v}),
                                            Err(_) => {
                                                json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"original resource unavailable"}})
                                            }
                                        };
                                        if tx_results.send(msg).is_err() {
                                            break;
                                        }
                                    }
                                    Err(RecvTimeoutError::Timeout) => client.expire(),
                                    Err(RecvTimeoutError::Disconnected) => break,
                                }
                            }
                        });
                    }
                    return Ok(Self {
                        input: rx,
                        calls: Calls::negotiated(&msg["result"])?,
                        sequence: 1,
                        identity: enabled
                            .then(|| json!({"application":cfg.app,"tenant":cfg.tenant})),
                        media: enabled.then_some(jobs),
                        responses,
                    });
                }
                Received::Response { result: Err(_), .. } => {
                    return Err("initialize refused".into());
                }
                Received::Notification => {}
            }
        }
    }
    fn other(&mut self, incoming: Incoming) -> Result<(), Error> {
        match incoming {
            Incoming::Notification { .. } => Ok(()),
            Incoming::Call { id, method, params }
                if method == "gateway.media" && self.media.is_some() =>
            {
                if self
                    .media
                    .as_ref()
                    .ok_or("media not enabled")?
                    .try_send((id.clone(), params))
                    .is_err()
                {
                    send(
                        &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32000,"message":"resource reader unavailable"}}),
                    )?;
                }
                Ok(())
            }
            Incoming::Call { id, .. } => send(
                &json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"method_not_found"}}),
            ),
            _ => Err("unexpected host result".into()),
        }
    }
    pub fn poll(&mut self) -> Result<Vec<(Id, bool)>, Error> {
        let mut results = Vec::new();
        for reply in self.responses.try_iter() {
            send(&reply)?;
        }
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
                    other => self.other(other)?,
                },
            }
        }
    }
    pub fn submit(&mut self, mut params: Value) -> Result<Id, Error> {
        if let Some(id) = &self.identity {
            params["media_identity"] = id.clone();
        }
        self.sequence = self.sequence.checked_add(1).ok_or("RPC id overflow")?;
        let id = Id::Number(self.sequence);
        send(&self.calls.request(id.clone(), "gateway.inbound", params)?)?;
        Ok(id)
    }
}
