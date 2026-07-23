#!/usr/bin/env python3
from pathlib import Path

ROOT = Path.cwd()


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    body = path.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{relative}: expected one anchor, found {count}")
    path.write_text(body.replace(old, new), encoding="utf-8")


replace_once(
    "services/control-plane/src/state.rs",
    "            commands\n"
    "                .idempotency\n"
    "                .insert(legacy, command.command_id);\n"
    "            migration.recovered_results += 1;\n"
    "        }\n"
    "        if canonical != legacy\n",
    "            commands\n"
    "                .idempotency\n"
    "                .insert(legacy.clone(), command.command_id);\n"
    "            migration.recovered_results += 1;\n"
    "        }\n"
    "        if canonical != legacy\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "        MAX_PENDING_COMMANDS, idempotency_scope_key,\n",
    "        MAX_COMMAND_QUEUE_PER_DEVICE, MAX_PENDING_COMMANDS, idempotency_scope_key,\n",
)
print("command safety compile fix applied")
