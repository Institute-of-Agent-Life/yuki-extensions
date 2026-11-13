use crate::{Error, archive};
use serde::Deserialize;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Cursor, Read},
    path::Path,
};

const LOCK: &[u8] = include_bytes!("../inputs/source.lock.json");
const MANIFEST: &[u8] = include_bytes!("../inputs/oci-candidate.json");
const SIGNATURE: &[u8] = include_bytes!("../inputs/oci-candidate.json.sig");
const KEY: &str = include_str!("../inputs/signer.pub");

#[derive(Deserialize)]
struct Lock {
    source_commit: String,
    core_version: String,
    image_digest: String,
    platform: String,
    archive_sha256: String,
    artifacts: BTreeMap<String, String>,
}

#[derive(Deserialize)]
struct Manifest {
    source_commit: String,
    platform: String,
    sha256: String,
    oci: Graph,
    dirty: bool,
    published: bool,
    nonroot_owner: bool,
    readyz: String,
}

#[derive(Deserialize, PartialEq)]
struct Graph {
    roots: Vec<String>,
    verified_blobs: usize,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Descriptor {
    digest: String,
    size: u64,
    #[serde(default)]
    media_type: String,
}

#[derive(Default, Deserialize)]
struct Document {
    #[serde(default)]
    manifests: Vec<Descriptor>,
    #[serde(default)]
    layers: Vec<Descriptor>,
    config: Option<Descriptor>,
}

pub(crate) struct Core {
    pub(crate) version: String,
    pub(crate) image: String,
    pub(crate) platform: String,
}

fn files(raw: &[u8]) -> Result<BTreeMap<String, Vec<u8>>, Error> {
    let mut tar = tar::Archive::new(Cursor::new(raw));
    let mut files = BTreeMap::new();
    let mut total = 0u64;
    for entry in tar.entries()? {
        let mut entry = entry?;
        let path = entry.path()?;
        let name = path
            .to_str()
            .ok_or("invalid OCI member name")?
            .trim_end_matches('/');
        if entry.header().entry_type().is_dir() && matches!(name, "blobs" | "blobs/sha256") {
            continue;
        }
        if !entry.header().entry_type().is_file()
            || entry.size() > archive::MAX_MEMBER
            || !matches!(name, "oci-layout" | "index.json" | "manifest.json")
                && !name
                    .strip_prefix("blobs/sha256/")
                    .is_some_and(archive::valid_digest)
        {
            return Err("unexpected OCI archive entry".into());
        }
        total += entry.size();
        if total > archive::MAX_ARCHIVE || files.len() >= 2048 {
            return Err("OCI archive exceeds size limit".into());
        }
        let mut data = Vec::new();
        let name = name.to_owned();
        entry.read_to_end(&mut data)?;
        if files.insert(name, data).is_some() {
            return Err("duplicate OCI entry".into());
        }
    }
    Ok(files)
}

fn graph(raw: &[u8]) -> Result<Graph, Error> {
    let files = files(raw)?;
    let layout: serde_json::Value =
        serde_json::from_slice(files.get("oci-layout").ok_or("missing OCI layout")?)?;
    if layout["imageLayoutVersion"] != "1.0.0" {
        return Err("expected OCI layout 1.0".into());
    }
    let index: Document =
        serde_json::from_slice(files.get("index.json").ok_or("missing OCI index")?)?;
    let roots: Vec<_> = index
        .manifests
        .iter()
        .map(|item| item.digest.clone())
        .collect();
    if roots.is_empty() {
        return Err("empty OCI index".into());
    }
    let mut seen = BTreeSet::new();
    let mut pending = index.manifests;
    while let Some(item) = pending.pop() {
        let digest = item
            .digest
            .strip_prefix("sha256:")
            .filter(|s| archive::valid_digest(s))
            .ok_or("unsupported OCI digest")?;
        let blob = files
            .get(&format!("blobs/sha256/{digest}"))
            .ok_or("missing OCI blob")?;
        if blob.len() as u64 != item.size || archive::sha256(blob) != digest {
            return Err("OCI blob differs from descriptor".into());
        }
        if seen.insert(item.digest)
            && (item.media_type.contains("manifest") || item.media_type.contains("index"))
        {
            let content: Document = serde_json::from_slice(blob)?;
            pending.extend(content.manifests);
            pending.extend(content.layers);
            pending.extend(content.config);
        }
    }
    Ok(Graph {
        roots,
        verified_blobs: seen.len(),
    })
}

pub(crate) fn verify(path: &Path) -> Result<Core, Error> {
    let lock: Lock = serde_json::from_slice(LOCK)?;
    for (name, bytes) in [
        ("oci-candidate.json", MANIFEST),
        ("oci-candidate.json.sig", SIGNATURE),
        ("signer.pub", KEY.as_bytes()),
    ] {
        if lock.artifacts.get(name) != Some(&archive::sha256(bytes)) {
            return Err("embedded OCI verification input differs from pin".into());
        }
    }
    let raw = archive::checked_input(path, &lock.archive_sha256)?;
    archive::signature(MANIFEST, SIGNATURE, KEY, "yuki-core-candidate-v1")?;
    let manifest: Manifest = serde_json::from_slice(MANIFEST)?;
    if manifest.source_commit != lock.source_commit
        || manifest.platform != lock.platform
        || manifest.sha256 != lock.archive_sha256
        || manifest.dirty
        || manifest.published
        || !manifest.nonroot_owner
        || manifest.readyz != "verified"
        || manifest.oci.roots.as_slice() != [lock.image_digest.as_str()]
        || graph(&raw)? != manifest.oci
    {
        return Err("signed OCI graph or candidate contract differs".into());
    }
    Ok(Core {
        version: lock.core_version,
        image: lock.image_digest,
        platform: lock.platform,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn signature_binds_both_the_manifest_bytes_and_namespace() {
        let namespace = "yuki-core-candidate-v1";
        archive::signature(MANIFEST, SIGNATURE, KEY, namespace).unwrap();
        let mut changed = MANIFEST.to_vec();
        changed.push(b'\n');
        assert!(archive::signature(&changed, SIGNATURE, KEY, namespace).is_err());
        assert!(archive::signature(MANIFEST, SIGNATURE, KEY, "yuki-plugin-base-1.0").is_err());
    }
}
