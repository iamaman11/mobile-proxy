from pathlib import Path

path = Path(".agent/apply_foundation_primitives.py")
body = path.read_text(encoding="utf-8")
old = '''replace_once(
    "services/control-plane/src/routes.rs",
    "use uuid::Uuid;\\n",
    "use mobile_proxy_foundation::{CommandId, RequestContext};\\nuse uuid::Uuid;\\n",
)
'''
new = '''replace_once(
    "services/control-plane/src/routes.rs",
    "};\\nuse uuid::Uuid;\\n\\nuse crate::auth",
    "};\\nuse mobile_proxy_foundation::{CommandId, RequestContext};\\nuse uuid::Uuid;\\n\\nuse crate::auth",
)
'''
if body.count(old) != 1:
    raise RuntimeError("expected ambiguous uuid import patch block")
path.write_text(body.replace(old, new, 1), encoding="utf-8")
