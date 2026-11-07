//! Volatile original-chat typing leases, independent of business delivery receipts.
use crate::{social, transport};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    time::{Duration, Instant},
};

struct Lease {
    route: Value,
    payload: Value,
    expires: Instant,
    next: Instant,
}

struct Pending {
    lease: String,
    started: Instant,
    transfer: transport::Request,
}

#[derive(Default)]
pub struct Activity {
    leases: BTreeMap<String, Lease>,
    pending: Option<Pending>,
}

impl Activity {
    pub fn receive(&mut self, params: &Value, bot: i64, now: Instant) {
        let Some(id) = params["lease_id"].as_str().filter(|id| !id.is_empty()) else {
            return;
        };
        let Ok((chat, topic)) = social::route(params, bot) else {
            return;
        };
        if params["ttl_ms"] != 5000 || params["route"]["entry"].as_str().is_none_or(str::is_empty) {
            return;
        }
        // A lease keeps its original route even if a malformed later notice changes it.
        if self
            .leases
            .get(id)
            .is_some_and(|lease| lease.route != params["route"])
        {
            return;
        }
        if params["enabled"] == false {
            self.leases.remove(id);
            if self.pending.as_ref().is_some_and(|p| p.lease == id) {
                self.pending = None;
            }
            return;
        }
        if params["enabled"] != true {
            return;
        }
        if let Some(lease) = self.leases.get_mut(id) {
            lease.expires = now + Duration::from_secs(5);
            return;
        }
        if self.leases.len() >= 32 {
            return;
        }
        let mut payload = json!({"chat_id":chat,"action":"typing"});
        if let Some(topic) = topic {
            payload["message_thread_id"] = topic.into();
        }
        self.leases.insert(
            id.to_owned(),
            Lease {
                route: params["route"].clone(),
                payload,
                expires: now + Duration::from_secs(5),
                next: now,
            },
        );
    }

    pub fn clear(&mut self) {
        self.leases.clear();
        self.pending = None;
    }

    pub fn tick(&mut self, base: &str, token: &str, now: Instant) {
        self.leases.retain(|_, lease| lease.expires > now);
        if let Some(pending) = self.pending.as_mut() {
            // A stuck UI request is cancelled without waiting for the delivery transfer.
            if !self.leases.contains_key(&pending.lease)
                || now.duration_since(pending.started) >= Duration::from_secs(2)
                || pending.transfer.ready().unwrap_or(true)
            {
                self.pending = None;
            }
        }
        if self.pending.is_some() {
            return;
        }
        let Some((id, lease)) = self
            .leases
            .iter_mut()
            .filter(|(_, lease)| lease.next <= now)
            .min_by_key(|(_, lease)| lease.next)
        else {
            return;
        };
        lease.next = now + Duration::from_secs(3);
        if let Ok(transfer) = transport::start_with_timeout(
            &format!("{base}/bot{token}/sendChatAction"),
            Some(&lease.payload),
            4096,
            2,
        ) {
            self.pending = Some(Pending {
                lease: id.clone(),
                started: now,
                transfer,
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn notice() -> Value {
        json!({"lease_id":"turn-1","route":{"entry":"original","bot":"101","chat":"-15","topic":"7"},"enabled":true,"ttl_ms":5000})
    }

    #[test]
    fn original_route_renewal_and_end_are_bounded() {
        let now = Instant::now();
        let mut activity = Activity::default();
        let mut params = notice();
        activity.receive(&params, 202, now);
        assert!(activity.leases.is_empty());
        activity.receive(&params, 101, now);
        assert_eq!(
            activity.leases["turn-1"].payload,
            json!({"chat_id":"-15","message_thread_id":7,"action":"typing"})
        );
        params["route"]["chat"] = json!("-16");
        activity.receive(&params, 101, now + Duration::from_secs(2));
        assert_eq!(
            activity.leases["turn-1"].expires,
            now + Duration::from_secs(5)
        );
        params = notice();
        activity.receive(&params, 101, now + Duration::from_secs(2));
        assert_eq!(
            activity.leases["turn-1"].expires,
            now + Duration::from_secs(7)
        );
        assert_eq!(activity.leases["turn-1"].next, now);
        params["enabled"] = json!(false);
        activity.receive(&params, 101, now);
        assert!(activity.leases.is_empty());
        for n in 0..40 {
            params = notice();
            params["lease_id"] = json!(format!("turn-{n}"));
            activity.receive(&params, 101, now);
        }
        assert_eq!(activity.leases.len(), 32);
        activity.clear();
        assert!(activity.leases.is_empty());
    }

    #[test]
    fn lost_lease_expires_before_any_new_native_request() {
        let now = Instant::now();
        let mut activity = Activity::default();
        activity.receive(&notice(), 101, now);
        activity.tick("invalid-endpoint", "", now + Duration::from_secs(5));
        assert!(activity.leases.is_empty());
        assert!(activity.pending.is_none());
    }
}
