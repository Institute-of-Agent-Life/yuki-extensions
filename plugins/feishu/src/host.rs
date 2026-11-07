use crate::{
    Config, Error, attachment, segments,
    text::Reading,
    worker::{Job, Worker},
};
use serde_json::{Value, json};
use std::{
    env,
    io::{self, Write},
    sync::mpsc::{self, Receiver, RecvTimeoutError, TryRecvError},
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
    media: bool,
    send_enabled: bool,
    recall_enabled: bool,
    cfg: Config,
    namespace: String,
    worker: Option<Worker>,
    pending: Option<(Id, bool)>,
    text: Option<Reading>,
    text_enabled: bool,
    attachment: Option<attachment::Read>,
    upload_enabled: bool,
}
fn send(v: &Value) -> Result<(), Error> {
    let mut w = io::stdout().lock();
    writeln!(w, "{v}")?;
    Ok(w.flush()?)
}
fn response(id: Id, mut reply: Value) -> Result<(), Error> {
    reply["jsonrpc"] = json!("2.0");
    reply["id"] = json!(id);
    send(&reply)
}
type Input = Receiver<io::Result<Vec<u8>>>;
fn initialize() -> Result<(Input, Calls, Value), Error> {
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
            Received::Reply(value) => send(&value)?,
            Received::Response { result: Ok(_), .. } => {
                let reply: Value = serde_json::from_slice(&raw)?;
                return Ok((
                    rx,
                    Calls::negotiated(&reply["result"])?,
                    reply["result"].clone(),
                ));
            }
            Received::Response { result: Err(_), .. } => return Err("initialize refused".into()),
            Received::Notification => {}
        }
    }
}

pub fn cleanup() -> Result<(), Error> {
    let (input, mut calls, _) = initialize()?;
    while let Ok(raw) = input.recv() {
        match calls.receive(&raw?)? {
            Incoming::Call { id, method, params } if method == "forget.request" => response(
                id,
                json!({"result":{"key":params["key"],"watermark":params["watermark"],
                    "proof":"volatile-state-ended-with-previous-process"}}),
            )?,
            _ => return Err("unsupported cleanup callback".into()),
        }
    }
    Ok(())
}

