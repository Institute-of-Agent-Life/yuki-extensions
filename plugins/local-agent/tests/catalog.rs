#[path = "../src/catalog.rs"]
mod catalog;
use std::time::{SystemTime, UNIX_EPOCH};

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
