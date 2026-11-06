//! The plugin owns device membership in its catalog. Credentials remain with the Host.
use rusqlite::Connection;
use std::{path::Path, time::Duration};

pub struct Catalog(Connection);

impl Catalog {
    pub fn open(state: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        if !state.is_absolute() {
            return Err("state directory must be absolute".into());
        }
        std::fs::create_dir_all(state)?;
        let mut db = Connection::open(state.join("device-catalog.sqlite3"))?;
        db.busy_timeout(Duration::from_secs(5))?;
        let tx = db.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let version: i64 = tx.query_row("PRAGMA user_version", [], |r| r.get(0))?;
        let app: i64 = tx.query_row("PRAGMA application_id", [], |r| r.get(0))?;
        match (app, version) {
            (0, 0) => {
                let occupied: bool =
                    tx.query_row("SELECT EXISTS(SELECT 1 FROM sqlite_schema)", [], |r| {
                        r.get(0)
                    })?;
                if occupied {
                    return Err("unrecognized device catalog".into());
                }
                tx.execute_batch(include_str!("../migrations/001_catalog.sql"))?;
            }
            (1498172225, 1) => (),
            _ => return Err("incompatible device catalog".into()),
        }
        tx.commit()?;
        Ok(Self(db))
    }
    pub fn paired(&self, device: &str) -> rusqlite::Result<()> {
        self.0.execute(
            "INSERT INTO devices(device_id) VALUES (?1) ON CONFLICT(device_id) DO NOTHING",
            [device],
        )?;
        Ok(())
    }
    pub fn devices(&self) -> rusqlite::Result<Vec<String>> {
        self.0
            .prepare("SELECT device_id FROM devices ORDER BY device_id")?
            .query_map([], |r| r.get(0))?
            .collect()
    }
}