impl Host {
    pub fn connect(cfg: &Config) -> Result<Self, Error> {
        let (input, calls, init) = initialize()?;
        let permitted = |grant: &str, method: &str| {
            init["grants"]
                .as_array()
                .is_some_and(|grants| grants.iter().any(|g| g == grant))
                && init["method_revisions"].as_array().is_some_and(|methods| {
                    methods
                        .iter()
                        .any(|m| m["name"] == method && m["revision"] == 1)
                })
        };
        let media = permitted("gateway.media", "gateway.media");
        let send_enabled = permitted("gateway.send", "gateway.plan_send")
            && permitted("gateway.send", "gateway.dispatch_part");
        let text_enabled = permitted("gateway.send", "gateway.read_text");
        let upload_enabled = send_enabled
            && permitted("gateway.send", "gateway.prepare_part")
            && permitted("media.open", "media.open");
        let recall_enabled = send_enabled && permitted("gateway.recall", "gateway.recall");
        let namespace = init["namespace"]
            .as_str()
            .ok_or("missing namespace")?
            .to_owned();
        let worker = (media || send_enabled).then(|| Worker::new(cfg.clone(), namespace.clone()));
        Ok(Self {
            input,
            calls,
            sequence: 1,
            identity: media.then(|| json!({"application":cfg.app,"tenant":cfg.tenant})),
            media,
            send_enabled,
            recall_enabled,
            cfg: cfg.clone(),
            namespace,
            worker,
            pending: None,
            text: None,
            text_enabled,
            attachment: None,
            upload_enabled,
        })
    }
    fn submit_job(&mut self, id: Id, job: Job, media: bool) -> Result<(), Error> {
        if self.pending.is_none()
            && self.text.is_none()
            && self.attachment.is_none()
            && self
                .worker
                .as_ref()
                .is_some_and(|worker| worker.submit(job))
        {
            self.pending = Some((id, media));
            return Ok(());
        }
        let reply = if media {
            json!({"error":{"code":-32000,"message":"resource reader unavailable"}})
        } else {
            json!({"result":{"state":"failed"}})
        };
        response(id, reply)
    }
    fn read_page(&mut self) -> Result<(), Error> {
        let reading = self.text.as_mut().ok_or("missing original text read")?;
        self.sequence = self.sequence.checked_add(1).ok_or("RPC id overflow")?;
        let id = Id::Number(self.sequence);
        send(
            &self
                .calls
                .request(id.clone(), "gateway.read_text", reading.page())?,
        )?;
        reading.page_id = Some(id);
        Ok(())
    }
    fn begin_text(&mut self, id: Id, params: Value, planning: bool) -> Result<(), Error> {
        if self.text_enabled
            && self.pending.is_none()
            && self.text.is_none()
            && self.attachment.is_none()
        {
            if let Ok(reading) = Reading::new(id.clone(), params, planning) {
                self.text = Some(reading);
                return self.read_page();
            }
        }
        response(
            id,
            json!({"error":{"code":-32000,"message":"original text reader unavailable"}}),
        )
    }
    fn text_result(&mut self, id: Id, result: Result<Value, Value>) -> Result<(), Error> {
        // A forget ACK may precede a late page. Only the current page can advance this read.
        if self
            .text
            .as_ref()
            .is_none_or(|r| r.page_id.as_ref() != Some(&id))
        {
            return Ok(());
        }
        let mut reading = self.text.take().ok_or("missing original text read")?;
        let progress = result
            .map_err(|_| Error::from("original text revoked"))
            .and_then(|page| reading.accept(&page));
        if matches!(progress, Ok(false)) {
            self.text = Some(reading);
            return self.read_page();
        }
        let original_id = reading.original_id.clone();
        let planning = reading.planning;
        match progress.and_then(|_| reading.finish(&self.cfg)) {
            Ok(value) if planning => response(original_id, json!({"result":value})),
            Ok(value) => self.submit_job(original_id, Job::Delivery(value), false),
            Err(_) => response(
                original_id,
                json!({"error":{"code":-32000,"message":"original text unavailable"}}),
            ),
        }
    }
    fn attachment_page(&mut self) -> Result<(), Error> {
        let reading = self
            .attachment
            .as_mut()
            .ok_or("missing original attachment read")?;
        self.sequence = self.sequence.checked_add(1).ok_or("RPC id overflow")?;
        let id = Id::Number(self.sequence);
        send(
            &self
                .calls
                .request(id.clone(), "media.open", reading.page())?,
        )?;
        reading.page_id = Some(id);
        Ok(())
    }
    fn begin_attachment(&mut self, id: Id, params: Value) -> Result<(), Error> {
        if self.pending.is_none() && self.text.is_none() && self.attachment.is_none() {
            if let Ok(reading) =
                attachment::Read::new(&self.cfg, &self.namespace, id.clone(), params)
            {
                self.attachment = Some(reading);
                return self.attachment_page();
            }
        }
        response(id, json!({"result":{"state":"failed"}}))
    }
    fn attachment_result(&mut self, id: Id, result: Result<Value, Value>) -> Result<(), Error> {
        if self
            .attachment
            .as_ref()
            .is_none_or(|r| r.page_id.as_ref() != Some(&id))
        {
            return Ok(());
        }
        let mut reading = self
            .attachment
            .take()
            .ok_or("missing original attachment read")?;
        let progress = result
            .map_err(|_| Error::from("original attachment revoked"))
            .and_then(|page| reading.accept(&page));
        if matches!(progress, Ok(false)) {
            self.attachment = Some(reading);
            return self.attachment_page();
        }
        let original_id = reading.original_id.clone();
        match progress.and_then(|_| reading.finish()) {
            Ok((args, mime, bytes)) => {
                self.submit_job(original_id, Job::Upload(args, mime, bytes), false)
            }
            Err(_) => response(original_id, json!({"result":{"state":"failed"}})),
        }
    }
    fn other(&mut self, incoming: Incoming) -> Result<(), Error> {
        match incoming {
            Incoming::Notification { .. } => Ok(()),
            Incoming::Call { id, method, params } if method == "forget.request" => {
                if let Some(reading) = self.attachment.take() {
                    response(reading.original_id, json!({"result":{"state":"failed"}}))?;
                }
                if let Some(reading) = self.text.take() {
                    response(
                        reading.original_id,
                        json!({"error":{"code":-32000,"message":"original text cleared"}}),
                    )?;
                }
                let enabled = self.worker.is_some();
                // Drop joins the cancelled HTTP pipe and clears both private caches.
                drop(self.worker.take());
                if let Some((pending, media)) = self.pending.take() {
                    response(
                        pending,
                        if media {
                            json!({"error":{"code":-32000,"message":"original resource cleared"}})
                        } else {
                            json!({"result":{"state":"unknown"}})
                        },
                    )?;
                }
                if enabled {
                    self.worker = Some(Worker::new(self.cfg.clone(), self.namespace.clone()));
                }
                response(
                    id,
                    json!({"result":{"key":params["key"],"watermark":params["watermark"],
                    "proof":"volatile-resource-and-token-cleared-http-pipe-joined"}}),
                )
            }
            Incoming::Call { id, method, params } if method == "gateway.media" && self.media => {
                self.submit_job(id, Job::Media(params), true)
            }
            Incoming::Call { id, method, params }
                if method == "gateway.plan_send" && self.send_enabled =>
            {
                if !params["arguments"]["media"].is_null() && !self.upload_enabled {
                    return response(
                        id,
                        json!({"error":{"code":-32602,"message":"native upload not negotiated"}}),
                    );
                }
                if params["arguments"].get("text_source").is_some() {
                    return self.begin_text(id, params, true);
                }
                response(
                    id,
                    match segments::plan(&self.cfg, &params["arguments"]) {
                        Ok(plan) => json!({"result":plan}),
                        Err(_) => {
                            json!({"error":{"code":-32602,"message":"unsupported original Feishu delivery"}})
                        }
                    },
                )
            }
            Incoming::Call { id, method, params }
                if method == "gateway.prepare_part" && self.upload_enabled =>
            {
                self.begin_attachment(id, params)
            }
            Incoming::Call { id, method, params }
                if method == "gateway.dispatch_part" && self.send_enabled =>
            {
                if params["arguments"]["part"].get("text_range").is_some() {
                    return self.begin_text(id, params, false);
                }
                self.submit_job(id, Job::Delivery(params["arguments"].clone()), false)
            }
            Incoming::Call { id, method, params }
                if method == "gateway.recall" && self.recall_enabled =>
            {
                self.submit_job(id, Job::Recall(params["arguments"].clone()), false)
            }
            Incoming::Call { id, method, .. }
                if method == "gateway.part_status" && self.send_enabled =>
            {
                // The Host holds durable physical receipts. This process has no retry evidence.
                response(id, json!({"result":{"state":"unknown"}}))
            }
            Incoming::Call { id, .. } => response(
                id,
                json!({"error":{"code":-32601,"message":"method_not_found"}}),
            ),
            _ => Err("unexpected host result".into()),
        }
    }
    pub fn poll(&mut self) -> Result<Vec<(Id, bool)>, Error> {
        let mut results = Vec::new();
        if let Some(worker) = &self.worker {
            match worker.responses.try_recv() {
                Ok(reply) => {
                    let (id, _) = self.pending.take().ok_or("unexpected REST result")?;
                    response(id, reply)?;
                }
                Err(TryRecvError::Empty) => {}
                Err(TryRecvError::Disconnected) => return Err("REST worker disconnected".into()),
            }
        }
        // Drain a bounded batch of ready pages before returning to native WebSocket ACKs.
        for _ in 0..32 {
            let incoming = if self.text.is_some() || self.attachment.is_some() {
                self.input
                    .recv_timeout(Duration::from_millis(2))
                    .map_err(|error| match error {
                        RecvTimeoutError::Timeout => TryRecvError::Empty,
                        RecvTimeoutError::Disconnected => TryRecvError::Disconnected,
                    })
            } else {
                self.input.try_recv()
            };
            match incoming {
                Err(TryRecvError::Empty) => return Ok(results),
                Err(TryRecvError::Disconnected) => return Err("host disconnected".into()),
                Ok(raw) => match self.calls.receive(&raw?)? {
                    Incoming::Result { id, method, result } if method == "gateway.read_text" => {
                        self.text_result(id, result)?;
                    }
                    Incoming::Result { id, method, result } if method == "media.open" => {
                        self.attachment_result(id, result)?;
                    }
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
        Ok(results)
    }
    pub fn submit(&mut self, mut params: Value) -> Result<Id, Error> {
        if let Some(id) = &self.identity {
            params["media_identity"] = id.clone();
        } else {
            params
                .as_object_mut()
                .ok_or("invalid inbound frame")?
                .remove("topic_root");
        }
        self.sequence = self.sequence.checked_add(1).ok_or("RPC id overflow")?;
        let id = Id::Number(self.sequence);
        send(&self.calls.request(id.clone(), "gateway.inbound", params)?)?;
        Ok(id)
    }
}
