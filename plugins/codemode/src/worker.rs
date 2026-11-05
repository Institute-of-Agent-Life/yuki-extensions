use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    io::{BufRead, BufReader, Read, Write},
    process::{Child, ChildStdin, Command, Stdio},
    sync::{atomic::{AtomicBool, Ordering}, mpsc},
    thread,
    time::{Duration, Instant},
};
pub type Result<T> = std::result::Result<T, String>;

const MAX_FRAME: usize = 20 * 1024 * 1024;
const SECCOMP_SHA: &str = "57457313430e0bb513ccab8a6906c5e05ffc217459f9c5b01cc77d827dcedc81";
pub fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
pub fn field<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v[key].as_str().ok_or_else(|| format!("missing_{key}"))
}
pub fn same_contract(a: &Value, b: &Value) -> bool {
    ["abi", "engine_sha256", "launcher_sha256", "codec_sha256"].iter().all(|k| {
        a[*k].as_str().is_some_and(|x| !x.is_empty() && b[*k].as_str() == Some(x))
    })
}

// This process is a trusted Docker client. Script bytes only enter the isolated
// codec's stdin; they are never command arguments, shell commands or host files.
pub struct Worker {
    socket: String,
    container: String,
    child: Option<Child>,
    input: Option<ChildStdin>,
    replies: mpsc::Receiver<Result<Value>>,
    pub contract: Value,
}

fn docker(socket: &str) -> Command {
    let mut command = Command::new("docker");
    command.args(["--host", socket]).env_remove("DOCKER_CONTEXT");
    command
}

fn command(mut command: Command) -> Result<Vec<u8>> {
    let mut child = command.stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::null())
        .spawn().map_err(|_| "runtime_command_unavailable")?;
    let mut output = child.stdout.take().ok_or("runtime_stdout_missing")?;
    let reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        output.by_ref().take(1024 * 1024 + 1).read_to_end(&mut bytes).map(|_| bytes)
    });
    let deadline = Instant::now() + Duration::from_secs(20);
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
            _ => { let _ = child.kill(); let _ = child.wait(); break None; }
        }
    };
    let bytes = reader.join().map_err(|_| "runtime_reader_failed")?
        .map_err(|_| "runtime_read_failed")?;
    if bytes.len() > 1024 * 1024 || !status.is_some_and(|s| s.success()) {
        return Err("runtime_command_failed".into());
    }
    Ok(bytes)
}

