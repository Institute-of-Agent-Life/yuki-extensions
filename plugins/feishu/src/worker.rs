//! One in-flight REST operation leaves the native WebSocket writer responsive.
use crate::{Config, rest};
use serde_json::{Value, json};
use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, SyncSender},
    },
    thread::{self, JoinHandle},
    time::Duration,
};

pub enum Job {
    Media(Value),
    Delivery(Value),
    Recall(Value),
}

pub struct Worker {
    jobs: Option<SyncSender<Job>>,
    pub responses: Receiver<Value>,
    cancelled: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
}

impl Worker {
    pub fn new(cfg: Config, namespace: String) -> Self {
        let (jobs, incoming) = mpsc::sync_channel(1);
        let (completed, responses) = mpsc::sync_channel(1);
        let cancelled = Arc::new(AtomicBool::new(false));
        let cancel = Arc::clone(&cancelled);
        let thread = thread::spawn(move || {
            let mut client = rest::Client::new(Arc::clone(&cancel));
            while !cancel.load(Ordering::SeqCst) {
                let reply = match incoming.recv_timeout(Duration::from_millis(100)) {
                    Ok(Job::Media(params)) => match client.chunk(&cfg, &namespace, params) {
                        Ok(value) => json!({"result":value}),
                        Err(_) => {
                            json!({"error":{"code":-32000,"message":"original resource unavailable"}})
                        }
                    },
                    Ok(Job::Delivery(args)) => json!({"result":client.effect(&cfg, &args, false)}),
                    Ok(Job::Recall(args)) => json!({"result":client.effect(&cfg, &args, true)}),
                    Err(RecvTimeoutError::Timeout) => {
                        client.expire();
                        continue;
                    }
                    Err(RecvTimeoutError::Disconnected) => break,
                };
                if completed.try_send(reply).is_err() {
                    break;
                }
            }
        });
        Self {
            jobs: Some(jobs),
            responses,
            cancelled,
            thread: Some(thread),
        }
    }

    pub fn submit(&self, job: Job) -> bool {
        self.jobs
            .as_ref()
            .is_some_and(|queue| queue.try_send(job).is_ok())
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        self.cancelled.store(true, Ordering::SeqCst);
        self.jobs.take();
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
