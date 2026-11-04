use std::net::SocketAddr;
use tiny_http::{Method, Request};

pub fn loopback(name: &str) -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let address: SocketAddr = std::env::var(name)?.parse()?;
    if !address.ip().is_loopback() || address.port() == 0 {
        return Err("expected a configured loopback port".into());
    }
    Ok(address)
}

// Only the owner authenticates devices, picks the implicit entry, and commits request IDs.
// The pinned owner ignores explicit selectors, even when a foreign binding is supplied.
pub fn check(request: &Request) -> Result<(), (u16, &'static str)> {
    let path = request.url().split('?').next().unwrap_or("");
    let route = path.strip_prefix("/client/v1/").ok_or((404, "not_found"))?;
    if route.split('/').any(|p| {
        p.is_empty()
            || p == "."
            || p == ".."
            || !p
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    }) {
        return Err((404, "not_found"));
    }
    let parts: Vec<_> = route.split('/').collect();
    let public = matches!(
        (request.method(), parts.as_slice()),
        (&Method::Post, ["pair" | "messages"])
            | (&Method::Get, ["me" | "stream" | "meta"])
            | (&Method::Get, ["requests", _])
            | (&Method::Get, ["conversations", _, "events"])
    );
    if !public {
        return Err((404, "not_found"));
    }
    if request
        .headers()
        .iter()
        .any(|h| h.field.equiv("X-Yuki-Entry") || h.field.equiv("X-Yuki-Conversation"))
    {
        return Err((503, "owner_selection_unavailable"));
    }
    if request
        .headers()
        .iter()
        .filter(|h| h.field.equiv("Authorization"))
        .count()
        > 1
    {
        return Err((400, "ambiguous_authorization"));
    }
    Ok(())
}
