#!/system/bin/sh
set -eu

ROOT="/data/adb/mobile-proxy-node/current"
BIN="$ROOT/bin"
CFG="$ROOT/config"

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

pkill -f "$BIN/host-daemon" || true
pkill -f "$BIN/sing-box" || true
sleep 1

nohup "$BIN/host-daemon" --config "$CFG/host-daemon.json" >/dev/null 2>&1 &
