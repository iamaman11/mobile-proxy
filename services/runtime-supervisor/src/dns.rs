use std::{fs, net::IpAddr, process::Command};

use anyhow::{Context, Result, bail};
use serde_json::{Value, json};
use tracing::info;

use crate::config::SupervisorConfig;

pub fn reconcile_cellular_dns(config: &SupervisorConfig) -> Result<bool> {
    let output = Command::new("dumpsys")
        .arg("connectivity")
        .output()
        .context("failed to run dumpsys connectivity")?;
    if !output.status.success() {
        bail!("dumpsys connectivity failed");
    }
    let addresses = parse_validated_cellular_dns(&String::from_utf8_lossy(&output.stdout));
    if addresses.is_empty() {
        return Ok(false);
    }

    let body = fs::read_to_string(&config.proxy_config)
        .with_context(|| format!("failed to read {}", config.proxy_config.display()))?;
    let mut document: Value = serde_json::from_str(&body)
        .with_context(|| format!("failed to parse {}", config.proxy_config.display()))?;
    let servers: Vec<Value> = addresses
        .iter()
        .enumerate()
        .map(|(index, address)| {
            json!({
                "type": "udp",
                "tag": format!("dns-cellular-{}", index + 1),
                "server": address.to_string(),
                "server_port": 53
            })
        })
        .collect();
    let primary = "dns-cellular-1";
    if document.pointer("/dns/servers") == Some(&Value::Array(servers.clone()))
        && document.pointer("/dns/final").and_then(Value::as_str) == Some(primary)
        && document
            .pointer("/route/default_domain_resolver")
            .and_then(Value::as_str)
            == Some(primary)
    {
        return Ok(false);
    }

    document["dns"]["servers"] = Value::Array(servers);
    document["dns"]["final"] = Value::String(primary.into());
    document["route"]["default_domain_resolver"] = Value::String(primary.into());
    let temp = config.proxy_config.with_extension("json.tmp");
    fs::write(&temp, serde_json::to_vec_pretty(&document)?)
        .with_context(|| format!("failed to write {}", temp.display()))?;
    fs::rename(&temp, &config.proxy_config)
        .with_context(|| format!("failed to replace {}", config.proxy_config.display()))?;
    info!(dns_servers = ?addresses, "updated proxy DNS from validated cellular network");
    Ok(true)
}

fn parse_validated_cellular_dns(raw: &str) -> Vec<IpAddr> {
    raw.lines()
        .filter(|line| {
            line.contains("NetworkAgentInfo")
                && line.contains("type: MOBILE")
                && line.contains("state: CONNECTED/CONNECTED")
                && line.contains("VALIDATED")
                && !line.contains("CAPTIVE_PORTAL")
        })
        .flat_map(|line| {
            line.split("DnsAddresses: [")
                .nth(1)
                .and_then(|rest| rest.split(']').next())
                .unwrap_or_default()
                .split(',')
                .filter_map(|raw| raw.trim().trim_start_matches('/').parse().ok())
                .collect::<Vec<IpAddr>>()
        })
        .fold(Vec::new(), |mut unique, address| {
            if !unique.contains(&address) {
                unique.push(address);
            }
            unique
        })
}

#[cfg(test)]
mod tests {
    use super::parse_validated_cellular_dns;

    #[test]
    fn extracts_validated_cellular_dns() {
        let line = "NetworkAgentInfo{ ni{[type: MOBILE[LTE], state: CONNECTED/CONNECTED]} lp{{DnsAddresses: [ /134.17.1.0,/134.17.1.1 ]}} nc{[ INTERNET&VALIDATED ]}}";
        assert_eq!(
            parse_validated_cellular_dns(line),
            [
                "134.17.1.0".parse::<std::net::IpAddr>().unwrap(),
                "134.17.1.1".parse::<std::net::IpAddr>().unwrap(),
            ]
        );
    }

    #[test]
    fn rejects_captive_dns() {
        let line = "NetworkAgentInfo{ ni{[type: MOBILE[LTE], state: CONNECTED/CONNECTED]} lp{{DnsAddresses: [ /1.2.3.4 ]}} nc{[ VALIDATED&CAPTIVE_PORTAL ]}}";
        assert!(parse_validated_cellular_dns(line).is_empty());
    }
}
