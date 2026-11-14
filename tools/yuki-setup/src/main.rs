mod archive;
mod config;
mod install;
mod oci;
use std::{
    collections::HashMap,
    env, fs,
    path::{Path, PathBuf},
};
type Error = Box<dyn std::error::Error>;

fn timezone_valid(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 96
        && value.split('/').all(|seg| {
            !seg.is_empty()
                && seg != "."
                && seg != ".."
                && seg
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"_+-".contains(&b))
        })
}

fn run() -> Result<(), Error> {
    let mut cli = env::args().skip(1);
    let cmd = cli
        .next()
        .ok_or("use init or doctor with --archive FILE --dir DIRECTORY")?;
    if !["init", "doctor", "native"].contains(&cmd.as_str()) {
        return Err("use init, doctor or native".into());
    }
    let mut args = HashMap::new();
    while let Some(k) = cli.next() {
        if ![
            "--archive",
            "--dir",
            "--core",
            "--timezone",
            "--profile",
            "--entry",
            "--entry-network",
            "--plugin",
            "--plugin-file",
        ]
        .contains(&k.as_str())
        {
            return Err("unknown setup option".into());
        }
        let value = cli.next().ok_or("missing option value")?;
        if args.insert(k, value).is_some() {
            return Err("duplicate option".into());
        }
    }
    let dir = PathBuf::from(args.get("--dir").ok_or("missing --dir")?);
    if cmd == "native" {
        let selected = args.get("--plugin").map(String::as_str);
        let plugin_file = args.get("--plugin-file");
        let optional = selected == Some("web-fetch") && plugin_file.is_some();
        if let Some(version) = args.get("--core") {
            let archive = args.get("--archive").ok_or("missing --archive")?;
            if args.keys().any(|k| {
                !["--core", "--dir", "--archive", "--plugin", "--plugin-file"].contains(&k.as_str())
            }) {
                return Err("unknown option for native base installation".into());
            }
            let result = if version == "1.0.0" {
                if selected.is_some() != optional || plugin_file.is_some() != optional {
                    return Err(
                        "native --core 1.0.0 requires a pinned web-fetch package when selected"
                            .into(),
                    );
                }
                install::base(Path::new(archive), &dir, plugin_file.map(Path::new))
            } else {
                if selected.is_some() || plugin_file.is_some() {
                    return Err("optional plugin needs a compatible native setup package".into());
                }
                install::published_base(version, Path::new(archive), &dir)
            }
            .map_err(|err| {
                eprintln!("{err}");
                "native base input refused"
            })?;
            println!("{}", serde_json::to_string(&result)?);
            return Ok(());
        }
        if selected.is_some() != optional
            || plugin_file.is_some() != optional
            || args
                .keys()
                .any(|k| !["--dir", "--archive", "--plugin", "--plugin-file"].contains(&k.as_str()))
        {
            return Err("native takes --archive and --dir; a selected Windows web-fetch also requires --plugin-file".into());
        }
        let archive = Path::new(args.get("--archive").ok_or("missing --archive")?);
        let result =
            install::candidate(archive, &dir, plugin_file.map(Path::new)).map_err(|err| {
                eprintln!("{err}");
                "native input refused"
            })?;
        println!("{result}");
        return Ok(());
    }
    let core = oci::verify(Path::new(args.get("--archive").ok_or("missing --archive")?)).map_err(
        |err| {
            eprintln!("CORE-039 verification failed: {err}");
            "offline input refused"
        },
    )?;
    if args.get("--core").is_some_and(|v| v != &core.version) {
        return Err("selected core version does not match the verified input".into());
    }
    if args.contains_key("--plugin-file")
        || args.contains_key("--plugin")
        || args.get("--profile").is_some_and(|v| v != "direct")
    {
        return Err("selected component has no compatible pinned package in this candidate".into());
    }
    let entry = config::Entry::parse(
        args.get("--entry").map(String::as_str),
        args.get("--entry-network").map(String::as_str),
    )?;
    let zone = args.get("--timezone").map(String::as_str);
    if zone.is_some_and(|v| !timezone_valid(v)) {
        return Err("invalid timezone".into());
    }
    if cmd == "init" {
        fs::create_dir_all(&dir)?;
    }
    if !fs::symlink_metadata(&dir)?.is_dir() {
        return Err("unsafe setup destination".into());
    }
    let _guard = if cmd == "init" {
        Some(config::lock(&dir)?)
    } else {
        None
    };
    let existing = config::read_optional(&dir.join("compose.yaml"))?;
    let environment = config::read_optional(&dir.join(".env"))?;
    let soul = config::read_optional(&dir.join("SOUL.example.md"))?;
    let project = match existing.as_deref() {
        Some(contents) => config::read_project(contents)?.map(str::to_owned),
        None if cmd == "init" => Some(config::new_project()?),
        None => return Err("incomplete offline kit".into()),
    };
    let compose = config::compose(&core.image, &core.platform, &entry, project.as_deref());
    let legacy = matches!(entry, config::Entry::Local)
        && existing.as_deref().is_some_and(|v| {
            config::pinned_compose(v, &config::legacy_compose(&core.image, &core.platform))
        });
    if !legacy
        && existing
            .as_deref()
            .is_some_and(|v| !config::pinned_compose(v, &compose))
    {
        return Err("compose.yaml differs from the pinned offline kit; preserve it and use a separate directory".into());
    }
    if cmd == "init" {
        let text = environment.as_deref().unwrap_or("");
        let old_zone = config::read_zone(text)?;
        let value = zone.or(old_zone).unwrap_or("UTC");
        if !timezone_valid(value) {
            return Err("invalid existing timezone".into());
        }
        let changed = if zone.is_some() || old_zone.is_none() {
            config::dotenv(text, value)?
        } else {
            text.to_owned()
        };
        if existing.is_none() {
            config::create(&dir.join("compose.yaml"), &compose)?;
        }
        if soul.is_none() {
            config::create(&dir.join("SOUL.example.md"), config::SOUL)?;
        }
        config::update_env(&dir, environment.as_deref(), &changed)?;
    } else if existing.is_none() || soul.is_none() || environment.is_none() {
        return Err("incomplete offline kit".into());
    }
    let env_text = config::read_optional(&dir.join(".env"))?.ok_or("missing .env")?;
    let observed = config::read_zone(&env_text)?.ok_or("missing timezone")?;
    if !timezone_valid(observed) || zone.is_some_and(|v| v != observed) {
        return Err("offline timezone differs".into());
    }
    println!(
        "offline doctor passed; candidate={} platform={} image={} profile=direct entry={} storage={} project={}",
        core.version,
        core.platform,
        core.image,
        entry.name(),
        if legacy { "legacy-bind" } else { "volume" },
        project.as_deref().unwrap_or("compose-default"),
    );
    Ok(())
}
fn main() {
    if let Err(err) = run() {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
