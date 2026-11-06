CREATE TABLE connections (
    device_id TEXT PRIMARY KEY NOT NULL REFERENCES devices(device_id),
    journal_namespace TEXT NOT NULL,
    connection_epoch INTEGER NOT NULL CHECK(connection_epoch > 0),
    connected INTEGER NOT NULL DEFAULT 0 CHECK(connected IN (0,1)),
    device_capabilities_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE instances (
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    instance_id TEXT NOT NULL,
    catalog_json TEXT NOT NULL,
    PRIMARY KEY(device_id, instance_id)
);
PRAGMA user_version=2;
