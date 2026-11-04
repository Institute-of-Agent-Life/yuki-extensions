use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::Path,
    process,
};

pub const SOUL: &str = "# SOUL example\n\nThe operator owns the character's description. Review this sample before editing the owner's SOUL.md.\n";

pub fn compose(digest: &str, platform: &str) -> String {
    format!(
        r#"# Generated from a verified offline CORE-039 candidate.
services:
  core:
    image: yuki-core@{digest}
    platform: {platform}
    pull_policy: never
    user: '65532:65532'
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    environment:
      TZ: ${{YUKI_TIMEZONE:-UTC}}
    volumes:
      - ./data:/data
    entrypoint: ['/bin/sh', '-ec']
    command:
      - |
        if [ ! -f /data/owner/yuki.toml ]; then yuki-core --data /data/owner init; fi
        exec yuki-core --data /data/owner run
    healthcheck:
      test: ['CMD', 'yuki-core', '--data', '/data/owner', 'operator', 'database-info']
      interval: 10s
      timeout: 3s
      retries: 5
"#
    )
}

pub fn pinned_compose(existing: &str, generated: &str) -> bool {
    fn directives(s: &str) -> Vec<&str> {
        s.lines()
            .filter_map(|line| {
                let body = line.split_once(" #").map_or(line, |(v, _)| v).trim_end();
                if body.is_empty() || body.trim_start().starts_with('#') {
                    None
                } else {
                    Some(body)
                }
            })
            .collect()
    }
    directives(existing) == directives(generated)
}

pub fn read_zone(input: &str) -> Result<Option<&str>, &'static str> {
    let mut value = None;
    for line in input.lines() {
        let line = line
            .trim_start()
            .strip_prefix("export ")
            .unwrap_or(line.trim_start());
        if let Some((key, raw)) = line.split_once('=') {
            if key.trim() == "YUKI_TIMEZONE" {
                if value.is_some() {
                    return Err("duplicate YUKI_TIMEZONE in .env");
                }
                let raw = raw.split('#').next().unwrap_or("").trim();
                let unquoted = raw
                    .strip_prefix('"')
                    .and_then(|v| v.strip_suffix('"'))
                    .or_else(|| raw.strip_prefix("'").and_then(|v| v.strip_suffix("'")))
                    .unwrap_or(raw);
                value = Some(unquoted);
            }
        }
    }
    Ok(value)
}

// Only our own keys are edited. Unknown assignments and comments remain byte-for-byte.
pub fn dotenv(input: &str, timezone: &str) -> Result<String, &'static str> {
    const KEY: &str = "YUKI_TIMEZONE";
    let mut found = false;
    let mut result = String::new();
    let newline = if input.contains("\r\n") { "\r\n" } else { "\n" };
    for line in input.split_inclusive('\n') {
        let stripped = line.trim_start();
        let assignment = stripped.strip_prefix("export ").unwrap_or(stripped);
        if assignment
            .split_once('=')
            .is_some_and(|(k, _)| k.trim() == KEY)
        {
            if found {
                return Err("duplicate YUKI_TIMEZONE in .env");
            }
            found = true;
            let equal = line.find('=').unwrap();
            let after = &line[equal + 1..];
            let value = after.trim_start();
            let end = value.trim_end_matches(['\r', '\n']);
            // Managed timezone values are plain or quoted. Keep the original inline comment.
            let suffix = end
                .find('#')
                .map(|pos| &end[end[..pos].trim_end().len()..])
                .unwrap_or("");
            result.push_str(&line[..=equal]);
            result.push_str(&after[..after.len() - value.len()]);
            result.push_str(timezone);
            result.push_str(suffix);
            result.push_str(&line[line.trim_end_matches(['\r', '\n']).len()..]);
        } else {
            result.push_str(line);
        }
    }
    if !found {
        if !result.is_empty() && !result.ends_with('\n') {
            result.push_str(newline);
        }
        result.push_str(&format!("{KEY}={timezone}{newline}"));
    }
    Ok(result)
}

pub fn read_optional(path: &Path) -> io::Result<Option<String>> {
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_file() => fs::read_to_string(path).map(Some),
        Ok(_) => Err(io::Error::other("managed path is not a regular file")),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e),
    }
}

pub fn create(path: &Path, content: &str) -> io::Result<()> {
    let mut f = OpenOptions::new().write(true).create_new(true).open(path)?;
    f.write_all(content.as_bytes())?;
    f.sync_all()
}

pub fn update_env(dir: &Path, previous: Option<&str>, content: &str) -> io::Result<()> {
    if previous == Some(content) {
        return Ok(());
    }
    let dest = dir.join(".env");
    let temp = dir.join(format!(".yuki-env-{}.tmp", process::id()));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temp)?;
    let result = (|| {
        if previous.is_some() {
            file.set_permissions(fs::metadata(&dest)?.permissions())?;
        }
        file.write_all(content.as_bytes())?;
        file.sync_all()?;
        drop(file);
        if read_optional(&dest)?.as_deref() != previous {
            return Err(io::Error::other(".env changed during generation"));
        }
        fs::rename(&temp, &dest)
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp);
    }
    result
}

pub fn lock(dir: &Path) -> io::Result<File> {
    let path = dir.join(".yuki-setup.lock");
    if fs::symlink_metadata(&path).is_ok_and(|m| !m.file_type().is_file()) {
        return Err(io::Error::other("unsafe setup lock"));
    }
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    file.try_lock()
        .map_err(|_| io::Error::other("setup is already running"))?;
    Ok(file)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updating_a_managed_value_preserves_other_assignments_and_comments() {
        let input = "VENDOR_TOKEN=${OWNER_SECRET}\r\n export YUKI_TIMEZONE='UTC'  # manual\r\n";
        let expected =
            "VENDOR_TOKEN=${OWNER_SECRET}\r\n export YUKI_TIMEZONE=Asia/Shanghai  # manual\r\n";
        assert_eq!(dotenv(input, "Asia/Shanghai").unwrap(), expected);
        assert_eq!(read_zone(expected).unwrap(), Some("Asia/Shanghai"));
        assert!(dotenv("YUKI_TIMEZONE=A\nexport YUKI_TIMEZONE=B\n", "UTC").is_err());
    }

    #[test]
    fn manual_comments_are_preserved_and_changed_image_is_refused() {
        let original = compose("sha256:example", "linux/arm64");
        assert!(pinned_compose(
            &format!("# local note\n{original}"),
            &original
        ));
        assert!(!pinned_compose(
            &original.replace("sha256:example", "latest"),
            &original
        ));
    }
}
