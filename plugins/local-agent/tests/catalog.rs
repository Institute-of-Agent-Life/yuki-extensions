#[path = "../src/catalog.rs"]
mod catalog;
use std::time::{SystemTime, UNIX_EPOCH};
use catalog::Catalog;
use rusqlite::Connection;
use serde_json::json;

#[test]
fn reopening_is_idempotent_and_rejects_foreign_databases() {
    let state = std::env::temp_dir().join(format!(
        "yuki-catalog-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let db = catalog::Catalog::open(&state).unwrap();
    db.paired("paired-without-instance").unwrap();
    db.paired("paired-without-instance").unwrap();
    drop(db);
    assert_eq!(
        catalog::Catalog::open(&state).unwrap().devices().unwrap(),
        ["paired-without-instance"]
    );
    let foreign = state.join("foreign");
    std::fs::create_dir(&foreign).unwrap();
    let path = foreign.join("device-catalog.sqlite3");
    let existing = rusqlite::Connection::open(&path).unwrap();
    existing
        .execute_batch("CREATE TABLE original(value); INSERT INTO original VALUES(17)")
        .unwrap();
    drop(existing);
    assert!(catalog::Catalog::open(&foreign).is_err());
    let existing = rusqlite::Connection::open(&path).unwrap();
    assert_eq!(
        existing
            .query_row("SELECT value FROM original", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        17
    );
    drop(existing);
    std::fs::remove_dir_all(state).unwrap();
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn migration_keeps_paired_device_and_fences_replacement() {
        let dir = tempfile::tempdir().unwrap();
        let db = Connection::open(dir.path().join("device-catalog.sqlite3")).unwrap();
        db.execute_batch(include_str!("../migrations/001_catalog.sql")).unwrap();
        db.execute("INSERT INTO devices VALUES ('original')", []).unwrap();
        drop(db);
        let mut catalog = Catalog::open(dir.path()).unwrap();
        assert_eq!(catalog.devices().unwrap(), ["original"]);
        assert!(catalog.attach("original", "stable", 10).unwrap());
        assert!(catalog.replace("original", 10, &json!({}), &[json!({"id":"old"})]).unwrap());
        assert!(catalog.attach("original", "stable", 11).unwrap());
        assert!(!catalog.replace("original", 10, &json!({}), &[json!({"id":"late"})]).unwrap());
        assert!(!catalog.disconnect("original", 10).unwrap());
        assert!(catalog.replace("original", 11, &json!({"tty":false}), &[]).unwrap());
        let value = catalog.snapshot().unwrap();
        assert_eq!(value["catalog"][0]["instances"], json!([]));
        assert_eq!(value["catalog"][0]["connected"], true);
        assert_eq!(value["catalog"][0]["journal_namespace"], "stable");
        assert!(!catalog.attach("original", "new-namespace", 12).unwrap());
        assert!(!catalog.attach("original", "stable", 9).unwrap());
        catalog.shutdown();
        assert!(!catalog.replace("original", 11, &json!({}), &[]).unwrap());
    }
    #[test]
    fn incomplete_snapshot_rolls_back_and_unknown_schema_is_preserved() {
        let dir = tempfile::tempdir().unwrap();
        let mut catalog = Catalog::open(dir.path()).unwrap();
        catalog.attach("device", "namespace", 1).unwrap();
        catalog.replace("device", 1, &json!({}), &[json!({"id":"retained"})]).unwrap();
        assert!(catalog.replace("device", 1, &json!({}), &[json!({"id":"duplicate"}),json!({"id":"duplicate"})]).is_err());
        assert_eq!(catalog.snapshot().unwrap()["catalog"][0]["instances"], json!([{"id":"retained"}]));
        drop(catalog);
        let db = Connection::open(dir.path().join("device-catalog.sqlite3")).unwrap();
        db.execute_batch("PRAGMA user_version=99").unwrap();
        drop(db);
        assert!(Catalog::open(dir.path()).is_err());
        let db = Connection::open(dir.path().join("device-catalog.sqlite3")).unwrap();
        assert_eq!(db.query_row("PRAGMA user_version", [], |r| r.get::<_, i64>(0)).unwrap(), 99);
    }
}
