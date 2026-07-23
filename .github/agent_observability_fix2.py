from pathlib import Path

path = Path('.github/agent_observability.py')
text = path.read_text()
old_anchor = '''replace_once(
    "services/host-daemon/src/health.rs",
    ''' + "'''" + '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());

        let healthy =
''' + "'''" + ''',
'''
new_anchor = '''replace_once(
    "services/host-daemon/src/health.rs",
    ''' + "'''" + '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());
''' + "'''" + ''',
'''
if text.count(old_anchor) != 1:
    raise RuntimeError('expected one health observability anchor')
text = text.replace(old_anchor, new_anchor, 1)
old_suffix = '''        let healthy =
''' + "'''" + '''
)
replace_once(
    "services/host-daemon/src/control_plane.rs",
'''
new_suffix = "'''\n)\nreplace_once(\n    \"services/host-daemon/src/control_plane.rs\",\n"
if text.count(old_suffix) != 1:
    raise RuntimeError('expected one duplicated healthy suffix')
text = text.replace(old_suffix, new_suffix, 1)
path.write_text(text)
Path(__file__).unlink()
