#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
BIN="$ROOT/bin"
LOG_DIR="/data/local/tmp/mobile-proxy-logs"
BOOT_LOG="$LOG_DIR/runtime-boot.log"
SUPERVISOR_LOG="$LOG_DIR/runtime-supervisor.log"
WATCHDOG_PID="$LOG_DIR/runtime-watchdog.pid"

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

if [ -f "$WATCHDOG_PID" ] && kill -0 "$(cat "$WATCHDOG_PID")" 2>/dev/null; then
  log_boot "runtime_watchdog_already_running pid=$(cat "$WATCHDOG_PID")"
  exit 0
fi

nohup sh -c '
ROOT="$1"
BIN="$ROOT/bin"
LOG_DIR="/data/local/tmp/mobile-proxy-logs"
SUPERVISOR_LOG="$LOG_DIR/runtime-supervisor.log"
WATCHDOG_PID="$LOG_DIR/runtime-watchdog.pid"
echo "$$" > "$WATCHDOG_PID"
while true; do
  "$BIN/runtime-supervisor" --runtime-root "$ROOT" >> "$SUPERVISOR_LOG" 2>&1
  code="$?"
  date "+%Y-%m-%dT%H:%M:%S%z runtime_supervisor_exited code=$code; restarting" >> "$SUPERVISOR_LOG"
  sleep 2
done
' mobile-proxy-runtime-watchdog "$ROOT" >/dev/null 2>&1 &
log_boot "runtime_watchdog_spawned pid=$!"
