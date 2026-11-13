use serde_json::{Value, json};
use std::{
    collections::HashSet,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};

const LIMIT: u64 = 100 * 1024 * 1024;

pub struct Journal {
    _lock: File,
    file: File,
    path: PathBuf,
    pub state: Value,
}

impl Journal {
    pub fn open(path: &Path) -> Result<Self, String> {
        let lock = open_regular(&path.with_extension("lock"), false)?;
        lock.try_lock().map_err(|_| "another subscription writer")?;
        let mut file = open_regular(path, true)?;
        if file.metadata().map_err(|e| e.to_string())?.len() > LIMIT {
            return Err("journal quota reached".into());
        }
        let mut bytes = vec![];
        file.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
        if !bytes.is_empty() && bytes.last() != Some(&b'\n') {
            return Err("incomplete journal; retain for forward repair".into());
        }
        let mut state = json!({"schema":1,"subscriptions":{}});
        for line in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()) {
            state = serde_json::from_slice(line).map_err(|_| "invalid journal record")?;
            if state["schema"] != 1 || !state["subscriptions"].is_object() {
                return Err("unsupported journal schema".into());
            }
        }
        Ok(Self {
            _lock: lock,
            file,
            path: path.into(),
            state,
        })
    }

    pub fn erase(&mut self, ids: &HashSet<i64>) -> Result<(), String> {
        let mut state = self.state.clone();
        let subscriptions = state["subscriptions"]
            .as_object_mut()
            .ok_or("invalid subscriptions")?;
        for subscription in subscriptions.values_mut() {
            if !subscription["publishing"].is_null() {
                return Err("original publication must be reconciled before erasure".into());
            }
            let receipts = subscription["receipts"]
                .as_array_mut()
                .ok_or("invalid receipts")?;
            let mut kept = Vec::with_capacity(receipts.len());
            for row in receipts.iter() {
                let publication = &row["publication"];
                let source = publication["source_event_id"]
                    .as_i64()
                    .ok_or("invalid publication source")?;
                let related = publication["sources"]["ids"]
                    .as_array()
                    .ok_or("missing publication sources")?;
                if publication["sources"]["complete"] != true {
                    return Err("publication dependency set incomplete".into());
                }
                if !ids.contains(&source)
                    && !related
                        .iter()
                        .any(|id| id.as_i64().is_some_and(|id| ids.contains(&id)))
                {
                    kept.push(row.clone());
                }
            }
            *receipts = kept;
        }
        // Historical rows contain the original receipts too. Rewrite the
        // sanitized state even if a previous replacement finished before its ACK.
        let temporary = self.path.with_extension("erasing");
        match fs::remove_file(&temporary) {
            Ok(()) => (),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => (),
            Err(error) => return Err(error.to_string()),
        }
        let mut bytes = serde_json::to_vec(&state).map_err(|e| e.to_string())?;
        bytes.push(b'\n');
        let mut staged = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .map_err(|e| e.to_string())?;
        staged
            .write_all(&bytes)
            .and_then(|()| staged.sync_all())
            .map_err(|e| e.to_string())?;
        drop(staged);
        fs::rename(&temporary, &self.path).map_err(|e| e.to_string())?;
        #[cfg(unix)]
        File::open(self.path.parent().ok_or("journal parent required")?)
            .and_then(|directory| directory.sync_all())
            .map_err(|e| e.to_string())?;
        self.file = open_regular(&self.path, true)?;
        self.state = state;
        Ok(())
    }

    pub fn commit(&mut self, state: Value) -> Result<(), String> {
        if state == self.state {
            return Ok(());
        }
        let mut bytes = serde_json::to_vec(&state).map_err(|e| e.to_string())?;
        bytes.push(b'\n');
        if self.file.metadata().map_err(|e| e.to_string())?.len() + bytes.len() as u64 > LIMIT {
            return Err("journal quota reached; retain original cursor".into());
        }
        self.file
            .write_all(&bytes)
            .and_then(|_| self.file.sync_all())
            .map_err(|e| e.to_string())?;
        self.state = state;
        Ok(())
    }
}

fn open_regular(path: &Path, append: bool) -> Result<File, String> {
    if fs::symlink_metadata(path).is_ok_and(|metadata| !metadata.is_file()) {
        return Err("unsafe subscription state path".into());
    }
    OpenOptions::new()
        .read(true)
        .write(!append)
        .append(append)
        .create(true)
        .open(path)
        .map_err(|e| e.to_string())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn durable_restart_and_truncated_record() {
        let p = std::env::temp_dir().join(format!(
            "subscription-{}-{}.journal",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        {
            let mut j = Journal::open(&p).unwrap();
            assert!(Journal::open(&p).is_err());
            j.commit(
                json!({"schema":1,"subscriptions":{"a":{"pending":[{"event_key":"original"}]}}}),
            )
            .unwrap();
        }
        {
            let j = Journal::open(&p).unwrap();
            assert_eq!(
                j.state["subscriptions"]["a"]["pending"][0]["event_key"],
                "original"
            );
        }
        OpenOptions::new()
            .append(true)
            .open(&p)
            .unwrap()
            .write_all(b"{")
            .unwrap();
        assert!(Journal::open(&p).is_err());
        std::fs::remove_file(&p).unwrap();
        std::fs::remove_file(p.with_extension("lock")).unwrap();
    }

    #[test]
    fn erasure_rewrites_old_rows_and_keeps_the_seen_key() {
        let path = std::env::temp_dir().join(format!(
            "subscription-erase-{}-{}.journal",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let mut journal = Journal::open(&path).unwrap();
        let first = json!({"request":{"payload":"deleted source"},
            "publication":{"source_event_id":12,"sources":{"ids":[12],"complete":true}}});
        let other = json!({"request":{"payload":"preserved source"},
            "publication":{"source_event_id":13,"sources":{"ids":[13],"complete":true}}});
        let state = json!({"schema":1,"subscriptions":{"news":{
            "seen":{"old":true,"other":true},"pending":[],"receipts":[first,other]}}});
        journal.commit(state.clone()).unwrap();
        let mut second = state.clone();
        second["subscriptions"]["news"]["publishing"] = "unknown-operation".into();
        journal.commit(second).unwrap();
        assert!(journal.erase(&HashSet::from([12])).is_err());
        journal.commit(state).unwrap();
        journal.erase(&HashSet::from([12])).unwrap();
        journal.erase(&HashSet::from([12])).unwrap();
        drop(journal);
        let raw = fs::read_to_string(&path).unwrap();
        assert!(!raw.contains("deleted source"));
        let reopened = Journal::open(&path).unwrap();
        let restored = &reopened.state["subscriptions"]["news"];
        assert_eq!(restored["seen"]["old"], true);
        assert_eq!(restored["receipts"], json!([other]));
        drop(reopened);
        fs::remove_file(&path).unwrap();
        fs::remove_file(path.with_extension("lock")).unwrap();
    }
}
