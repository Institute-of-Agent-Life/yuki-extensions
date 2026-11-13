mod config;
use std::{
    collections::HashMap,
    env, fs,
    path::{Path, PathBuf},
    process::Command,
};
type Error = Box<dyn std::error::Error>;

struct Core {
    version: String,
    image: String,
    platform: String,
}

fn python() -> Command {
    let mut python = Command::new(if cfg!(windows) { "py" } else { "python3" });
    if cfg!(windows) {
        python.arg("-3.12");
    }
    python
}

fn verify(archive: &Path) -> Result<Core, Error> {
    let out = python()
        .args([
            "-I",
            "-c",
            concat!(include_str!("keygen.py"), "\n", include_str!("verify.py")),
        ])
        .arg(archive)
        .args([
            include_str!("../inputs/source.lock.json"),
            include_str!("../inputs/oci-candidate.json"),
            include_str!("../inputs/oci-candidate.json.sig"),
            include_str!("../inputs/signer.pub"),
            include_str!("../inputs/verify_dist.py"),
            include_str!("../inputs/verify_oci.py"),
        ])
        .output()?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        eprintln!(
            "CORE-039 verification failed: {}",
            stderr.lines().last().unwrap_or("unknown error")
        );
        return Err("offline input refused".into());
    }
    let value = String::from_utf8(out.stdout)?;
    let mut lines = value.lines();
    let core = Core {
        version: lines.next().ok_or("missing version")?.to_owned(),
        image: lines.next().ok_or("missing image digest")?.to_owned(),
        platform: lines.next().ok_or("missing platform")?.to_owned(),
    };
    if lines.next().is_some() {
        return Err("invalid verified input".into());
    }
    Ok(core)
}

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
            if version != "1.0.0"
                || selected.is_some() != optional
                || plugin_file.is_some() != optional
            {
                return Err("native --core 1.0.0 accepts the base archive and optionally the frozen web-fetch package".into());
            }
            let archive = args.get("--archive").ok_or("missing --archive")?;
            if args.keys().any(|k| {
                !["--core", "--dir", "--archive", "--plugin", "--plugin-file"].contains(&k.as_str())
            }) {
                return Err("unknown option for native base installation".into());
            }
            let result = python()
                .args([
                    "-I",
                    "-c",
                    concat!(include_str!("keygen.py"), "\n", include_str!("stable.py")),
                ])
                .arg(archive)
                .arg(dir)
                .arg(include_str!("../inputs/base-1.0.json"))
                .arg(plugin_file.map(String::as_str).unwrap_or(""))
                .output()?;
            if !result.status.success() {
                eprintln!(
                    "{}",
                    String::from_utf8_lossy(&result.stderr)
                        .lines()
                        .last()
                        .unwrap_or("base verification failed")
                );
                return Err("native base input refused".into());
            }
            print!("{}", String::from_utf8(result.stdout)?);
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
        let output = python()
            .args([
                "-I",
                "-c",
                concat!(include_str!("keygen.py"), "\n", include_str!("native.py")),
            ])
            .arg(args.get("--archive").ok_or("missing --archive")?)
            .arg(dir)
            .args([
                include_str!("../inputs/native.lock.json"),
                include_str!("../inputs/verify_dist.py"),
                "b542c9bdd5535e944aeadd8442b3a4c766eab010a14ed3d9e665c5e1bffbf2db",
                include_str!("../inputs/web-fetch.lock.json"),
                plugin_file.map(String::as_str).unwrap_or(""),
            ])
            .output()?;
        if !output.status.success() {
            eprintln!(
                "{}",
                String::from_utf8_lossy(&output.stderr)
                    .lines()
                    .last()
                    .unwrap_or("native verifier failed")
            );
            return Err("native input refused".into());
        }
        print!("{}", String::from_utf8(output.stdout)?);
        return Ok(());
    }
    let core = verify(Path::new(args.get("--archive").ok_or("missing --archive")?))?;
    if args.get("--core").is_some_and(|v| v != &core.version) {
        return Err("selected core version does not match the verified input".into());
    }
    if args.get("--plugin-file").is_some()
        || args.get("--plugin").is_some()
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
        None if cmd == "init" => Some(config::new_project(&mut python())?),
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

#[cfg(test)]
mod public_base_tests {
    use super::python;

    #[test]
    fn commit_refuses_to_replace_even_an_empty_existing_destination() {
        let probe = r#"
from pathlib import Path
from tempfile import TemporaryDirectory
import runpy
commit = runpy.run_path("src/stable.py")["commit_directory"]
with TemporaryDirectory() as tmp:
    src, dst = (Path(tmp) / n for n in ["staged", "installed"])
    src.mkdir()
    (src / "checked").write_bytes(b"payload")
    dst.mkdir()
    try:
        commit(src, dst)
    except OSError:
        assert src.is_dir() and not list(dst.iterdir())
    else:
        raise AssertionError("existing directory replaced")
    dst.rmdir()
    commit(src, dst)
    assert not src.exists() and (dst / "checked").read_bytes() == b"payload"
"#;
        assert!(
            python()
                .args(["-I", "-c", probe])
                .status()
                .unwrap()
                .success()
        );
    }
}
