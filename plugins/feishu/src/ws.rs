use prost::Message;
use std::{
    collections::HashMap,
    time::{Duration, Instant},
};

#[derive(Clone, PartialEq, Message)]
pub struct Header {
    #[prost(string, required, tag = "1")]
    pub key: String,
    #[prost(string, required, tag = "2")]
    pub value: String,
}

#[derive(Clone, PartialEq, Message)]
pub struct Frame {
    #[prost(uint64, required, tag = "1")]
    pub seq_id: u64,
    #[prost(uint64, required, tag = "2")]
    pub log_id: u64,
    #[prost(int32, required, tag = "3")]
    pub service: i32,
    #[prost(int32, required, tag = "4")]
    pub method: i32,
    #[prost(message, repeated, tag = "5")]
    pub headers: Vec<Header>,
    #[prost(string, optional, tag = "6")]
    pub payload_encoding: Option<String>,
    #[prost(string, optional, tag = "7")]
    pub payload_type: Option<String>,
    #[prost(bytes = "vec", optional, tag = "8")]
    pub payload: Option<Vec<u8>>,
    #[prost(string, optional, tag = "9")]
    pub log_id_new: Option<String>,
}

impl Frame {
    pub fn header(&self, key: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|h| h.key == key)
            .map(|h| h.value.as_str())
    }
    pub fn ping(service: i32) -> Self {
        Self {
            service,
            headers: vec![Header {
                key: "type".into(),
                value: "ping".into(),
            }],
            ..Default::default()
        }
    }
    pub fn ack(mut self, code: u16, elapsed: Duration) -> Self {
        self.payload = Some(format!("{{\"code\":{code}}}").into_bytes());
        self.headers.push(Header {
            key: "biz_rt".into(),
            value: elapsed.as_millis().to_string(),
        });
        self
    }
}

struct Parts {
    deadline: Instant,
    slots: Vec<Option<Vec<u8>>>,
    size: usize,
}

#[derive(Default)]
pub struct Assembler {
    groups: HashMap<(i32, String, String), Parts>,
}
impl Assembler {
    pub fn payload(&mut self, f: &Frame, now: Instant) -> Result<Option<Vec<u8>>, &'static str> {
        const MAX: usize = 2 * 1024 * 1024;
        self.groups.retain(|_, v| v.deadline > now);
        let count: usize = f
            .header("sum")
            .unwrap_or("1")
            .parse()
            .map_err(|_| "invalid_fragment_count")?;
        let index: usize = f
            .header("seq")
            .unwrap_or("0")
            .parse()
            .map_err(|_| "invalid_fragment_index")?;
        let data = f.payload.as_deref().unwrap_or_default();
        if !(1..=128).contains(&count) || index >= count || data.len() > MAX {
            return Err("invalid_fragment");
        }
        if count == 1 {
            return Ok(Some(data.to_vec()));
        }
        let key = (
            f.service,
            f.header("type").ok_or("missing_type")?.into(),
            f.header("message_id")
                .filter(|s| !s.is_empty())
                .ok_or("missing_message_id")?
                .into(),
        );
        if self.groups.len() >= 64 && !self.groups.contains_key(&key) {
            return Err("fragment_capacity");
        }
        let group = self.groups.entry(key.clone()).or_insert_with(|| Parts {
            deadline: now + Duration::from_secs(5),
            slots: vec![None; count],
            size: 0,
        });
        if group.slots.len() != count {
            return Err("fragment_conflict");
        }
        match &group.slots[index] {
            Some(old) if old != data => return Err("fragment_conflict"),
            None => {
                group.size += data.len();
                if group.size > MAX {
                    return Err("fragment_capacity");
                }
                group.slots[index] = Some(data.to_vec());
            }
            _ => {}
        }
        if group.slots.iter().any(Option::is_none) {
            return Ok(None);
        }
        let group = self.groups.remove(&key).unwrap();
        let mut bytes = Vec::with_capacity(group.size);
        for slot in group.slots.into_iter().flatten() {
            bytes.extend(slot);
        }
        Ok(Some(bytes))
    }
}
