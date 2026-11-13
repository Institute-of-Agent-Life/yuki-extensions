use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet, HashSet},
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
};

type Result<T> = std::result::Result<T, String>;

pub fn lock(root: &Path) -> io::Result<File> {
    let path = root.join(".worker.lock");
    if fs::symlink_metadata(&path).is_ok_and(|m| !m.is_file()) {
        return Err(io::Error::other("unsafe rebuild worker lock"));
    }
    let handle = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    handle.try_lock()?;
    Ok(handle)
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
enum Role {
    Primary,
    Context,
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Selection {
    event: u64,
    role: Role,
}

#[derive(Deserialize, Serialize)]
struct Source {
    event: u64,
    role: Role,
    version: String,
}

#[derive(Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum Mode {
    FunctionTool,
    TextJson,
    JsonSchema,
}

#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Plan {
    scope: String,
    route: String,
    mode: Mode,
    sources: Vec<Selection>,
}

#[derive(Deserialize)]
#[serde(tag = "action", deny_unknown_fields)]
enum Job {
    #[serde(rename = "rebuild.preview")]
    Preview { batch: String, plan: Plan },
    #[serde(rename = "rebuild.apply")]
    Apply {
        batch: String,
        preview: String,
        operation: String,
        approved: Vec<u64>,
    },
    #[serde(rename = "rebuild.status")]
    Status { batch: String },
    #[serde(rename = "rebuild.read")]
    Read { batch: String, offset: u64 },
    #[serde(rename = "rebuild.pause")]
    Pause { batch: String },
    #[serde(rename = "rebuild.resume")]
    Resume { batch: String },
    #[serde(rename = "rebuild.cancel")]
    Cancel { batch: String },
}

impl Job {
    fn batch(&self) -> &str {
        match self {
            Self::Preview { batch, .. }
            | Self::Apply { batch, .. }
            | Self::Status { batch }
            | Self::Read { batch, .. }
            | Self::Pause { batch }
            | Self::Resume { batch }
            | Self::Cancel { batch } => batch,
        }
    }

