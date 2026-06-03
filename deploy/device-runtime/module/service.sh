#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
RUNTIME_ROOT="/data/adb/mobile-proxy-node"
BIN="$ROOT/bin"
LOG_DIR="/data/local/tmp/mobile-proxy-logs"
BOOT_LOG="$LOG_DIR/runtime-boot.log"
SUPERVISOR_LOG="$LOG_DIR/runtime-supervisor.log"

export PATH="$BIN:$PATH"

mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

log_boot() {
  echo "$(timestamp) $*" >> "$BOOT_LOG"
}

stop_legacy_runtime_procs() {
  pkill -f "$RUNTIME_ROOT/current/bin/runtime-supervisor" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/runtime-supervisor" || true
  pkill -f "$RUNTIME_ROOT/current/bin/host-daemon" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/host-daemon" || true
  pkill -f "$RUNTIME_ROOT/current/bin/sing-box" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/sing-box" || true
  pkill -f "$RUNTIME_ROOT/current/service.sh --route-guard" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/service.sh --route-guard" || true
}

if [ ! -x "$BIN/runtime-supervisor" ]; then
  echo "missing runtime-supervisor binary: $BIN/runtime-supervisor" >&2
  exit 1
fi

if [ ! -f "$ROOT/config/host-daemon.json" ]; then
  echo "missing host-daemon config: $ROOT/config/host-daemon.json" >&2
  exit 1
fi

stop_legacy_runtime_procs
sleep 1

nohup "$BIN/runtime-supervisor" --runtime-root "$ROOT" >> "$SUPERVISOR_LOG" 2>&1 &
log_boot "runtime_supervisor_spawned pid=$!"