impl Worker {
    pub fn start(cancel: &AtomicBool) -> Result<Self> {
        if !cfg!(target_os = "linux") { return Err("runtime_abi_unavailable".into()); }
        if cancel.load(Ordering::Acquire) { return Err("cancelled".into()); }
        let path = std::env::var("YUKI_CODE_RUNTIME_CONFIG").map_err(|_| "runtime_not_installed")?;
        let bytes = std::fs::read(path).map_err(|_| "runtime_config_unavailable")?;
        if bytes.len() > 1024 * 1024 { return Err("runtime_config_too_large".into()); }
        let config: Value = serde_json::from_slice(&bytes).map_err(|_| "runtime_config_invalid")?;
        let image = field(&config, "image_id")?;
        let hex = image.strip_prefix("sha256:").ok_or("runtime_image_not_pinned")?;
        if hex.len() != 64 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("runtime_image_not_pinned".into());
        }
        let socket = field(&config, "docker_socket")?.to_owned();
        if !socket.starts_with("unix:///") { return Err("runtime_requires_local_daemon".into()); }
        let policy = field(&config, "seccomp_path")?;
        if digest(&std::fs::read(policy).map_err(|_| "runtime_seccomp_unavailable")?) != SECCOMP_SHA {
            return Err("runtime_seccomp_mismatch".into());
        }
        let profiles = std::fs::read_to_string("/sys/kernel/security/apparmor/profiles")
            .map_err(|_| "runtime_apparmor_unavailable")?;
        for profile in ["yuki-bot-codemode", "yuki-bot-codemode//launcher", "yuki-bot-codemode//launcher//worker"] {
            if !profiles.lines().any(|line| line == format!("{profile} (enforce)")) {
                return Err("runtime_apparmor_not_enforced".into());
            }
        }
        let contract = config["contract"].clone();
        if !same_contract(&contract, &contract) { return Err("runtime_contract_invalid".into()); }
        let mut create = docker(&socket);
        create.args(["create", "--init", "--interactive", "--attach", "stdin", "--attach", "stdout",
            "--user", "10001:10001", "--cap-drop", "ALL", "--network", "none", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m", "--pids-limit", "64", "--memory", "1g",
            "--security-opt", "apparmor=yuki-bot-codemode",
            "--security-opt", &format!("seccomp={policy}"), image]);
        let container = String::from_utf8(command(create)?).map_err(|_| "runtime_container_id_invalid")?.trim().to_owned();
        if container.len() != 64 || !container.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err("runtime_container_id_invalid".into());
        }
        let (_tx, replies) = mpsc::sync_channel(1);
        let mut worker = Self { socket, container, child: None, input: None, replies, contract };
        if let Err(error) = worker.initialize(cancel) {
            if !worker.close() { return Err("temporary_cleanup_failed".into()); }
            return Err(error);
        }
        Ok(worker)
    }

    fn initialize(&mut self, cancel: &AtomicBool) -> Result<()> {
        let (tx, replies) = mpsc::sync_channel(1);
        self.replies = replies;
        let mut inspect = docker(&self.socket);
        inspect.args(["inspect", &self.container]);
        let inspection: Value = serde_json::from_slice(&command(inspect)?).map_err(|_| "runtime_inspection_invalid")?;
        if inspection[0]["Config"]["StdinOnce"] != true { return Err("runtime_disconnect_cleanup_unavailable".into()); }
        let mut attach = docker(&self.socket);
        attach.args(["start", "--attach", "--interactive", &self.container]);
        let mut child = attach.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null())
            .spawn().map_err(|_| "runtime_attach_failed")?;
        self.input = child.stdin.take();
        let stdout = child.stdout.take().ok_or("runtime_stdout_missing")?;
        self.child = Some(child);
        thread::spawn(move || {
            let mut input = BufReader::new(stdout);
            loop {
                let mut raw = Vec::new();
                let result = input.by_ref().take(MAX_FRAME as u64 + 1).read_until(b'\n', &mut raw);
                let value = match result {
                    Ok(0) => break,
                    Ok(_) if raw.len() <= MAX_FRAME && raw.last() == Some(&b'\n') =>
                        serde_json::from_slice(&raw).map_err(|_| "runtime_frame_invalid".into()),
                    _ => Err("runtime_frame_too_large_or_truncated".into()),
                };
                let stop = value.is_err();
                if tx.send(value).is_err() || stop { break; }
            }
        });
        let ready = self.receive(cancel)?;
        if ready["ready"] != true || !same_contract(&ready["contract"], &self.contract) {
            return Err("runtime_contract_mismatch".into());
        }
        Ok(())
    }

    fn receive(&self, cancel: &AtomicBool) -> Result<Value> {
        let deadline = Instant::now() + Duration::from_secs(45);
        loop {
            if cancel.load(Ordering::Acquire) { return Err("cancelled".into()); }
            if Instant::now() >= deadline { return Err("runtime_watchdog".into()); }
            match self.replies.recv_timeout(Duration::from_millis(25)) {
                Ok(value) => return value,
                Err(mpsc::RecvTimeoutError::Timeout) => (),
                Err(mpsc::RecvTimeoutError::Disconnected) => return Err("runtime_disconnected".into()),
            }
        }
    }
    pub fn exchange(&mut self, request: &Value, cancel: &AtomicBool) -> Result<Value> {
        if cancel.load(Ordering::Acquire) { return Err("cancelled".into()); }
        let mut bytes = serde_json::to_vec(request).map_err(|_| "runtime_request_invalid")?;
        bytes.push(b'\n');
        if bytes.len() > MAX_FRAME { return Err("runtime_request_too_large".into()); }
        self.input.as_mut().ok_or("runtime_disconnected")?.write_all(&bytes)
            .and_then(|_| self.input.as_mut().unwrap().flush()).map_err(|_| "runtime_write_failed")?;
        let result = self.receive(cancel)?;
        if result.get("error").is_some() { return Err("runtime_codec_unavailable".into()); }
        Ok(result)
    }
    pub fn close(&mut self) -> bool {
        self.input.take();
        if self.container.is_empty() { return true; }
        let mut remove = docker(&self.socket);
        remove.args(["rm", "--force", &self.container]);
        let removed = command(remove).is_ok();
        if let Some(mut child) = self.child.take() { let _ = child.kill(); let _ = child.wait(); }
        if removed { self.container.clear(); }
        removed
    }
}
impl Drop for Worker { fn drop(&mut self) { self.close(); } }
