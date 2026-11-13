use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, fs, io, path::Path};

pub fn request(job: &Value) -> Result<(&'static str, Value), String> {
    let obj = job.as_object().ok_or("job must be an object")?;
    let action = job["action"].as_str().ok_or("action required")?;
    let (method, allowed, required): (_, &[&str], &[&str]) = match action {
        "scan" | "audit" | "stats" => (
            "maintenance.audit",
            &["scope", "purpose", "fact", "after", "integrity"],
            &["scope", "purpose"],
        ),
        "apply" => (
            "maintenance.audit.apply",
            &[
                "scope",
                "purpose",
                "fact",
                "after",
                "integrity",
                "operation",
                "fingerprint",
                "approved",
            ],
            &["scope", "purpose", "operation", "fingerprint", "approved"],
        ),
        "reembed" => (
            "maintenance.reembed",
            &[
                "scope",
                "purpose",
                "operation",
                "route",
                "profile",
                "fact",
                "revision",
            ],
            &[
                "scope",
                "purpose",
                "operation",
                "route",
                "profile",
                "fact",
                "revision",
            ],
        ),
        _ => return Err("unsupported maintenance action".into()),
    };
    if obj
        .keys()
        .any(|k| k != "action" && !allowed.contains(&k.as_str()))
    {
        return Err("unknown job field".into());
    }
    let mut params = serde_json::Map::new();
    for k in allowed {
        if let Some(v) = obj.get(*k) {
            params.insert((*k).into(), v.clone());
        }
    }
    for k in required {
        if !params.contains_key(*k) {
            return Err(format!("missing {k}"));
        }
    }
    for (k, v) in &params {
        let valid = match k.as_str() {
            "integrity" => v.is_boolean(),
            "approved" | "revision" => true,
            _ => v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 256),
        };
        if !valid {
            return Err(format!("invalid {k}"));
        }
    }
    if action == "audit" || action == "stats" {
        params.entry("integrity").or_insert(Value::Bool(true));
    }
    if action == "stats" && params["integrity"] != true {
        return Err("stats requires integrity findings".into());
    }
    if action == "apply" {
        let ids = params["approved"]
            .as_array()
            .ok_or("approved must be an array")?;
        let mut seen = std::collections::HashSet::new();
        if ids.len() > 8
            || ids.iter().any(|v| {
                !v.as_str()
                    .is_some_and(|s| !s.is_empty() && s.len() <= 256 && seen.insert(s))
            })
        {
            return Err("invalid or duplicate approved fact".into());
        }
    }
    if action == "reembed" && !params["revision"].as_u64().is_some_and(|n| n > 0) {
        return Err("positive original revision required".into());
    }
    Ok((method, Value::Object(params)))
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum Lexical {
    Current,
    Missing,
    Mismatch,
    NotIndexed,
    Unexpected,
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum VectorState {
    Current,
    Missing,
    InvalidShape,
    Stale,
    NotIndexed,
}

#[derive(Deserialize, Serialize)]
struct VectorCoverage {
    route: String,
    profile: String,
    coverage: VectorState,
    attempt: Option<String>,
}

#[derive(Deserialize)]
struct Integrity {
    lexical: Lexical,
    evidence_missing: bool,
    event_evidence_checked: u64,
    invalid_event_evidence: u64,
    vectors: Vec<VectorCoverage>,
}

pub fn scan_report(raw: Value, integrity_requested: bool) -> Result<Value, String> {
    if raw["paid_calls"] != 0 {
        return Err("audit charged a request".into());
    }
    let items = raw["items"].as_array().ok_or("audit items missing")?;
    let routes = raw["embedding_routes"]
        .as_array()
        .ok_or("audit routes missing")?;
    if integrity_requested {
        let mut findings = Vec::with_capacity(items.len());
        let mut coverage = Vec::with_capacity(items.len());
        let mut lexical_repairs = 0;
        let mut missing_evidence = 0;
        let mut checked = 0_u64;
        let mut invalid = 0_u64;
        for item in items {
            let integrity = Integrity::deserialize(&item["integrity"])
                .map_err(|e| format!("Host integrity findings unavailable: {e}"))?;
            lexical_repairs += usize::from(matches!(
                integrity.lexical,
                Lexical::Missing | Lexical::Mismatch | Lexical::Unexpected
            ));
            missing_evidence += usize::from(integrity.evidence_missing);
            checked = checked
                .checked_add(integrity.event_evidence_checked)
                .ok_or("invalid checked evidence count")?;
            invalid = invalid
                .checked_add(integrity.invalid_event_evidence)
                .ok_or("invalid evidence count")?;
            findings.push(json!({
                "fact": item["fact"], "revision": item["revision"],
                "lexical": integrity.lexical, "evidence_missing": integrity.evidence_missing,
                "event_evidence_checked": integrity.event_evidence_checked,
                "invalid_event_evidence": integrity.invalid_event_evidence,
            }));
            coverage.push(json!({
                "fact": item["fact"], "revision": item["revision"],
                "retained_evidence": item["evidence_retained"], "recorded_evidence": item["evidence_total"],
                "profiles": integrity.vectors,
            }));
        }
        let stats = json!({
            "facts": items.len(), "lexical_repairs": lexical_repairs,
            "facts_missing_evidence": missing_evidence,
            "event_evidence_checked": checked, "invalid_event_evidence": invalid,
        });
        return Ok(json!({
            "audit": raw, "coverage": coverage, "bounded_page": true,
            "quality_findings": findings, "stats": stats, "paid_calls": 0,
        }));
    }
    let coverage: Vec<_> = items.iter().map(|item| {
        let profiles = item["vector_profiles"].as_array().cloned().unwrap_or_default();
        let missing: Vec<_> = routes.iter().filter(|r| !profiles.contains(&r["profile"]))
            .map(|r| json!({"route":r["route"],"profile":r["profile"],"dimensions":r["dimensions"]})).collect();
        json!({"fact":item["fact"],"revision":item["revision"],
               "retained_evidence":item["evidence_retained"],"recorded_evidence":item["evidence_total"],
               "missing_profiles":missing,"missing_profile_attempt_state":"not_observed_by_audit"})
    }).collect();
    Ok(json!({"audit":raw,"coverage":coverage,"bounded_page":true,
              "quality_findings":"not_exposed_by_candidate","paid_calls":0}))
}

fn references(values: &Value) -> Result<BTreeSet<String>, String> {
    serde_json::from_value(values.clone()).map_err(|_| "quality erasure references missing".into())
}

pub fn bind_result(method: &str, response: &Value) -> Result<BTreeSet<String>, String> {
    if method == "maintenance.audit" {
        let mut all = BTreeSet::new();
        for item in response["items"].as_array().ok_or("audit items missing")? {
            all.extend(references(&item["erasure_refs"])?);
        }
        return Ok(all);
    }
    references(&response["erasure_refs"])
}

pub fn erase(root: &Path, params: &Value) -> Result<(), String> {
    let erased = references(&params["erasure_refs"])?;
    if erased.is_empty() || params["sources"].as_array().is_none_or(|s| !s.is_empty()) {
        return Err("unrecognized quality erasure obligation".into());
    }
    let mut unclassified = false;
    for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        let Some(file) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        let Some(name) = file
            .strip_suffix(".result.tmp")
            .or_else(|| file.strip_suffix(".result"))
            .filter(|name| super::job_name(name))
        else {
            continue;
        };
        let result: Value = match crate::rebuild::read_json(&path) {
            Ok(Some(result)) => result,
            Ok(None) => continue,
            Err(_) => {
                unclassified = true;
                continue;
            }
        };
        let matches = match result["state"].as_str() {
            Some("not_completed") => false,
            Some("completed") => match references(&result["erasure_refs"]) {
                Ok(refs) => !refs.is_disjoint(&erased),
                Err(_) => {
                    unclassified = true;
                    continue;
                }
            },
            _ => {
                unclassified = true;
                continue;
            }
        };
        if matches {
            let job = root.join(format!("{name}.job"));
            if !root.join(format!("{name}.started")).is_file() {
                return Err("original quality job fence missing".into());
            }
            remove(&job)?;
            remove(&path)?;
        }
    }
    crate::rebuild::sync_dir(root).map_err(|e| e.to_string())?;
    if unclassified {
        return Err("quality report erasure requires classification of remaining files".into());
    }
    Ok(())
}

