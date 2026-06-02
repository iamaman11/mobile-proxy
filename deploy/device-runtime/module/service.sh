#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
RUNTIME_ROOT="/data/adb/mobile-proxy-node"
BIN="$ROOT/bin"
CFG="$ROOT/config"
LOG_DIR="/data/local/tmp/mobile-proxy-logs"
HOST_LOG="$LOG_DIR/host-daemon.log"
BOOT_LOG="$LOG_DIR/runtime-boot.log"
ROUTE_GUARD_PID_FILE="$LOG_DIR/route-guard.pid"
WG_PACKAGE="com.wireguard.android"
WG_MAIN_ACTIVITY="com.wireguard.android/.activity.MainActivity"
WG_BROADCAST_UP="com.wireguard.android.action.SET_TUNNEL_UP"
WG_TUNNEL_NAME="${WG_TUNNEL_NAME:-WiGandroid}"
WG_UI_DUMP="/data/local/tmp/mobile-proxy-wg-ui.xml"

# Ensure runtime helper binaries/shims (for example curl shim on Android) are discoverable.
export PATH="$BIN:$PATH"

mkdir -p "$LOG_DIR"

timestamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

log_boot() {
  echo "$(timestamp) $*" >> "$BOOT_LOG"
}

stop_runtime_procs() {
  pkill -f "$RUNTIME_ROOT/current/bin/host-daemon" || true
  pkill -f "$RUNTIME_ROOT/current/bin/sing-box" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/host-daemon" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/sing-box" || true
  pkill -f "$RUNTIME_ROOT/current/service.sh --route-guard" || true
  pkill -f "$RUNTIME_ROOT/releases/.*/service.sh --route-guard" || true
  if [ -f "$ROUTE_GUARD_PID_FILE" ]; then
    rg_pid="$(cat "$ROUTE_GUARD_PID_FILE" 2>/dev/null || true)"
    if [ -n "$rg_pid" ]; then
      kill "$rg_pid" >/dev/null 2>&1 || true
    fi
    rm -f "$ROUTE_GUARD_PID_FILE" >/dev/null 2>&1 || true
  fi
}

spawn_host_daemon() {
  nohup "$BIN/host-daemon" --config "$CFG/host-daemon.json" >> "$HOST_LOG" 2>&1 &
  log_boot "host_daemon_spawned pid=$!"
}

cellular_route_hint() {
  # Fast path: if main table already resolves, use it.
  line="$(ip -4 route get 1.1.1.1 2>/dev/null | head -n 1 || true)"
  dev=""
  via=""
  if [ -n "$line" ]; then
    set -- $line
    while [ "$#" -gt 1 ]; do
      case "$1" in
        dev) dev="$2" ;;
        via) via="$2" ;;
      esac
      shift
    done
    case "$dev" in
      rmnet*|ccmni*|pdp*|wwan*)
        echo "$dev|$via"
        return 0
        ;;
    esac
  fi

  # Fallback: read per-interface routing tables when main default is missing.
  for candidate in $(ip -o link show 2>/dev/null | sed -n 's/^[0-9][0-9]*: \([^:]*\):.*/\1/p' | grep -E '^(rmnet|ccmni|pdp|wwan)'); do
    line="$(ip -4 route show table all 2>/dev/null | grep -E "^default .* dev $candidate( |$)" | head -n 1 || true)"
    [ -n "$line" ] || continue
    dev=""
    via=""
    set -- $line
    while [ "$#" -gt 1 ]; do
      case "$1" in
        dev) dev="$2" ;;
        via) via="$2" ;;
      esac
      shift
    done
    [ -n "$dev" ] || dev="$candidate"
    case "$dev" in
      rmnet*|ccmni*|pdp*|wwan*)
        echo "$dev|$via"
        return 0
        ;;
    esac
  done

  return 1
}

ensure_cellular_default_route() {
  hint="$(cellular_route_hint || true)"
  [ -n "$hint" ] || return 1
  dev="${hint%%|*}"
  via="${hint#*|}"
  if ip route show default 2>/dev/null | grep -Eq "default .* dev $dev( |$)"; then
    return 0
  fi
  if [ -n "$via" ]; then
    ip route replace default via "$via" dev "$dev" >/dev/null 2>&1 || return 1
    log_boot "default_route_repaired dev=$dev via=$via"
  else
    ip route replace default dev "$dev" >/dev/null 2>&1 || return 1
    log_boot "default_route_repaired dev=$dev"
  fi
  return 0
}

route_guard_loop() {
  while true; do
    if ! main_cellular_default_ready; then
      if ensure_cellular_default_route; then
        log_boot "default_route_guard_repaired"
      fi
    fi
    sleep 5
  done
}

spawn_route_guard() {
  # Keep route guard as a background worker in this process; avoids SELinux issues
  # seen when recursively executing service.sh through /data/adb/current symlinks.
  route_guard_loop >/dev/null 2>&1 &
  echo "$!" > "$ROUTE_GUARD_PID_FILE"
  log_boot "route_guard_started pid=$!"
}

cellular_default_ready() {
  ip -4 route show table all 2>/dev/null | grep -Eq '^default .* dev (rmnet|ccmni|pdp|wwan)[^ ]*'
}

main_cellular_default_ready() {
  ip route show default 2>/dev/null | grep -Eq '^default .* dev (rmnet|ccmni|pdp|wwan)[^ ]*'
}

tun0_ready() {
  ip -4 addr show tun0 2>/dev/null | grep -q 'inet '
}

