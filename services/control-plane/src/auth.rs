use anyhow::{Result, bail};
use axum::{
    extract::{Request, State},
    http::{HeaderMap, StatusCode, header::AUTHORIZATION},
    middleware::Next,
    response::Response,
};
use subtle::ConstantTimeEq;

#[derive(Clone)]
pub struct AuthConfig {
    admin_token: String,
    device_token: String,
}

impl AuthConfig {
    pub fn new(admin_token: String, device_token: String) -> Result<Self> {
        if admin_token.trim().is_empty() || device_token.trim().is_empty() {
            bail!("control-plane admin and device tokens must be non-empty");
        }
        if bool::from(admin_token.as_bytes().ct_eq(device_token.as_bytes())) {
            bail!("control-plane admin and device tokens must be different");
        }
        Ok(Self {
            admin_token,
            device_token,
        })
    }
}

fn bearer(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
}

fn matches(candidate: Option<&str>, expected: &str) -> bool {
    candidate.is_some_and(|value| bool::from(value.as_bytes().ct_eq(expected.as_bytes())))
}

pub async fn require_admin(
    State(auth): State<AuthConfig>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    if !matches(bearer(request.headers()), &auth.admin_token) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(next.run(request).await)
}

pub async fn require_device(
    State(auth): State<AuthConfig>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    if !matches(bearer(request.headers()), &auth.device_token) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(next.run(request).await)
}

#[cfg(test)]
mod tests {
    use super::AuthConfig;

    #[test]
    fn rejects_empty_or_shared_tokens() {
        assert!(AuthConfig::new("".into(), "device".into()).is_err());
        assert!(AuthConfig::new("same".into(), "same".into()).is_err());
        assert!(AuthConfig::new("admin".into(), "device".into()).is_ok());
    }
}
