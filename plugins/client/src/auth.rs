use std::net::SocketAddr;
use tiny_http::{Method, Request};

pub fn loopback(name: &str) -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let address: SocketAddr = std::env::var(name)?.parse()?;
    if !address.ip().is_loopback() || address.port() == 0 {
        return Err("expected a configured loopback port".into());
    }
    Ok(address)
}

// Only the owner authenticates devices, resolves selected entries, and commits request IDs.
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
        (&Method::Post, ["pair" | "messages" | "uploads"])
            | (&Method::Get, ["me" | "home" | "stream" | "meta"])
            | (&Method::Get, ["requests", _])
            | (&Method::Get, ["conversations", _, "events"])
            | (
                &Method::Get,
                ["conversations", _, "events", _, "attachments", _]
            )
    );
    if !public {
        return Err((404, "not_found"));
    }
    for name in ["Authorization", "X-Yuki-Entry", "X-Yuki-Conversation"] {
        if request
            .headers()
            .iter()
            .filter(|h| h.field.equiv(name))
            .count()
            > 1
        {
            return Err((400, "ambiguous_authority"));
        }
    }
    Ok(())
}
