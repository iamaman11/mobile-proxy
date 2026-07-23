from pathlib import Path

path = Path('.github/agent_observability.py')
text = path.read_text()
old = '''replace_once(
    "services/host-daemon/src/health.rs",
    ''' + "'''" + '''                .as_ref()
                .is_some_and(|snapshot| snapshot.connected);
''' + "'''" + ''',
    ''' + "'''" + '''                .as_ref()
                .is_some_and(|snapshot| {
                    snapshot.connected && snapshot.freshness == TunnelFreshness::Fresh
                });
''' + "'''" + '''
)
'''
new = '''replace_once(
    "services/host-daemon/src/health.rs",
    ".is_some_and(|snapshot| snapshot.connected);",
    ''' + "'''" + '''.is_some_and(|snapshot| {
                    snapshot.connected && snapshot.freshness == TunnelFreshness::Fresh
                });''' + "'''" + '''
)
'''
if text.count(old) != 1:
    raise RuntimeError('expected one health readiness patch block')
path.write_text(text.replace(old, new, 1))
Path(__file__).unlink()
