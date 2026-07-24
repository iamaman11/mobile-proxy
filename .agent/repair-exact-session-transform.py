from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
old = r'''tunnel = replace_once(
    tunnel,
    """                mark_heartbeat(&state, &heartbeat).await;
""",
    """                mark_heartbeat(&state, &heartbeat, authority_id).await;
""",
    "QUIC heartbeat authority",
)
'''
new = r'''tunnel = replace_once(
    tunnel,
    """            Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                mark_heartbeat(&state, &heartbeat).await;
            }
""",
    """            Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                mark_heartbeat(&state, &heartbeat, authority_id).await;
            }
""",
    "QUIC heartbeat authority",
)
'''
count = source.count(old)
if count != 1:
    raise SystemExit(f"QUIC heartbeat transformation repair: expected one source block, found {count}")
source = source.replace(old, new, 1)

output_repair_source = Path(".agent/repair-exact-session-output.py").read_text(encoding="utf-8")
Path("/tmp/repair-exact-session-output.py").write_text(output_repair_source, encoding="utf-8")
source += r'''

from pathlib import Path as _ExactSessionRepairPath
_exact_session_repair_path = _ExactSessionRepairPath("/tmp/repair-exact-session-output.py")
exec(
    compile(
        _exact_session_repair_path.read_text(encoding="utf-8"),
        str(_exact_session_repair_path),
        "exec",
    )
)
'''

path.write_text(source, encoding="utf-8")
