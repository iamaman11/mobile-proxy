use axum::{
    Json,
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
};

use subtle::ConstantTimeEq;

pub fn authorize(headers: &HeaderMap, token: &str) -> Result<(), ApiError> {
    let actual = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    
    let is_authorized = if let Some(actual_token) = actual {
        bool::from(actual_token.as_bytes().ct_eq(token.as_bytes()))
    } else {
        false
    };

    if is_authorized {
        Ok(())
    } else {
        Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "invalid bearer token".into(),
        ))
    }
}

pub struct ApiError(pub StatusCode, pub String);

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        (self.0, Json(serde_json::json!({ "error": self.1 }))).into_response()
    }
}
