#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
BIN="$ROOT/bin"
LOG_DIR="/data/local/tmp/mobile-proxy-logs"
BOOT_LOG="$LOG_DIR/runtime-boot.log"
SUPERVISOR_LOG="$LOG_DIR/runtime-supervisor.log"
WATCHDOG_PID="$LOG_DIR/runtime-watchdog.pid"
WATCHDOG_SCRIPT="$LOG_DIR/runtime-watchdog.sh"

export PATH="$BIN:$PATH"

mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

log_boot() {
  echo "$(timestamp) $*" >> "$BOOT_LOG"
}

watchdog_running() {
  if [ ! -f "$WATCHDOG_PID" ]; then
    return 1
  fi
  pid="$(cat "$WATCHDOG_PID" 2>/dev/null || true)"
  if [ -z "$pid" ] || [ ! -r "/proc/$pid/cmdline" ]; then
    return 1
  fi
  tr '\000' ' ' < "/proc/$pid/cmdline" | grep -q "$WATCHDOG_SCRIPT"
}

if [ ! -x "$BIN/runtime-supervisor" ]; then
  echo "missing runtime-supervisor binary: $BIN/runtime-supervisor" >&2
  exit 1
fi

if [ ! -f "$ROOT/config/host-daemon.json" ]; then
  echo "missing host-daemon config: $ROOT/config/host-daemon.json" >&2
  exit 1
fi

if watchdog_running; then
  log_boot "runtime_watchdog_already_running pid=$(cat "$WATCHDOG_PID")"
  exit 0
fi
rm -f "$WATCHDOG_PID"

cat > "$WATCHDOG_SCRIPT" <<'EOF'
#!/system/bin/sh
set -u
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
EOF
chmod 0700 "$WATCHDOG_SCRIPT"

nohup sh "$WATCHDOG_SCRIPT" "$ROOT" >/dev/null 2>&1 &
log_boot "runtime_watchdog_spawned pid=$!"
