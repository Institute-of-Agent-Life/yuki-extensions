//! The plugin owns device membership in its catalog. Credentials remain with the Host.
use rusqlite::{Connection, params};
use serde_json::{Value, json};
use std::{path::Path, time::Duration};

pub struct Catalog(Connection, bool);

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
            (1498172225, 1 | 2) => (),
            _ => return Err("incompatible device catalog".into()),
        }
        if version <= 1 { tx.execute_batch(include_str!("../migrations/002_connections.sql"))?; }
        tx.commit()?;
        Ok(Self(db, true))
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
    pub fn startup(&mut self) -> rusqlite::Result<()> {
        self.0.execute("UPDATE connections SET connected=0", [])?;
        Ok(())
    }
    pub fn shutdown(&mut self) {
        self.1 = false;
        let _ = self.0.execute("UPDATE connections SET connected=0", []);
    }
    pub fn attach(&mut self, device: &str, namespace: &str, epoch: i64) -> rusqlite::Result<bool> {
        if !self.1 || epoch <= 0 { return Ok(false); }
        let tx = self.0.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        let previous = tx.query_row("SELECT journal_namespace,connection_epoch FROM connections WHERE device_id=?1", [device],
            |r| Ok((r.get::<_, String>(0)?, r.get::<_, i64>(1)?)));
        match previous {
            Ok((ns, old)) if ns != namespace || old >= epoch => return Ok(false),
            Err(rusqlite::Error::QueryReturnedNoRows) | Ok(_) => (),
            Err(error) => return Err(error),
        }
        tx.execute("INSERT INTO devices(device_id) VALUES (?1) ON CONFLICT DO NOTHING", [device])?;
        tx.execute("INSERT INTO connections(device_id,journal_namespace,connection_epoch) VALUES (?1,?2,?3) ON CONFLICT(device_id) DO UPDATE SET connection_epoch=excluded.connection_epoch,connected=0", params![device, namespace, epoch])?;
        tx.commit()?;
        Ok(true)
    }
    pub fn replace(&mut self, device: &str, epoch: i64, capabilities: &Value, instances: &[Value]) -> rusqlite::Result<bool> {
        if !self.1 { return Ok(false); }
        let tx = self.0.transaction_with_behavior(rusqlite::TransactionBehavior::Immediate)?;
        if tx.execute("UPDATE connections SET connected=1,device_capabilities_json=?3 WHERE device_id=?1 AND connection_epoch=?2",
                      params![device, epoch, capabilities.to_string()])? != 1 { return Ok(false); }
        tx.execute("DELETE FROM instances WHERE device_id=?1", [device])?;
        for item in instances {
            tx.execute("INSERT INTO instances(device_id,instance_id,catalog_json) VALUES (?1,?2,?3)",
                params![device, item["id"].as_str().unwrap(), item.to_string()])?;
        }
        tx.commit()?;
        Ok(true)
    }
    pub fn disconnect(&mut self, device: &str, epoch: i64) -> rusqlite::Result<bool> {
        Ok(self.0.execute("UPDATE connections SET connected=0 WHERE device_id=?1 AND connection_epoch=?2", params![device, epoch])? == 1)
    }
    pub fn snapshot(&self) -> rusqlite::Result<Value> {
        let mut statement = self.0.prepare("SELECT d.device_id,c.journal_namespace,c.connection_epoch,c.connected,c.device_capabilities_json FROM devices d LEFT JOIN connections c ON c.device_id=d.device_id ORDER BY d.device_id")?;
        let mut result = Vec::new();
        let rows = statement.query_map([], |r| Ok((r.get::<_, String>(0)?,r.get::<_, Option<String>>(1)?,r.get::<_, Option<i64>>(2)?,r.get::<_, Option<bool>>(3)?,r.get::<_, Option<String>>(4)?)))?;
        for row in rows {
            let (device, namespace, epoch, connected, capabilities) = row?;
            let items = self.0.prepare("SELECT catalog_json FROM instances WHERE device_id=?1 ORDER BY instance_id")?
                .query_map([&device], |r| r.get::<_, String>(0))?.collect::<rusqlite::Result<Vec<_>>>()?;
            result.push(json!({"device_id":device,"journal_namespace":namespace,"connection_epoch":epoch,
                "connected":connected.unwrap_or(false),"device_capabilities":capabilities.and_then(|s| serde_json::from_str::<Value>(&s).ok()).unwrap_or(json!({})),
                "instances":items.iter().map(|s| serde_json::from_str::<Value>(s).unwrap()).collect::<Vec<_>>()}));
        }
        Ok(json!({"devices":self.devices()?,"catalog":result}))
    }
}