    fn selected_sources(&self) -> &[Selection] {
        match self {
            Self::Preview { plan, .. } => &plan.sources,
            _ => &[],
        }
    }
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "phase", rename_all = "snake_case")]
enum Phase {
    Selecting,
    Prepared {
        sources: Vec<Source>,
    },
    Review {
        preview: String,
        count: u64,
        content: Value,
        sources: Vec<Source>,
        approvals: BTreeMap<String, Vec<u64>>,
        pending: Option<String>,
    },
    Forgotten,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Execution {
    Active,
    Paused,
    Cancelled,
}

#[derive(Deserialize, Serialize)]
struct Batch {
    version: u32,
    plan: Plan,
    jobs: BTreeSet<String>,
    execution: Execution,
    phase: Phase,
}

#[derive(Deserialize, Serialize)]
struct Approval {
    operation: String,
    ordinals: Vec<u64>,
}

pub(crate) fn sync_dir(path: &Path) -> io::Result<()> {
    #[cfg(unix)]
    File::open(path)?.sync_all()?;
    #[cfg(not(unix))]
    let _ = path;
    Ok(())
}

pub fn write_json(path: &Path, value: &impl Serialize) -> Result<()> {
    let parent = path.parent().ok_or("missing state directory")?;
    let temp = path.with_extension(format!(
        "{}.tmp",
        path.extension().and_then(|s| s.to_str()).unwrap_or("state")
    ));
    let written = (|| -> io::Result<()> {
        match fs::remove_file(&temp) {
            Ok(()) => (),
            Err(e) if e.kind() == io::ErrorKind::NotFound => (),
            Err(e) => return Err(e),
        }
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let mut file = options.open(&temp)?;
        serde_json::to_writer(&mut file, value)?;
        file.write_all(b"\n")?;
        file.sync_all()?;
        drop(file);
        fs::rename(temp, path)?;
        sync_dir(parent)
    })();
    written.map_err(|e| e.to_string())
}

pub(crate) fn read_json<T: DeserializeOwned>(path: &Path) -> Result<Option<T>> {
    match fs::symlink_metadata(path) {
        Ok(m) if m.is_file() => (),
        Ok(_) => return Err("unsafe maintenance state file".into()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.to_string()),
    };
    let file = File::open(path).map_err(|e| e.to_string())?;
    serde_json::from_reader(file)
        .map(Some)
        .map_err(|e| e.to_string())
}

pub(crate) fn identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

pub(crate) fn state_dir(parent: &Path, name: &str) -> Result<PathBuf> {
    let path = parent.join(name);
    match fs::create_dir(&path) {
        Ok(()) => sync_dir(parent).map_err(|e| e.to_string())?,
        Err(e) if e.kind() == io::ErrorKind::AlreadyExists => (),
        Err(e) => return Err(e.to_string()),
    }
    if !fs::symlink_metadata(&path).is_ok_and(|m| m.is_dir()) {
        return Err("unsafe maintenance state directory".into());
    }
    Ok(path)
}

fn load(path: &Path) -> Result<Option<Batch>> {
    let state = read_json::<Batch>(path)?;
    if state.as_ref().is_some_and(|s| s.version != 1) {
        return Err("unsupported rebuild journal version".into());
    }
    Ok(state)
}

fn plan_valid(plan: &Plan) -> bool {
    let mut ids = HashSet::new();
    !plan.scope.trim().is_empty()
        && plan.scope.len() <= 256
        && !plan.route.trim().is_empty()
        && plan.route.len() <= 128
        && plan.sources.len() <= 64
        && plan.sources.iter().any(|s| s.role == Role::Primary)
        && plan
            .sources
            .iter()
            .all(|s| s.event > 0 && ids.insert(s.event))
}

fn preview(
    path: &Path,
    batch: &str,
    state: &mut Batch,
    mut call: impl FnMut(&str, Value) -> Result<Value>,
) -> Result<Value> {
    if let Phase::Review {
        preview, sources, ..
    } = &state.phase
    {
        let current = call(
            "maintenance.extract.preview",
            preview_args(&state.plan, batch, sources),
        )?;
        if current["preview"] != *preview || current["original"] != true {
            return Err("original preview replay mismatch".into());
        }
        return status(state);
    }
    if matches!(state.phase, Phase::Selecting) {
        let mut sources = Vec::with_capacity(state.plan.sources.len());
        for selected in &state.plan.sources {
            let page = call(
                "maintenance.history.page",
                json!({
                    "scope":state.plan.scope,"purpose":"rebuild","event":selected.event
                }),
            )?;
            let item = page["items"]
                .as_array()
                .and_then(|items| {
                    if let [item] = items.as_slice() {
                        Some(item)
                    } else {
                        None
                    }
                })
                .filter(|item| item["event"] == selected.event)
                .ok_or("original source page mismatch")?;
            let version = item["version"]
                .as_str()
                .filter(|s| !s.is_empty())
                .ok_or("original source version missing")?;
            sources.push(Source {
                event: selected.event,
                role: selected.role,
                version: version.to_owned(),
            });
        }
        state.phase = Phase::Prepared { sources };
        write_json(path, state)?;
    }
    let Phase::Prepared { sources } = &state.phase else {
        return status(state);
    };
    let preview = call(
        "maintenance.extract.preview",
        preview_args(&state.plan, batch, sources),
    )?;
    let id = preview["preview"]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or("no reviewed preview; keep the original request key")?;
    let count = preview["action_count"]
        .as_u64()
        .filter(|n| *n <= 128)
        .ok_or("invalid original action count")?;
    let content = preview["content"].clone();
    let Phase::Prepared { sources } = std::mem::replace(&mut state.phase, Phase::Selecting) else {
        unreachable!("preview requires a prepared source selection")
    };
    state.phase = Phase::Review {
        preview: id.to_owned(),
        count,
        content,
        sources,
        approvals: BTreeMap::new(),
        pending: None,
    };
    write_json(path, state)?;
    status(state)
}

fn preview_args(plan: &Plan, batch: &str, sources: &[Source]) -> Value {
    json!({
        "scope":plan.scope,"purpose":"rebuild","key":batch,"format":"extraction",
        "route":plan.route,"mode":plan.mode,"sources":sources
    })
}

fn apply(
    state_path: &Path,
    state: &mut Batch,
    id: &str,
    approval: Approval,
    mut call: impl FnMut(&str, Value) -> Result<Value>,
) -> Result<Value> {
    let Approval {
        operation,
        ordinals: approved,
    } = approval;
    let Phase::Review {
        preview,
        count,
        approvals,
        pending,
        ..
    } = &mut state.phase
    else {
        return Err("no original preview available for approval".into());
    };
    let distinct: HashSet<_> = approved.iter().collect();
    if id != preview.as_str()
        || !identifier(&operation)
        || approved.len() > 128
        || approved.len() != distinct.len()
        || approved.iter().any(|n| n >= count)
    {
        return Err("invalid preview, operation or approved ordinals".into());
    }
    if pending.as_ref().is_some_and(|p| p != &operation) {
        return Err("resolve the original pending apply operation first".into());
    }
    let original_subset = approvals
        .entry(operation.clone())
        .or_insert_with(|| approved.clone());
    if original_subset != &approved {
        return Err("original approved subset changed".into());
    }
    *pending = Some(operation.clone());
    write_json(state_path, state)?;
    let original = format!("{id}/{operation}");
    let receipt = call(
        "maintenance.extract.apply",
        json!({
            "scope":state.plan.scope,"purpose":"rebuild","preview":id,
            "operation":original,"approved":approved
        }),
    )?;
    let ordinals = receipt["applied"].as_array().and_then(|items| {
        items
            .iter()
            .map(|item| item["ordinal"].as_u64())
            .collect::<Option<Vec<_>>>()
    });
    let mut expected = approved;
    expected.sort_unstable();
    if receipt["preview"] != id
        || receipt["operation"] != original
        || ordinals.as_ref() != Some(&expected)
    {
        return Err("original apply receipt mismatch".into());
    }
    let Phase::Review { pending, .. } = &mut state.phase else {
        unreachable!("apply requires a reviewed preview")
    };
    *pending = None;
    write_json(state_path, state)?;
    Ok(receipt)
}

fn status(state: &Batch) -> Result<Value> {
    let mut report = match &state.phase {
        Phase::Selecting => json!({"phase":"selecting"}),
        Phase::Prepared { .. } => json!({"phase":"prepared"}),
        Phase::Review {
            preview,
            count,
            content,
            approvals,
            pending,
            ..
        } => {
            let pending = match pending {
                Some(operation) => {
                    let ordinals = approvals
                        .get(operation)
                        .ok_or("pending approval missing from journal")?;
                    Some(json!({"operation":operation,"ordinals":ordinals}))
                }
                None => None,
            };
            let applied: BTreeSet<_> = approvals
                .iter()
                .filter(|(operation, _)| {
                    pending
                        .as_ref()
                        .is_none_or(|p| p["operation"] != **operation)
                })
                .flat_map(|(_, ordinals)| ordinals.iter().copied())
                .collect();
            json!({"phase":"review","preview":preview,"action_count":count,"content":content,
                   "applied_ordinals":applied,"pending":pending})
        }
        Phase::Forgotten => return Err("original rebuild sources forgotten".into()),
    };
    report["execution"] = json!(state.execution);
    Ok(report)
}

pub fn run(
    root: &Path,
    name: &str,
    job: Value,
    mut call: impl FnMut(&str, Value) -> Result<Value>,
) -> Result<Value> {
    let job: Job = serde_json::from_value(job).map_err(|e| e.to_string())?;
    let batch = job.batch().to_owned();
    if !identifier(&batch) {
        return Err("invalid original batch identifier".into());
    }
    let directory = state_dir(root, &format!("batch-{batch}"))?;
    let path = directory.join("state.json");
    let mut state = match (load(&path)?, &job) {
        (Some(state), _) if matches!(state.phase, Phase::Forgotten) => return status(&state),
        (Some(state), Job::Preview { plan, .. }) if &state.plan != plan => {
            return Err("original batch plan changed".into());
        }
        (Some(state), _) => state,
        (None, Job::Preview { plan, .. }) if plan_valid(plan) => Batch {
            version: 1,
            plan: plan.clone(),
            jobs: BTreeSet::new(),
            execution: Execution::Active,
            phase: Phase::Selecting,
        },
        (None, Job::Preview { .. }) => return Err("invalid original source selection".into()),
        (None, _) => return Err("original batch does not exist".into()),
    };
    if state.jobs.insert(name.to_owned()) {
        write_json(&path, &state)?;
    }
    if let Some(execution) = match &job {
        Job::Pause { .. } if matches!(state.execution, Execution::Active) => {
            Some(Execution::Paused)
        }
        Job::Resume { .. } if matches!(state.execution, Execution::Paused) => {
            Some(Execution::Active)
        }
        Job::Cancel { .. } => Some(Execution::Cancelled),
        _ => None,
    } {
        state.execution = execution;
        write_json(&path, &state)?;
        return status(&state);
    }
    match job {
        Job::Preview { .. } if matches!(state.execution, Execution::Active) => {
            preview(&path, &batch, &mut state, call)
        }
        Job::Apply {
            preview,
            operation,
            approved,
            ..
        } if matches!(state.execution, Execution::Active) => apply(
            &path,
            &mut state,
            &preview,
            Approval {
                operation,
                ordinals: approved,
            },
            call,
        ),
        Job::Preview { .. } | Job::Apply { .. } => {
            Err("original rebuild is paused or cancelled".into())
        }
        Job::Status { .. } | Job::Pause { .. } | Job::Resume { .. } | Job::Cancel { .. } => {
            status(&state)
        }
        Job::Read { offset, .. } => {
            let Phase::Review {
                preview, content, ..
            } = &state.phase
            else {
                return Err("no original preview available for review".into());
            };
            call(
                "maintenance.content",
                json!({
                    "scope":state.plan.scope,"purpose":"rebuild","kind":"preview","id":preview,
                    "sha256":content["sha256"],"offset":offset
                }),
            )
        }
    }
}

pub fn erase(root: &Path, sources: &Value) -> Result<()> {
    let sources: Vec<u64> = serde_json::from_value(sources.clone()).map_err(|e| e.to_string())?;
    let mut forgotten = HashSet::new();
    let mut incomplete = false;
    for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
        let Ok(entry) = entry else {
            incomplete = true;
            continue;
        };
        if !entry
            .file_name()
            .to_str()
            .and_then(|name| name.strip_prefix("batch-"))
            .is_some_and(identifier)
        {
            continue;
        }
        if !entry.file_type().is_ok_and(|kind| kind.is_dir()) {
            incomplete = true;
            continue;
        }
        let directory = entry.path();
        let path = directory.join("state.json");
        let Ok(state) = load(&path) else {
            incomplete = true;
            continue;
        };
        let Some(mut state) = state else {
            incomplete |= remove(&directory.join("state.json.tmp")).is_err();
            incomplete |= sync_dir(&directory).is_err();
            continue;
        };
        if !matches!(state.phase, Phase::Forgotten)
            && !state
                .plan
                .sources
                .iter()
                .any(|source| sources.contains(&source.event))
        {
            continue;
        }
        state.phase = Phase::Forgotten;
        state.plan.sources.clear();
        forgotten.insert(entry.file_name());
        incomplete |= write_json(&path, &state).is_err();
        for job in &state.jobs {
            if !crate::job_name(job) {
                incomplete = true;
                continue;
            }
            incomplete |= !remove_results(&root.join(format!("{job}.job")));
        }
    }
    for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
        let Ok(entry) = entry else {
            incomplete = true;
            continue;
        };
        let path = entry.path();
        if !crate::safe_job(&path) {
            continue;
        }
        let Ok(job) = read_json::<Job>(&path) else {
            incomplete = true;
            continue;
        };
        let Some(job) = job else {
            continue;
        };
        if forgotten.contains(std::ffi::OsStr::new(&format!("batch-{}", job.batch())))
            || job
                .selected_sources()
                .iter()
                .any(|s| sources.contains(&s.event))
        {
            incomplete |= !remove_results(&path);
        }
    }
    incomplete |= sync_dir(root).is_err();
    if incomplete {
        return Err("unresolved rebuild files require operator review".into());
    }
    Ok(())
}

pub(crate) fn remove_results(job: &Path) -> bool {
    let result = remove(&job.with_extension("result"));
    let transient = remove(&job.with_extension("result.tmp"));
    // Keep the input as a retry anchor until both output paths are clear.
    result.is_ok() && transient.is_ok() && remove(job).is_ok()
}

pub(crate) fn remove(path: &Path) -> Result<()> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
