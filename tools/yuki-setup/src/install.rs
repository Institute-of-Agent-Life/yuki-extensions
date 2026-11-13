use crate::{
    Error,
    archive::{self, Package},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

const BASE_LOCK: &[u8] = include_bytes!("../inputs/base-1.0.json");
const CANDIDATE_LOCK: &[u8] = include_bytes!("../inputs/native.lock.json");
const OPTIONAL_LOCK: &[u8] = include_bytes!("../inputs/web-fetch.lock.json");
const PLUGIN_DIRECTORY: &str = "plugins/web-fetch";
const PLUGIN_BINARY: &str = "yuki-web-fetch.exe";

#[derive(Deserialize)]
struct BinaryPin {
    archive_sha256: String,
    binary_sha256: String,
}

#[derive(Deserialize)]
struct FrozenPlugin {
    sha256: String,
    members: BTreeMap<String, String>,
}

#[derive(Deserialize)]
struct BaseLock {
    source_commit: String,
    version: String,
    signer: String,
    platforms: BTreeMap<String, BinaryPin>,
    verifiers: BTreeMap<String, String>,
    windows_web_fetch: FrozenPlugin,
}

#[derive(Deserialize)]
struct BaseManifest {
    format: String,
    version: String,
    source_commit: String,
    source_tree_sha256: String,
    platform: [String; 2],
    binary: String,
    members: BTreeMap<String, String>,
    methods: Vec<String>,
}

#[derive(Deserialize)]
struct Support {
    source_commit: String,
    source_tree_sha256: String,
    source_dirty: bool,
    methods: Vec<String>,
    files: BTreeMap<String, String>,
}

#[derive(Deserialize)]
struct CandidateLock {
    source_commit: String,
    fixtures_sha256: String,
    native: BTreeMap<String, CandidatePin>,
}

#[derive(Deserialize)]
struct CandidatePin {
    #[serde(flatten)]
    binary: BinaryPin,
    signer: String,
    signer_sha256: String,
}

#[derive(Deserialize)]
struct CandidateManifest {
    os: String,
    arch: String,
    source_commit: String,
    dirty: bool,
    status: String,
    binary_profile: String,
    host_schema_sha256: String,
    members: BTreeMap<String, CandidateMember>,
    implemented_methods: Vec<String>,
    sdk_versions: Value,
}

#[derive(Deserialize)]
struct CandidateMember {
    bytes: u64,
    sha256: String,
}

#[derive(Deserialize)]
struct OptionalPlugin {
    target: String,
    binary_sha256: String,
    required_host_schema_sha256: String,
    manifest: String,
}

#[derive(Deserialize)]
struct Plugin {
    id: String,
    grants: Vec<String>,
    env: Vec<String>,
}

#[derive(Serialize)]
pub(crate) struct InstalledBase {
    version: String,
    source: String,
    binary: String,
    platform: String,
    plugins: Vec<&'static str>,
}

fn target() -> (&'static str, &'static str) {
    let system = if cfg!(target_os = "macos") {
        "darwin"
    } else {
        std::env::consts::OS
    };
    let arch = if cfg!(target_arch = "aarch64") {
        "arm64"
    } else {
        std::env::consts::ARCH
    };
    (system, arch)
}

fn exe_name(base: &str) -> String {
    format!("bin/{base}{}", std::env::consts::EXE_SUFFIX)
}

fn executable(raw: &[u8], expected: (&str, &str)) -> Result<(), Error> {
    let actual = if raw.starts_with(b"MZ") && raw.len() >= 64 {
        let offset = u32::from_le_bytes(raw[60..64].try_into()?) as usize;
        let bytes = raw.get(offset..).ok_or("invalid PE offset")?;
        match bytes.get(..6) {
            Some(b"PE\0\0\x64\x86") => ("windows", "x86_64"),
            Some(b"PE\0\0\x64\xaa") => ("windows", "arm64"),
            _ => return Err("invalid PE header".into()),
        }
    } else if raw.starts_with(b"\x7fELF\x02\x01") {
        match raw.get(18..20) {
            Some(b"\x3e\0") => ("linux", "x86_64"),
            Some(b"\xb7\0") => ("linux", "arm64"),
            _ => return Err("invalid ELF header".into()),
        }
    } else if raw.starts_with(b"\xcf\xfa\xed\xfe") {
        match raw.get(4..8) {
            Some(b"\x07\0\0\x01") => ("darwin", "x86_64"),
            Some(b"\x0c\0\0\x01") => ("darwin", "arm64"),
            _ => return Err("invalid Mach-O header".into()),
        }
    } else {
        return Err("unknown native executable header".into());
    };
    if actual != expected {
        return Err("executable header differs from signed target".into());
    }
    Ok(())
}

fn new_destination(path: &Path) -> Result<PathBuf, Error> {
    let path = std::path::absolute(path)?;
    if path.file_name().is_none() || path.symlink_metadata().is_ok() {
        return Err("native destination must be new".into());
    }
    Ok(path)
}

#[cfg(unix)]
fn publish(stage: &Path, destination: &Path) -> io::Result<()> {
    use rustix::fs::{CWD, RenameFlags, renameat_with};
    renameat_with(CWD, stage, CWD, destination, RenameFlags::NOREPLACE)?;
    Ok(())
}

#[cfg(windows)]
fn publish(stage: &Path, destination: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::MoveFileExW;

    let stage: Vec<_> = stage.as_os_str().encode_wide().chain([0]).collect();
    let destination: Vec<_> = destination.as_os_str().encode_wide().chain([0]).collect();
    // Both paths are NUL-terminated and remain live until the call returns.
    if unsafe { MoveFileExW(stage.as_ptr(), destination.as_ptr(), 0) } == 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn install_files(
    destination: &Path,
    materialize: impl FnOnce(&Path) -> Result<(), Error>,
) -> Result<(), Error> {
    let parent = destination.parent().ok_or("missing installation parent")?;
    let temporary = tempfile::Builder::new()
        .prefix(".yuki-native-")
        .tempdir_in(parent)?;
    let stage = temporary.path().join("installation");
    fs::create_dir(&stage)?;
    materialize(&stage)?;
    publish(&stage, destination)?;
    Ok(())
}

fn initialize_plugin(
    stage: &Path,
    destination: &Path,
    host: &str,
    manifest: &str,
    lexical: bool,
) -> Result<(), Error> {
    let plugin: Plugin = toml::from_str(manifest)?;
    let (_, tools) = manifest
        .split_once("[[tools]]")
        .ok_or("missing optional tool declaration")?;
    let owner = stage.join("owner");
    let mut command = Command::new(stage.join(host));
    command.arg("--data").arg(&owner).arg("init");
    if lexical {
        command.args(["--memory-mode", "lexical-only"]);
    }
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    let deadline = Instant::now() + Duration::from_secs(if lexical { 30 } else { 20 });
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => break,
            Ok(Some(_)) => return Err("optional plugin owner initialization failed".into()),
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(20)),
            result => {
                let _ = child.kill();
                child.wait()?;
                result?;
                return Err("optional plugin owner initialization timed out".into());
            }
        }
    }
    let program = destination.join(PLUGIN_DIRECTORY).join(PLUGIN_BINARY);
    let program = program.to_str().ok_or("non-UTF-8 plugin destination")?;
    let mut config = OpenOptions::new()
        .append(true)
        .open(owner.join("yuki.toml"))?;
    writeln!(config, "\n[[plugins]]")?;
    writeln!(config, "id = {}", serde_json::to_string(&plugin.id)?)?;
    writeln!(config, "namespace = \"official.web-fetch\"")?;
    if !lexical {
        writeln!(config, "program = {}", serde_json::to_string(program)?)?;
    }
    writeln!(
        config,
        "grants = {}",
        serde_json::to_string(&plugin.grants)?
    )?;
    writeln!(config, "env = {}", serde_json::to_string(&plugin.env)?)?;
    if lexical {
        writeln!(config, "program = {}", serde_json::to_string(program)?)?;
    }
    writeln!(config, "[[plugins.tools]]{tools}")?;
    Ok(())
}

