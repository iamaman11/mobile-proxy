#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
RUNTIME_ROOT="/data/adb/mobile-proxy-node"
BIN="$ROOT/bin"
CFG="$ROOT/config"
LOG_DIR="$RUNTIME_ROOT/logs"
HOST_LOG="$LOG_DIR/host-daemon.log"
BOOT_LOG="$LOG_DIR/runtime-boot.log"

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
}

spawn_host_daemon() {
  nohup "$BIN/host-daemon" --config "$CFG/host-daemon.json" >> "$HOST_LOG" 2>&1 &
  log_boot "host_daemon_spawned pid=$!"
}

cellular_route_hint() {
  line="$(ip -4 route get 1.1.1.1 2>/dev/null | head -n 1 || true)"
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
  [ -n "$dev" ] || return 1
  case "$dev" in
    rmnet*|ccmni*|pdp*|wwan*)
      echo "$dev|$via"
      return 0
      ;;
  esac
  return 1
}

ensure_cellular_default_route() {
  hint="$(cellular_route_hint || true)"
  [ -n "$hint" ] || return 0
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

cellular_default_ready() {
  ip route show default 2>/dev/null | grep -Eq 'default .* rmnet[0-9]+'
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

kick_wireguard() {
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
      monkey -p com.wireguard.android -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
      sleep 2
    fi
    am broadcast --user 0 -a com.wireguard.android.action.SET_TUNNEL_UP --es tunnel WiGandroid >/dev/null 2>&1 || true
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

if needs_wireguard; then
  kick_wireguard &
  log_boot "wireguard_helper_started pid=$!"
fi

stop_runtime_procs
sleep 1

ensure_cellular_default_route || true
spawn_host_daemon
