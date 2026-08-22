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
    ui_token: String,
}

impl AuthConfig {
    pub fn new(admin_token: String, device_token: String, ui_token: String) -> Result<Self> {
        validate_token("control-plane admin token", &admin_token)?;
        validate_token("control-plane device token", &device_token)?;
        validate_token("control-plane UI token", &ui_token)?;
        if bool::from(admin_token.as_bytes().ct_eq(device_token.as_bytes()))
            || bool::from(admin_token.as_bytes().ct_eq(ui_token.as_bytes()))
            || bool::from(device_token.as_bytes().ct_eq(ui_token.as_bytes()))
        {
            bail!("control-plane admin, device, and UI tokens must be different")
        }
        Ok(Self {
            admin_token,
            device_token,
            ui_token,
        })
    }
}

fn bearer(headers: &HeaderMap) -> Option<&str> {
    let candidate = headers
        .get(AUTHORIZATION)?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")?;
    if candidate.is_empty()
        || candidate.len() > 4096
        || candidate
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
    {
        return None;
    }
    Some(candidate)
}

fn matches(candidate: Option<&str>, expected: &str) -> bool {
    candidate.is_some_and(|value| bool::from(value.as_bytes().ct_eq(expected.as_bytes())))
}

fn validate_token(field: &str, value: &str) -> Result<()> {
    if value.len() < 8
        || value.len() > 4096
        || value
            .chars()
            .any(|character| character.is_control() || character.is_whitespace())
    {
        bail!("{field} is invalid")
    }
    Ok(())
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

pub async fn require_ui(
    State(auth): State<AuthConfig>,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    if !matches(bearer(request.headers()), &auth.ui_token) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(next.run(request).await)
}

#[cfg(test)]
mod tests {
    use axum::http::{HeaderMap, HeaderValue, header::AUTHORIZATION};

    use super::{AuthConfig, bearer};

    #[test]
    fn rejects_invalid_or_shared_tokens() {
        assert!(AuthConfig::new("".into(), "device-token".into(), "ui-token".into()).is_err());
        assert!(
            AuthConfig::new("same-token".into(), "same-token".into(), "ui-token".into()).is_err()
        );
        assert!(
            AuthConfig::new(
                "admin token with spaces".into(),
                "device-token".into(),
                "ui-token".into()
            )
            .is_err()
        );
        assert!(
            AuthConfig::new(
                "admin-secret".into(),
                "device-secret".into(),
                "ui-secret".into()
            )
            .is_ok()
        );
    }

    #[test]
    fn bearer_syntax_is_exact_and_bounded() {
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_static("Bearer admin-secret"),
        );
        assert_eq!(bearer(&headers), Some("admin-secret"));
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_static("Bearer token with spaces"),
        );
        assert!(bearer(&headers).is_none());
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_static("bearer admin-secret"),
        );
        assert!(bearer(&headers).is_none());
    }
}