pub(crate) fn base(
    path: &Path,
    destination: &Path,
    optional: Option<&Path>,
) -> Result<InstalledBase, Error> {
    let pin: BaseLock = serde_json::from_slice(BASE_LOCK)?;
    let target = target();
    let platform = format!("{}-{}", target.0, target.1);
    let entry = pin
        .platforms
        .get(&platform)
        .ok_or("no verified package on this native target")?;
    if optional.is_some() && target != ("windows", "x86_64") {
        return Err("no verified optional plugin on this target".into());
    }
    let destination = new_destination(destination)?;
    let raw = archive::checked_input(path, &entry.archive_sha256)?;
    let mut package = Package::read(&raw, true)?;
    let signed = package.member("base.json")?;
    archive::signature(
        &signed,
        &package.member("base.json.sig")?,
        &pin.signer,
        "yuki-plugin-base-1.0",
    )?;
    let manifest: BaseManifest = serde_json::from_slice(&signed)?;
    let host = exe_name("yuki-base");
    if manifest.format != "yuki-plugin-base-v1"
        || manifest.version != pin.version
        || manifest.source_commit != pin.source_commit
        || manifest.platform != [target.0, target.1]
        || manifest.binary != host
        || manifest.members.get(&host) != Some(&entry.binary_sha256)
    {
        return Err("unexpected base version, source, platform or executable".into());
    }
    package.inventory(
        manifest
            .members
            .keys()
            .map(String::as_str)
            .chain(["base.json", "base.json.sig"]),
    )?;
    for (name, digest) in &manifest.members {
        package.checked_member(name, digest, None)?;
    }
    for (name, digest) in &pin.verifiers {
        package.checked_member(&format!("ci/{name}"), digest, None)?;
    }
    executable(&package.member(&host)?, target)?;
    verify_base_contract(&mut package, &manifest)?;

    let plugin_raw = optional
        .map(|path| archive::checked_input(path, &pin.windows_web_fetch.sha256))
        .transpose()?;
    let plugin = plugin_raw
        .as_deref()
        .map(|raw| Package::read(raw, false))
        .transpose()?;
    install_files(&destination, |stage| {
        package.extract(stage, &host, true)?;
        if let Some(mut plugin) = plugin {
            plugin.inventory(pin.windows_web_fetch.members.keys().map(String::as_str))?;
            for (name, digest) in &pin.windows_web_fetch.members {
                if name.contains('/') {
                    return Err("unexpected nested optional package member".into());
                }
                plugin.checked_member(name, digest, None)?;
            }
            let manifest = String::from_utf8(plugin.member("plugin.toml")?)?;
            plugin.extract(&stage.join(PLUGIN_DIRECTORY), PLUGIN_BINARY, false)?;
            initialize_plugin(stage, &destination, &host, &manifest, true)?;
        }
        Ok(())
    })?;
    Ok(InstalledBase {
        version: pin.version,
        source: pin.source_commit,
        binary: entry.binary_sha256.clone(),
        platform,
        plugins: optional.into_iter().map(|_| "web-fetch").collect(),
    })
}

