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
    // The Manager's full status contains other runs, services and host paths.
    let ready = response["ready"]
        .as_bool()
        .ok_or("invalid_manager_response")?;
    Ok(json!({"ready":ready}))
}
