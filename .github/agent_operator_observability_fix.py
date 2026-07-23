from pathlib import Path

path = Path('.github/agent_operator_observability.py')
text = path.read_text()
replacements = {
    r'"mobile_proxy_reverse_tunnel_active_transport{{transport=\"{transport}\"}} {}"': r'r#"mobile_proxy_reverse_tunnel_active_transport{{transport="{transport}"}} {}"#',
    r'"mobile_proxy_reverse_tunnel_freshness{{state=\"{state}\"}} {}"': r'r#"mobile_proxy_reverse_tunnel_freshness{{state="{state}"}} {}"#',
    r'"mobile_proxy_reverse_tunnel_last_failover_reason{{reason=\"{reason}\"}} {}"': r'r#"mobile_proxy_reverse_tunnel_last_failover_reason{{reason="{reason}"}} {}"#',
    r'"mobile_proxy_reverse_tunnel_active_transport{transport=\"tls_tcp\"} 1"': r'r#"mobile_proxy_reverse_tunnel_active_transport{transport="tls_tcp"} 1"#',
    r'"mobile_proxy_reverse_tunnel_freshness{state=\"fresh\"} 1"': r'r#"mobile_proxy_reverse_tunnel_freshness{state="fresh"} 1"#',
    r'"mobile_proxy_reverse_tunnel_last_failover_reason{reason=\"connect_timeout\"} 1"': r'r#"mobile_proxy_reverse_tunnel_last_failover_reason{reason="connect_timeout"} 1"#',
    r'metrics.matches("transport=\"")': r'metrics.matches(r#"transport=""#)',
    r'metrics.matches("state=\"")': r'metrics.matches(r#"state=""#)',
    r'metrics.matches("reason=\"")': r'metrics.matches(r#"reason=""#)',
}
for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'expected one metric quote pattern, found {count}: {old}')
    text = text.replace(old, new, 1)
path.write_text(text)
Path(__file__).unlink()