fn verify_base_contract(package: &mut Package<'_>, manifest: &BaseManifest) -> Result<(), Error> {
    let freeze: Value =
        serde_json::from_slice(&package.member("protocol/plugin/stable/1.0/freeze.json")?)?;
    let frozen = freeze["methods"]
        .as_object()
        .ok_or("missing frozen methods")?;
    let schema: Value = serde_json::from_slice(&package.member("support/host-schema.json")?)?;
    let methods = schema["methods"]
        .as_object()
        .ok_or("missing base methods")?;
    let support: Support =
        serde_json::from_slice(&package.member("support/support-manifest.json")?)?;
    let expected: BTreeSet<_> = frozen
        .keys()
        .map(String::as_str)
        .chain(["initialize"])
        .collect();
    if schema["status"] != "witnessed-base"
        || methods.keys().ne(frozen.keys())
        || support.source_commit != manifest.source_commit
        || support.source_tree_sha256 != manifest.source_tree_sha256
        || support.source_dirty
        || support.methods != manifest.methods
        || manifest.methods.len() != expected.len()
        || manifest
            .methods
            .iter()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            != expected
    {
        return Err("stable contract differs from signed base".into());
    }
    for (name, spec) in methods {
        if frozen[name].as_str() != Some(&archive::sha256(&serde_json::to_vec(spec)?)) {
            return Err(format!("frozen method semantics differ: {name}").into());
        }
    }
    for (name, digest) in &support.files {
        if manifest.members.get(&format!("support/{name}")) != Some(digest) {
            return Err("stable support inventory differs".into());
        }
    }
    Ok(())
}

