use serde_json::{Value, json};

#[cfg(unix)]
fn exchange(path: &std::path::Path, operation: &str) -> Result<Value, &'static str> {
    use std::{
        fs,
        io::{BufRead, BufReader, Read, Write},
        os::unix::{fs::FileTypeExt, net::UnixStream},
        time::Duration,
    };
    if !path.is_absolute() || !fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_socket()) {
        return Err("manager_unavailable");
    }
    let mut socket = UnixStream::connect(path).map_err(|_| "manager_unavailable")?;
    for set_timeout in [UnixStream::set_read_timeout, UnixStream::set_write_timeout] {
        set_timeout(&socket, Some(Duration::from_secs(6))).map_err(|_| "manager_unavailable")?;
    }
    let request = json!({"method":"environment_status","args":{},"request_id":operation});
    writeln!(socket, "{request}").map_err(|_| "manager_unavailable")?;
    let mut bytes = Vec::new();
    BufReader::new(socket)
        .take(262145)
        .read_until(b'\n', &mut bytes)
        .map_err(|_| "manager_unavailable")?;
    if bytes.len() > 262144 || !bytes.ends_with(b"\n") {
        return Err("invalid_manager_response");
    }
    serde_json::from_slice(&bytes).map_err(|_| "invalid_manager_response")
}

#[cfg(not(unix))]
fn exchange(_path: &std::path::Path, _operation: &str) -> Result<Value, &'static str> {
    Err("manager_unavailable")
}

pub fn status(operation: &str) -> Result<Value, &'static str> {
    let address = std::env::var_os("YUKI_ENV_MANAGER_SOCKET").ok_or("manager_unavailable")?;
    let response = exchange(std::path::Path::new(&address), operation)?;
    project_status(&response)
}

fn project_status(response: &Value) -> Result<Value, &'static str> {
    let ready = response["ready"]
        .as_bool()
        .ok_or("invalid_manager_response")?;
    let storage = &response["storage"];
    let size = |field: &str| storage[field].as_u64().ok_or("invalid_manager_response");
    let capacity = size("capacity_bytes")?;
    let used = size("used_bytes")?;
    let available = size("available_bytes")?;
    if used > capacity
        || available > capacity - used
        || response["home"] != "/home/yuki"
        || response["workspace"] != "/workspace"
    {
        return Err("invalid_manager_response");
    }
    Ok(json!({
        "ready":ready,
        "home":"/home/yuki",
        "workspace":"/workspace",
        "storage":{"capacity_bytes":capacity,"used_bytes":used,"available_bytes":available}
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn original_manager_exposes_environment_capacity() {
        if std::env::var_os("YUKI_ENV_TEST_MANAGER").is_some() {
            let value = status("test-original-operation").unwrap();
            assert_eq!(value["ready"], false);
            assert!(value["storage"]["capacity_bytes"].as_u64().unwrap() > 0);
        }
    }

    #[test]
    fn status_projects_only_virtual_paths_and_storage_counts() {
        let mut report = json!({
            "ready":true, "home":"/home/yuki", "workspace":"/workspace",
            "generation":"manager-private", "runs":[{"run_id":"private-run"}],
            "services":[{"name":"private-service"}], "host_available_bytes":400,
            "storage":{"capacity_bytes":100,"used_bytes":60,"available_bytes":35}
        });
        assert_eq!(
            project_status(&report),
            Ok(json!({
                "ready":true, "home":"/home/yuki", "workspace":"/workspace",
                "storage":{"capacity_bytes":100,"used_bytes":60,"available_bytes":35}
            }))
        );
        report["storage"]["available_bytes"] = json!(41);
        assert_eq!(project_status(&report), Err("invalid_manager_response"));
    }
}
