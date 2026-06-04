#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
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

if [ ! -x "$BIN/runtime-supervisor" ]; then
  echo "missing runtime-supervisor binary: $BIN/runtime-supervisor" >&2
  exit 1
fi

if [ ! -f "$ROOT/config/host-daemon.json" ]; then
  echo "missing host-daemon config: $ROOT/config/host-daemon.json" >&2
  exit 1
fi

nohup "$BIN/runtime-supervisor" --runtime-root "$ROOT" >> "$SUPERVISOR_LOG" 2>&1 &
log_boot "runtime_supervisor_spawned pid=$!"
