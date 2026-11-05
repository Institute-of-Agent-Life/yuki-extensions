use serde_json::{Value, json};

pub fn request(job: &Value) -> Result<(&'static str, Value), String> {
    let obj = job.as_object().ok_or("job must be an object")?;
    let action = job["action"].as_str().ok_or("action required")?;
    let (method, allowed, required): (_, &[&str], &[&str]) = match action {
        "scan" => (
            "maintenance.audit",
            &["scope", "purpose", "fact", "after"],
            &["scope", "purpose"],
        ),
        "apply" => (
            "maintenance.audit.apply",
            &[
                "scope",
                "purpose",
                "fact",
                "after",
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
        if k != "approved"
            && k != "revision"
            && !v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 256)
        {
            return Err(format!("invalid {k}"));
        }
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

/// Interpret only the producer's observed counts and semantic identities.
pub fn scan_report(raw: Value) -> Result<Value, String> {
    if raw["paid_calls"] != 0 {
        return Err("audit charged a request".into());
    }
    let items = raw["items"].as_array().ok_or("audit items missing")?;
    let routes = raw["embedding_routes"]
        .as_array()
        .ok_or("audit routes missing")?;
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

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn same_dimensions_different_profile_stays_missing() {
        let r=scan_report(json!({"paid_calls":0,"fingerprint":"original","items":[{"fact":"f","revision":2,"vector_profiles":["old"],"evidence_total":0,"evidence_retained":0}],"embedding_routes":[{"route":"new","profile":"new","dimensions":3}]})).unwrap();
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
    }
}
