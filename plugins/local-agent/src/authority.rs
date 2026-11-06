use crate::rpc::{Error, Rpc};
use serde_json::{Value, json};
use std::net::SocketAddr;
use std::time::{Duration, Instant};

pub struct Connection {
    pub device: String,
    pub namespace: String,
    pub epoch: i64,
    handle: String,
    opened: Instant,
}
fn text(value: &Value, name: &str) -> Result<String, Error> {
    value[name].as_str().filter(|s| !s.is_empty()).map(str::to_owned).ok_or(Error::Unavailable)
}
impl Connection {
    pub fn open(rpc: &Rpc, agent: &ureq::Agent, core: SocketAddr, bearer: &str) -> Result<Self, (u16, &'static str)> {
        // Only the core authenticates the original credential. The raw Bearer
        // crosses the private HTTP exchange, never the SDK or catalog database.
        let mut reply = agent.post(format!("http://{core}/core/v1/entry/exchange"))
            .header("Authorization", bearer).header("Content-Type", "application/json")
            .send(json!({"purpose":"connector","plugin":rpc.installation}).to_string().as_bytes())
            .map_err(|_| (502, "core_unavailable"))?;
        let code = reply.status().as_u16();
        if code != 200 {
            return Err((if matches!(code, 401 | 403) { code } else { 503 }, "connector_authority_refused"));
        }
        let body = reply.body_mut().with_config().limit(65536).read_to_vec().map_err(|_| (502, "invalid_core_response"))?;
        let value: Value = serde_json::from_slice(&body).map_err(|_| (502, "invalid_core_response"))?;
        let proof = value["data"]["proof"].as_str().filter(|v| !v.is_empty()).ok_or((502, "invalid_core_response"))?;
        let grant = rpc.call("device.connect", json!({"proof":proof})).map_err(status)?;
        let result = Self { device: text(&grant, "device_id").map_err(status)?,
            namespace: text(&grant, "journal_namespace").map_err(status)?,
            epoch: grant["connection_epoch"].as_i64().filter(|x| *x > 0).ok_or((502, "invalid_core_response"))?,
            handle: text(&grant, "handle").map_err(status)?, opened: Instant::now() };
        if grant["purpose"] != "connector" || grant["closed"] != false {
            return Err((502, "invalid_core_response"));
        }
        Ok(result)
    }
    pub fn check(&self, rpc: &Rpc) -> Result<(), Error> {
        let value = rpc.call("device.check", json!({"handle":self.handle}))?;
        if value["device_id"] != self.device || value["journal_namespace"] != self.namespace
            || value["connection_epoch"] != self.epoch || value["purpose"] != "connector" || value["closed"] != false {
            return Err(Error::Denied);
        }
        Ok(())
    }
    pub fn renewal_due(&self) -> bool {
        // The pinned contract grants 300 seconds. Close at a frame boundary
        // with 60 seconds left so the original Connector can reconnect. Never
        // renew an old stream into a newer epoch and displace its replacement.
        self.opened.elapsed() >= Duration::from_secs(240)
    }
    pub fn close(&self, rpc: &Rpc) {
        // A stale epoch may be refused. Never substitute a new handle or retry.
        let _ = rpc.call("device.close", json!({"handle":self.handle}));
    }
}
pub fn status(error: Error) -> (u16, &'static str) {
    match error { Error::Denied => (403, "connector_authority_refused"), Error::Unavailable => (503, "connector_authority_unavailable") }
}