pub(crate) fn candidate(
    path: &Path,
    destination: &Path,
    optional: Option<&Path>,
) -> Result<String, Error> {
    let pin: CandidateLock = serde_json::from_slice(CANDIDATE_LOCK)?;
    let target = target();
    let platform = format!("{}/{}", target.0, target.1);
    let entry = pin
        .native
        .get(&platform)
        .ok_or("no pinned host for this native target")?;
    if archive::sha256(entry.signer.as_bytes()) != entry.signer_sha256 {
        return Err("setup signer differs from pin".into());
    }
    let destination = new_destination(destination)?;
    let raw = archive::checked_input(path, &entry.binary.archive_sha256)?;
    let mut package = Package::read(&raw, true)?;
    let signed = package.member("candidate.json")?;
    archive::signature(
        &signed,
        &package.member("candidate.json.sig")?,
        &entry.signer,
        "yuki-core-candidate-v1",
    )?;
    let manifest: CandidateManifest = serde_json::from_slice(&signed)?;
    let host = exe_name("yuki-core");
    if manifest.os != target.0
        || manifest.arch != target.1
        || manifest.source_commit != pin.source_commit
        || manifest.binary_profile != "release"
        || manifest.dirty
        || manifest.status != "unpublished-development-candidate"
        || manifest
            .members
            .get("fixtures/host-boundaries.json")
            .map(|m| &m.sha256)
            != Some(&pin.fixtures_sha256)
        || manifest.members.get(&host).map(|m| &m.sha256) != Some(&entry.binary.binary_sha256)
    {
        return Err("unexpected native candidate contract".into());
    }
    package.inventory(
        manifest
            .members
            .keys()
            .map(String::as_str)
            .chain(["candidate.json", "candidate.json.sig"]),
    )?;
    for (name, member) in &manifest.members {
        package.checked_member(name, &member.sha256, Some(member.bytes))?;
    }
    executable(&package.member(&host)?, target)?;
    let idl = package.checked_member(
        "protocol/host-preview.json",
        &manifest.host_schema_sha256,
        None,
    )?;
    let idl: Value = serde_json::from_slice(&idl)?;
    let methods = idl["methods"]
        .as_object()
        .ok_or("missing candidate methods")?;
    if methods.keys().ne(manifest.implemented_methods.iter()) {
        return Err("signed candidate capabilities differ from IDL".into());
    }
    let sdk: Value = serde_json::from_slice(&package.member("sdk/distributions.json")?)?;
    if sdk["sdk_versions"] != manifest.sdk_versions {
        return Err("candidate SDK version differs".into());
    }
    for role in ["python-sdk", "rust-sdk", "golden", "verification"] {
        let item = &sdk["members"][role];
        let name = item["name"].as_str().ok_or("missing SDK member")?;
        let digest = item["sha256"].as_str().ok_or("missing SDK digest")?;
        package.checked_member(&format!("sdk/{name}"), digest, None)?;
    }
    let plugin = optional
        .map(|path| -> Result<_, Error> {
            let pin: OptionalPlugin = serde_json::from_slice(OPTIONAL_LOCK)?;
            if pin.target != platform
                || pin.required_host_schema_sha256 != manifest.host_schema_sha256
            {
                return Err("no verified optional plugin for the selected host".into());
            }
            let binary = archive::checked_input(path, &pin.binary_sha256)?;
            executable(&binary, target)?;
            Ok((pin, binary))
        })
        .transpose()?;
    install_files(&destination, |stage| {
        package.extract(stage, &host, false)?;
        if let Some((pin, binary)) = plugin {
            let dir = stage.join(PLUGIN_DIRECTORY);
            fs::create_dir_all(&dir)?;
            fs::write(dir.join(PLUGIN_BINARY), binary)?;
            initialize_plugin(stage, &destination, &host, &pin.manifest, false)?;
        }
        Ok(())
    })?;
    Ok(format!(
        "verified native candidate {} {} {}",
        pin.source_commit, platform, entry.binary.archive_sha256
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn commit_refuses_to_replace_even_an_empty_existing_destination() {
        let work = tempfile::tempdir().unwrap();
        let stage = work.path().join("staged");
        let destination = work.path().join("installed");
        fs::create_dir(&stage).unwrap();
        fs::write(stage.join("checked"), b"payload").unwrap();
        fs::create_dir(&destination).unwrap();
        assert!(publish(&stage, &destination).is_err());
        assert_eq!(fs::read_dir(&destination).unwrap().count(), 0);
        fs::remove_dir(&destination).unwrap();
        publish(&stage, &destination).unwrap();
        assert!(!stage.exists());
        assert_eq!(fs::read(destination.join("checked")).unwrap(), b"payload");
    }
}
