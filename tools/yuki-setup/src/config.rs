use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::Path,
    process::{self, Command},
};

pub const SOUL: &str = "# SOUL example\n\nThe operator owns the character's description. Review this sample before editing the owner's SOUL.md.\n";

pub enum Entry<'a> {
    Local,
    External(&'a str),
}

impl<'a> Entry<'a> {
    pub fn parse(mode: Option<&str>, network: Option<&'a str>) -> Result<Self, &'static str> {
        match (mode.unwrap_or("local"), network) {
            ("local", None) => Ok(Self::Local),
            ("external", Some(name))
                if name.len() <= 128
                    && name
                        .as_bytes()
                        .first()
                        .is_some_and(u8::is_ascii_alphanumeric)
                    && name
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b)) =>
            {
                Ok(Self::External(name))
            }
            ("external", _) => Err("external entry requires a valid --entry-network name"),
            _ => Err("use --entry local or --entry external --entry-network NAME"),
        }
    }

    pub fn name(&self) -> &'static str {
        match self {
            Self::Local => "local",
            Self::External(_) => "external",
        }
    }
}

pub fn new_project(python: &mut Command) -> io::Result<String> {
    let output = python
        .args([
            "-I",
            "-c",
            "import secrets; print('yuki-' + secrets.token_hex(16))",
        ])
        .output()?;
    let name = std::str::from_utf8(&output.stdout).unwrap_or("").trim_end();
    if !output.status.success() || !valid_project(name) {
        return Err(io::Error::other(
            "could not generate a Compose project name",
        ));
    }
    Ok(name.to_owned())
}

fn valid_project(name: &str) -> bool {
    name.strip_prefix("yuki-").is_some_and(|id| {
        id.len() == 32
            && id
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    })
}

pub fn read_project(compose: &str) -> Result<Option<&str>, &'static str> {
    let mut names = compose
        .lines()
        .filter_map(|line| line.strip_prefix("name: "));
    let Some(name) = names.next() else {
        return Ok(None);
    };
    let name = name
        .split_once(" #")
        .map_or(name, |(value, _)| value)
        .trim_end();
    if names.next().is_some() || !valid_project(name) {
        return Err("invalid Compose project name");
    }
    Ok(Some(name))
}

pub fn compose(digest: &str, platform: &str, entry: &Entry<'_>, project: Option<&str>) -> String {
    let project_line = project
        .map(|name| format!("name: {name}\n"))
        .unwrap_or_default();
    let (listen, service_network, networks) = match entry {
        Entry::Local => ("127.0.0.1", "    network_mode: none\n", String::new()),
        Entry::External(name) => (
            "0.0.0.0",
            "    networks:\n      ingress:\n        aliases:\n          - \"${COMPOSE_PROJECT_NAME}-core\"\n",
            format!("networks:\n  ingress:\n    name: '{name}'\n    external: true\n"),
        ),
    };
    format!(
        r#"# Generated from a verified offline CORE-039 candidate.
{project_line}services:
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
{service_network}    volumes:
      - owner:/var/tmp
    entrypoint: ['/bin/sh', '-ec']
    command:
      - |
        if [ ! -e /var/tmp/yuki ]; then
          stage=$$(mktemp -d /var/tmp/.yuki-init.XXXXXXXX)
          trap 'rm -rf -- "$$stage"' EXIT
          yuki-core --data "$$stage" init
          sed -i 's/^listen = "127\.0\.0\.1:0"$$/listen = "{listen}:8080"/' "$$stage/yuki.toml"
          mv -T --no-clobber "$$stage" /var/tmp/yuki
          rm -rf -- "$$stage"
          trap - EXIT
        fi
        exec yuki-core --data /var/tmp/yuki run
    healthcheck:
      test:
        - CMD
        - /bin/bash
        - -ec
        - |
          exec 3<>/dev/tcp/127.0.0.1/8080
          printf 'GET /readyz HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
          read -r status <&3
          [[ "$$status" == 'HTTP/1.1 200 '* ]]
      interval: 2s
      timeout: 3s
      retries: 10
volumes:
  owner:
{networks}"#
    )
}

pub fn legacy_compose(digest: &str, platform: &str) -> String {
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
        let mut block = None;
        s.lines()
            .filter_map(|line| {
                let text = line.trim_start_matches(' ');
                let indent = line.len() - text.len();
                if text.is_empty() {
                    return None;
                }
                if let Some(parent) = block {
                    if indent > parent {
                        return Some(line);
                    }
                    block = None;
                }
                if text.starts_with('#') {
                    return None;
                }
                let body = line.split_once(" #").map_or(line, |(v, _)| v).trim_end();
                if body.trim_start() == "- |" {
                    block = Some(indent);
                }
                Some(body)
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
            let text = line.trim_end_matches(['\r', '\n']);
            let after = &text[equal + 1..];
            let value = after.trim_start();
            // Managed timezone values are plain or quoted. Keep the original inline comment.
            let suffix = value
                .find('#')
                .map(|pos| &value[value[..pos].trim_end().len()..])
                .unwrap_or("");
            result.push_str(&line[..=equal]);
            result.push_str(&after[..after.len() - value.len()]);
            result.push_str(timezone);
            if suffix.starts_with('#') {
                result.push(' ');
            }
            result.push_str(suffix);
            result.push_str(&line[text.len()..]);
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
        assert_eq!(
            dotenv("YUKI_TIMEZONE= \r\nOTHER=kept\r\n", "UTC").unwrap(),
            "YUKI_TIMEZONE= UTC\r\nOTHER=kept\r\n"
        );
        assert!(dotenv("YUKI_TIMEZONE=A\nexport YUKI_TIMEZONE=B\n", "UTC").is_err());
    }

    #[test]
    fn manual_comments_are_preserved_and_changed_image_is_refused() {
        let original = compose("sha256:example", "linux/arm64", &Entry::Local, None);
        assert!(pinned_compose(
            &format!("# local note\n{original}"),
            &original
        ));
        assert!(!pinned_compose(
            &original.replace("sha256:example", "latest"),
            &original
        ));
        assert!(!pinned_compose(
            &original.replace(" >&3", " >&3 # script bytes"),
            &original
        ));
    }

    #[test]
    fn external_entry_requires_an_explicit_compose_network() {
        assert!(Entry::parse(Some("external"), None).is_err());
        assert!(Entry::parse(None, Some("gateway")).is_err());
        assert!(Entry::parse(Some("external"), Some("bad'\nnet")).is_err());
        assert!(matches!(
            Entry::parse(Some("external"), Some("gateway-1")),
            Ok(Entry::External("gateway-1"))
        ));
    }

    #[test]
    fn compose_project_must_be_one_literal_generated_name() {
        let name = "yuki-0000000000000000000000000000000a";
        let yaml = format!("# local note\nname: {name} # keep\nservices:\n");
        assert_eq!(read_project(&yaml).unwrap(), Some(name));
        assert_eq!(read_project("services:\n").unwrap(), None);
        assert!(read_project("name: ${COMPOSE_PROJECT_NAME}\n").is_err());
        assert!(read_project(&format!("name: {name}\nname: {name}\n")).is_err());
    }
}
