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
path.write_text(source.replace(old, new, 1), encoding="utf-8")