needs_wireguard() {
  if tr -d '\r\n\t ' < "$CFG/host-daemon.json" | grep -q '"wireguard":{"enabled":true'; then
    return 0
  fi
  if [ -f "$CFG/sing-box.json" ] && grep -q '"listen"[[:space:]]*:[[:space:]]*"10\.66\.66\.2"' "$CFG/sing-box.json"; then
    return 0
  fi
  return 1
}

configure_wireguard_always_on() {
  settings put secure always_on_vpn_app "$WG_PACKAGE" >/dev/null 2>&1 || true
  settings put secure always_on_vpn_lockdown 0 >/dev/null 2>&1 || true
}

wireguard_ui_dump() {
  uiautomator dump "$WG_UI_DUMP" >/dev/null 2>&1 || return 1
  [ -f "$WG_UI_DUMP" ] || return 1
  return 0
}

wireguard_switch_checked() {
  wireguard_ui_dump || return 1
  line="$(grep 'resource-id="com.wireguard.android:id/tunnel_switch"' "$WG_UI_DUMP" | head -n 1 || true)"
  [ -n "$line" ] || return 1
  if echo "$line" | grep -q 'checked="true"'; then
    return 0
  fi
  return 1
}

wireguard_toggle_via_ui() {
  input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true
  wm dismiss-keyguard >/dev/null 2>&1 || true
  am start -n "$WG_MAIN_ACTIVITY" >/dev/null 2>&1 || true
  sleep 2
  wireguard_ui_dump || return 1
  line="$(grep 'resource-id="com.wireguard.android:id/tunnel_switch"' "$WG_UI_DUMP" | head -n 1 || true)"
  [ -n "$line" ] || return 1
  if echo "$line" | grep -q 'checked="true"'; then
    return 0
  fi
  bounds="$(echo "$line" | sed -n 's/.*bounds="\(\[[0-9]\+,[0-9]\+\]\[[0-9]\+,[0-9]\+\]\)".*/\1/p')"
  [ -n "$bounds" ] || return 1
  left="$(echo "$bounds" | sed -n 's/\[\([0-9]\+\),\([0-9]\+\)\]\[\([0-9]\+\),\([0-9]\+\)\]/\1/p')"
  top="$(echo "$bounds" | sed -n 's/\[\([0-9]\+\),\([0-9]\+\)\]\[\([0-9]\+\),\([0-9]\+\)\]/\2/p')"
  right="$(echo "$bounds" | sed -n 's/\[\([0-9]\+\),\([0-9]\+\)\]\[\([0-9]\+\),\([0-9]\+\)\]/\3/p')"
  bottom="$(echo "$bounds" | sed -n 's/\[\([0-9]\+\),\([0-9]\+\)\]\[\([0-9]\+\),\([0-9]\+\)\]/\4/p')"
  [ -n "$left" ] && [ -n "$top" ] && [ -n "$right" ] && [ -n "$bottom" ] || return 1
  x=$(( (left + right) / 2 ))
  y=$(( (top + bottom) / 2 ))
  input tap "$x" "$y" >/dev/null 2>&1 || true
  sleep 2
  wireguard_switch_checked
}

wireguard_broadcast_up() {
  am broadcast --user 0 --receiver-foreground -a "$WG_BROADCAST_UP" --es tunnel "$WG_TUNNEL_NAME" >/dev/null 2>&1 || true
}

kick_wireguard() {
  configure_wireguard_always_on
  attempt=0
  while [ "$attempt" -lt 12 ]; do
    if tun0_ready; then
      log_boot "tun0_ready attempt=$attempt"
      return 0
    fi
    attempt=$((attempt + 1))
    if cellular_default_ready; then
      route_ready=yes
    else
      route_ready=no
    fi
    log_boot "wireguard_kick attempt=$attempt cellular_default_ready=$route_ready"
    if [ "$attempt" -eq 1 ] || [ "$route_ready" = "yes" ] || [ $((attempt % 3)) -eq 0 ]; then
      monkey -p "$WG_PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
      sleep 2
    fi
    wireguard_broadcast_up
    if ! tun0_ready; then
      if wireguard_toggle_via_ui; then
        log_boot "wireguard_ui_toggle_ok attempt=$attempt"
      else
        log_boot "wireguard_ui_toggle_skipped attempt=$attempt"
      fi
    fi
    probe=0
    while [ "$probe" -lt 3 ]; do
      if tun0_ready; then
        log_boot "tun0_ready attempt=$attempt"
        return 0
      fi
      sleep 2
      probe=$((probe + 1))
    done
  done
  log_boot "tun0_not_ready after_attempts=$attempt"
  return 1
}

if [ ! -x "$BIN/host-daemon" ]; then
  echo "missing host-daemon binary: $BIN/host-daemon" >&2
  exit 1
fi

if [ ! -x "$BIN/sing-box" ]; then
  echo "missing sing-box binary: $BIN/sing-box" >&2
  exit 1
fi

if [ ! -f "$CFG/host-daemon.json" ]; then
  echo "missing host-daemon config: $CFG/host-daemon.json" >&2
  exit 1
fi

if [ "${1:-}" = "--route-guard" ]; then
  route_guard_loop
  exit 0
fi

if needs_wireguard; then
  kick_wireguard &
  log_boot "wireguard_helper_started pid=$!"
fi

stop_runtime_procs
sleep 1

spawn_route_guard
ensure_cellular_default_route || true
spawn_host_daemon
