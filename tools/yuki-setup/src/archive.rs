use crate::Error;
use sha2::{Digest, Sha256};
use ssh_key::{Algorithm, PublicKey, SshSig};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{self, Cursor, Read},
    path::Path,
};
use zip::ZipArchive;

pub(crate) const MAX_ARCHIVE: u64 = 128 * 1024 * 1024;
pub(crate) const MAX_MEMBER: u64 = 64 * 1024 * 1024;

pub(crate) fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(crate) fn valid_digest(digest: &str) -> bool {
    digest.len() == 64
        && digest
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub(crate) fn checked_input(path: &Path, expected: &str) -> Result<Vec<u8>, Error> {
    let file = File::open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() > MAX_ARCHIVE {
        return Err("expected a bounded regular package".into());
    }
    let mut bytes = Vec::new();
    file.take(MAX_ARCHIVE + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_ARCHIVE || sha256(&bytes) != expected {
        return Err("package SHA-256 differs from pin".into());
    }
    Ok(bytes)
}

pub(crate) fn signature(
    raw: &[u8],
    signed: &[u8],
    key: &str,
    namespace: &str,
) -> Result<(), Error> {
    let key = PublicKey::from_openssh(key.trim())?;
    let signed = SshSig::from_pem(signed)?;
    if key.algorithm() != Algorithm::Ed25519 || signed.algorithm() != Algorithm::Ed25519 {
        return Err("expected pinned Ed25519 SSH signature".into());
    }
    key.verify(namespace, raw, &signed)?;
    Ok(())
}

fn portable_member(name: &str) -> bool {
    name.is_ascii()
        && name.split('/').all(|part| {
            if part.is_empty()
                || part.ends_with(['.', ' '])
                || part
                    .bytes()
                    .any(|b| b.is_ascii_control() || b"\\:<>\"|?*".contains(&b))
            {
                return false;
            }
            let stem = part
                .split('.')
                .next()
                .unwrap_or_default()
                .to_ascii_uppercase();
            !matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
                && !(stem.len() == 4
                    && (stem.starts_with("COM") || stem.starts_with("LPT"))
                    && stem.as_bytes()[3].is_ascii_digit())
        })
}

struct Member {
    mode: Option<u32>,
    size: u64,
}

pub(crate) struct Package<'a> {
    zip: ZipArchive<Cursor<&'a [u8]>>,
    entries: BTreeMap<String, Member>,
}

impl<'a> Package<'a> {
    pub(crate) fn read(raw: &'a [u8], signed_files: bool) -> Result<Self, Error> {
        let mut zip = ZipArchive::new(Cursor::new(raw))?;
        if zip.has_duplicate_names() || zip.len() > 2048 {
            return Err("invalid package inventory".into());
        }
        let mut entries = BTreeMap::new();
        let mut folded = BTreeSet::new();
        let mut size = 0u64;
        for index in 0..zip.len() {
            let file = zip.by_index(index)?;
            let name = file.name()?.into_owned();
            let mode = file.unix_mode();
            let kind = mode.unwrap_or_default() & 0o170000;
            if !portable_member(&name)
                || !folded.insert(name.to_ascii_lowercase())
                || !file.is_file()
                || file.encrypted()
                || file.size() > MAX_MEMBER
                || (kind != 0o100000 && (signed_files || kind != 0))
            {
                return Err("unsafe archive member".into());
            }
            size += file.size();
            if size > MAX_ARCHIVE {
                return Err("archive members exceed size limit".into());
            }
            entries.insert(
                name,
                Member {
                    mode,
                    size: file.size(),
                },
            );
        }
        Ok(Self { zip, entries })
    }

    pub(crate) fn inventory<'b>(
        &self,
        expected: impl IntoIterator<Item = &'b str>,
    ) -> Result<(), Error> {
        if self
            .entries
            .keys()
            .map(String::as_str)
            .collect::<BTreeSet<_>>()
            != expected.into_iter().collect()
        {
            return Err("signed archive inventory mismatch".into());
        }
        Ok(())
    }

    pub(crate) fn member(&mut self, name: &str) -> Result<Vec<u8>, Error> {
        let size = self.entries.get(name).ok_or("missing archive member")?.size;
        let mut raw = Vec::new();
        self.zip
            .by_name(name)?
            .take(size + 1)
            .read_to_end(&mut raw)?;
        if raw.len() as u64 != size {
            return Err("archive member length mismatch".into());
        }
        Ok(raw)
    }

    pub(crate) fn checked_member(
        &mut self,
        name: &str,
        expected: &str,
        size: Option<u64>,
    ) -> Result<Vec<u8>, Error> {
        let raw = self.member(name)?;
        if size.is_some_and(|len| len != raw.len() as u64) || sha256(&raw) != expected {
            return Err(format!("changed member: {name}").into());
        }
        Ok(raw)
    }

    pub(crate) fn extract(
        &mut self,
        root: &Path,
        executable: &str,
        preserve_execute: bool,
    ) -> Result<(), Error> {
        let names: Vec<_> = self.entries.keys().cloned().collect();
        for name in names {
            let path = root.join(&name);
            fs::create_dir_all(path.parent().ok_or("missing member parent")?)?;
            let mut file = self.zip.by_name(&name)?;
            let mut output = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)?;
            let member = &self.entries[&name];
            if io::copy(&mut file.by_ref().take(member.size + 1), &mut output)? != member.size {
                return Err("archive member length mismatch".into());
            }
            if name == executable
                || (preserve_execute && member.mode.unwrap_or_default() & 0o111 != 0)
            {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    output.set_permissions(fs::Permissions::from_mode(0o755))?;
                }
            }
        }
        Ok(())
    }
}
