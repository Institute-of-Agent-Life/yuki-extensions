#[path = "../src/auth.rs"]
mod auth;
use tiny_http::{Header, Method, TestRequest};

#[test]
fn only_the_supported_owner_routes_can_be_dispatched() {
    assert!(auth::loopback("YUKI_UNCONFIGURED_CLIENT_REGRESSION_ADDRESS").is_err());
    let good = TestRequest::new()
        .with_method(Method::Post)
        .with_path("/client/v1/messages");
    assert!(auth::check(&good.into()).is_ok());
    for path in [
        "/admin/v1/health",
        "/client/v1/../admin",
        "/client/v1/%2e%2e/admin",
        "/client/v1/conversations/x%2f..%2fadmin/events",
    ] {
        let req = TestRequest::new().with_path(path);
        assert_eq!(auth::check(&req.into()).unwrap_err().0, 404);
    }
}

#[test]
fn explicit_selectors_and_ambiguous_bearers_stop_before_dispatch() {
    for header in ["X-Yuki-Entry", "X-Yuki-Conversation"] {
        let req = TestRequest::new()
            .with_path("/client/v1/me")
            .with_header(Header::from_bytes(header, "other").unwrap());
        assert_eq!(
            auth::check(&req.into()).unwrap_err(),
            (503, "owner_selection_unavailable")
        );
    }
    let req = TestRequest::new()
        .with_path("/client/v1/me")
        .with_header(Header::from_bytes("Authorization", "Bearer one").unwrap())
        .with_header(Header::from_bytes("Authorization", "Bearer two").unwrap());
    assert_eq!(
        auth::check(&req.into()).unwrap_err(),
        (400, "ambiguous_authorization")
    );
}
