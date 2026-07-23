from pathlib import Path

path = Path("crates/runtime-domain/src/lib.rs")
body = path.read_text(encoding="utf-8")
old = "/// Concrete transports such as QUIC, TLS/TCP and WireGuard compatibility are\n/// adapter capabilities and must not appear in this state machine.\n"
new = "/// Concrete tunnel implementations are adapter capabilities and must not\n/// appear in this state machine.\n"
if body.count(old) != 1:
    raise RuntimeError("expected runtime-domain transport comment anchor")
path.write_text(body.replace(old, new, 1), encoding="utf-8")
