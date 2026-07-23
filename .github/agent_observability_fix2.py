from pathlib import Path

path = Path('.github/agent_observability.py')
text = path.read_text()
old = '''replace_once(
    "services/host-daemon/src/health.rs",
    ''' + "'''" + '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());

        let healthy =
''' + "'''" + ''',
'''
new = '''replace_once(
    "services/host-daemon/src/health.rs",
    ''' + "'''" + '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());
''' + "'''" + ''',
'''
if text.count(old) != 1:
    raise RuntimeError('expected one health observability patch block')
path.write_text(text.replace(old, new, 1))
Path(__file__).unlink()