fn remove(path: &Path) -> Result<(), String> {
    match fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn same_dimensions_different_profile_stays_missing() {
        let legacy = json!({"paid_calls":0,"fingerprint":"original","items":[{"fact":"f","revision":2,"vector_profiles":["old"],"evidence_total":0,"evidence_retained":0}],"embedding_routes":[{"route":"new","profile":"new","dimensions":3}]});
        assert!(scan_report(legacy.clone(), true).is_err());
        let r = scan_report(legacy, false).unwrap();
        assert_eq!(r["coverage"][0]["missing_profiles"][0]["profile"], "new");
        assert_eq!(r["coverage"][0]["retained_evidence"], 0);
        assert_eq!(
            r["coverage"][0]["missing_profile_attempt_state"],
            "not_observed_by_audit"
        );
    }
    #[test]
    fn explicit_original_operation_and_unique_subset_required() {
        assert!(request(&json!({"action":"apply","scope":"own","purpose":"quality","fingerprint":"fp","approved":[]})).is_err());
        assert!(request(&json!({"action":"apply","scope":"own","purpose":"quality","operation":"o","fingerprint":"fp","approved":["f","f"]})).is_err());
        assert!(
            request(&json!({"action":"scan","scope":"own","purpose":"quality","actor":"override"}))
                .is_err()
        );
        assert!(
            request(&json!({"action":"scan","scope":"own","purpose":"quality","integrity":"true"}))
                .is_err()
        );
        let (method, params) =
            request(&json!({"action":"stats","scope":"own","purpose":"quality"})).unwrap();
        assert_eq!(method, "maintenance.audit");
        assert_eq!(params["integrity"], true);
    }
}
