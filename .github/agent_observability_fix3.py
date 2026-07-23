from pathlib import Path

path = Path('.github/agent_observability.py')
text = path.read_text()
marker = '''workflow = subprocess.check_output(
    ["git", "show", "origin/main:.github/workflows/rust-quality.yml"],
    text=True,
)
'''
addition = '''replace_once(
    "apps/operator-cli/src/commands.rs",
    ''' + "'''" + '''            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            tunnel_owner: Some("stock_wireguard_bridge".into()),
''' + "'''" + ''',
    ''' + "'''" + '''            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            reverse_tunnel_active_transport: None,
            reverse_tunnel_freshness: None,
            reverse_tunnel_failover_reason: None,
            tunnel_owner: Some("stock_wireguard_bridge".into()),
''' + "'''" + '''
)
'''
if text.count(marker) != 1:
    raise RuntimeError('expected one workflow restoration marker')
path.write_text(text.replace(marker, addition + marker, 1))
Path(__file__).unlink()
