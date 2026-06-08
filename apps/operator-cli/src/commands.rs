use anyhow::{Result, bail};
use proxy_core::{HealthRecord, JobRecord, RotateRequest, proxy_endpoints};
use serde::Serialize;
use uuid::Uuid;

use crate::cli::{AirplaneStudyArgs, RotateArgs};
use crate::http::{fetch_health, issue_rotation, wait_for_rotation};

#[derive(Debug, Serialize)]
pub struct StudyTrial {
    hold_secs: u64,
    run: u32,
    job_id: Uuid,
    job_status: String,
    changed: Option<bool>,
    final_readiness_state: String,
    final_serving: bool,
    final_public_ip: Option<String>,
    success: bool,
}

#[derive(Debug, Serialize)]
pub struct StudySummary {
    hold_secs: u64,
    runs: u32,
    successes: u32,
    success_rate: f64,
}

#[derive(Debug, Serialize)]
pub struct StudyReport {
    pub mode: &'static str,
    pub minimum_success_rate: f64,
    pub recommended_hold_secs: Option<u64>,
    pub summaries: Vec<StudySummary>,
    pub trials: Vec<StudyTrial>,
}

pub async fn run_status(client: &reqwest::Client, api: &str, token: &str) -> Result<()> {
    let health = fetch_health(client, api, token).await?;
    println!("{}", serde_json::to_string_pretty(&health)?);
    Ok(())
}

pub fn run_proxy() -> Result<()> {
    println!("{}", serde_json::to_string_pretty(&proxy_endpoints())?);
    Ok(())
}

pub async fn run_rotate(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    args: &RotateArgs,
) -> Result<()> {
    let request = build_rotate_request(args);
    let accepted = issue_rotation(client, api, token, &request).await?;
    println!("job accepted: {}", accepted.job_id);
    let (job, health) =
        wait_for_rotation(client, api, token, accepted.job_id, args.poll_secs).await?;
    println!("{}", serde_json::to_string_pretty(&job)?);
    println!("{}", serde_json::to_string_pretty(&health)?);
    Ok(())
}

pub async fn run_airplane_study(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    args: &AirplaneStudyArgs,
) -> Result<()> {
    let report = airplane_study_report(client, api, token, args).await?;
    println!("{}", serde_json::to_string_pretty(&report)?);
    if let Some(hold_secs) = report.recommended_hold_secs {
        println!(
            "recommended_hold_secs={} minimum_success_rate={}",
            hold_secs, report.minimum_success_rate
        );
        Ok(())
    } else {
        bail!(
            "no tested hold duration met the required success rate of {}",
            report.minimum_success_rate
        );
    }
}

pub fn build_rotate_request(args: &RotateArgs) -> RotateRequest {
    RotateRequest {
        strategy: args.strategy.clone(),
        require_public_ip_change: args.require_public_ip_change,
        reason: args.reason.clone(),
        hold_secs: args.hold_secs,
    }
}

pub async fn airplane_study_report(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    args: &AirplaneStudyArgs,
) -> Result<StudyReport> {
    let mut holds = args.hold_secs.clone();
    holds.sort_unstable();
    holds.dedup();

    let mut summaries = Vec::new();
    let mut trials = Vec::new();

    for hold_secs in holds {
        let mut successes = 0_u32;
        for run in 1..=args.runs {
            let request = RotateRequest {
                strategy: "airplane_bounce".into(),
                require_public_ip_change: args.require_public_ip_change,
                reason: format!("{}-{}s-run-{}", args.reason_prefix, hold_secs, run),
                hold_secs: Some(hold_secs),
            };
            let accepted = issue_rotation(client, api, token, &request).await?;
            let (job, health) =
                wait_for_rotation(client, api, token, accepted.job_id, args.poll_secs).await?;
            let success = is_successful_rotation(&job, &health, request.require_public_ip_change);
            if success {
                successes += 1;
            }
            println!(
                "hold={}s run={}/{} status={} changed={:?} readiness={} serving={} success={}",
                hold_secs,
                run,
                args.runs,
                job.status,
                job.changed,
                health.readiness_state,
                health.serving,
                success
            );
            trials.push(StudyTrial {
                hold_secs,
                run,
                job_id: accepted.job_id,
                job_status: job.status,
                changed: job.changed,
                final_readiness_state: health.readiness_state,
                final_serving: health.serving,
                final_public_ip: health.last_public_ip,
                success,
            });
        }
        let success_rate = f64::from(successes) / f64::from(args.runs);
        summaries.push(StudySummary {
            hold_secs,
            runs: args.runs,
            successes,
            success_rate,
        });
    }

    let minimum_success_rate = 0.99_f64;
    let recommended_hold_secs = summaries
        .iter()
        .find(|summary| summary.success_rate >= minimum_success_rate)
        .map(|summary| summary.hold_secs);

    Ok(StudyReport {
        mode: "programmatic_only",
        minimum_success_rate,
        recommended_hold_secs,
        summaries,
        trials,
    })
}

pub fn is_successful_rotation(
    job: &JobRecord,
    health: &HealthRecord,
    require_public_ip_change: bool,
) -> bool {
    job.status == "succeeded"
        && health.readiness_state == "healthy"
        && health.serving
        && (!require_public_ip_change || job.changed == Some(true))
}

#[cfg(test)]
mod tests {
    use super::{build_rotate_request, is_successful_rotation};
    use crate::cli::RotateArgs;
    use proxy_core::{
        DEFAULT_AIRPLANE_HOLD_SECS, HealthRecord, JobRecord, RotateRequest, default_rotate_request,
    };
    use uuid::Uuid;

    #[test]
    fn rotate_request_preserves_explicit_hold_secs() {
        let args = RotateArgs {
            strategy: "airplane_bounce".into(),
            require_public_ip_change: true,
            reason: "study".into(),
            hold_secs: Some(3),
            poll_secs: 2,
        };
        let request = build_rotate_request(&args);
        assert_eq!(request.hold_secs, Some(3));
    }

    #[test]
    fn default_rotate_request_uses_default_hold_secs() {
        let request: RotateRequest = default_rotate_request();
        assert_eq!(request.hold_secs, Some(DEFAULT_AIRPLANE_HOLD_SECS));
    }

    #[test]
    fn successful_rotation_requires_healthy_runtime() {
        let job = JobRecord {
            id: Uuid::new_v4(),
            kind: "rotate_ip".into(),
            status: "succeeded".into(),
            old_public_ip: Some("1.1.1.1".into()),
            new_public_ip: Some("2.2.2.2".into()),
            changed: Some(true),
        };
        let health = HealthRecord {
            node_id: "node".into(),
            node_name: "node".into(),
            binary_fingerprint: "fp".into(),
            readiness_state: "healthy".into(),
            serving: true,
            proxy_status: "running".into(),
            last_public_ip: Some("2.2.2.2".into()),
            active_operator_profile: None,
            active_operator_plmn: None,
            last_proxy_error: None,
            serving_failure_reason: None,
            degradation_reason_code: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
            tun0_present: Some(true),
            wg_handshake_recent: Some(true),
            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            tunnel_owner: Some("stock_wireguard_bridge".into()),
        };
        assert!(is_successful_rotation(&job, &health, true));

        let mut unhealthy = health.clone();
        unhealthy.readiness_state = "waiting_cellular".into();
        assert!(!is_successful_rotation(&job, &unhealthy, true));
    }
}
