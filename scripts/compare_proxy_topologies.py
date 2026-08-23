#!/usr/bin/env python3
"""A/B-test native and VM-terminated proxy paths, then restore production routing."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


MODES = ("reverse-tunnel", "server-termination")
PRODUCTION_MODE = "server-termination"


def switch_command(args: argparse.Namespace, mode: str, output: Path) -> list[str]:
    return [
        "python3",
        str(Path(__file__).with_name("switch_vm_proxy_transport.py")),
        "--mode", mode,
        "--project", args.project,
        "--zone", args.zone,
        "--instance", args.instance,
        "--ssh-user", args.ssh_user,
        "--ssh-key", args.ssh_key,
        "--output", str(output),
    ]


def run_probe(proxy: str, credentials: str, url: str, timeout: int) -> dict[str, object]:
    if any(character in credentials for character in "\r\n\0"):
        raise ValueError("proxy credentials contain an unsupported control character")
    escaped_credentials = credentials.replace("\\", "\\\\").replace('"', '\\"')
    curl_config = f'proxy-user = "{escaped_credentials}"\n'
    started = time.monotonic()
    command = [
        "curl", "--fail", "--silent", "--show-error",
        "--max-time", str(timeout), "--config", "-",
    ]
    if proxy.startswith("socks5h://"):
        command.extend(["--socks5-hostname", proxy.removeprefix("socks5h://")])
    else:
        command.extend(["--proxy", proxy])
    command.append(url)
    completed = subprocess.run(
        command,
        input=curl_config,
        capture_output=True,
        text=True,
    )
    duration_ms = round((time.monotonic() - started) * 1000)
    public_ip = completed.stdout.strip() if completed.returncode == 0 else None
    return {
        "ok": completed.returncode == 0 and bool(public_ip),
        "duration_ms": duration_ms,
        "public_ip": public_ip,
        "exit_code": completed.returncode,
    }


def summarize(results: list[dict[str, object]]) -> dict[str, object]:
    durations = [int(item["duration_ms"]) for item in results if item["ok"]]
    failure_exit_codes = Counter(
        str(item["exit_code"]) for item in results if not item["ok"]
    )
    return {
        "attempts": len(results),
        "successes": len(durations),
        "success_rate": len(durations) / len(results) if results else 0.0,
        "median_ms": round(statistics.median(durations)) if durations else None,
        "max_ms": max(durations) if durations else None,
        "public_ips": sorted({str(item["public_ip"]) for item in results if item["ok"]}),
        "failure_exit_codes": dict(sorted(failure_exit_codes.items())),
    }


def probe_mode(args: argparse.Namespace, credentials: str) -> dict[str, object]:
    surfaces = {
        "mixed_http_1080": f"http://{args.proxy_host}:1080",
        "mixed_socks_1080": f"socks5h://{args.proxy_host}:1080",
        "socks_1081": f"socks5h://{args.proxy_host}:1081",
        "http_3128": f"http://{args.proxy_host}:3128",
    }
    report: dict[str, object] = {}
    for name, proxy in surfaces.items():
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            results = list(executor.map(
                lambda _: run_probe(proxy, credentials, args.probe_url, args.timeout),
                range(args.attempts),
            ))
        report[name] = summarize(results)
        time.sleep(args.surface_pause_ms / 1000)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--ssh-user", required=True)
    parser.add_argument("--ssh-key", required=True)
    parser.add_argument("--proxy-host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=25)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--settle-secs", type=int, default=4)
    parser.add_argument("--surface-pause-ms", type=int, default=500)
    parser.add_argument("--probe-url", default="https://api.ipify.org")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.attempts < 1 or args.concurrency < 1 or args.concurrency > args.attempts:
        raise SystemExit("attempts/concurrency values are invalid")
    if not 0 <= args.settle_secs <= 30 or not 0 <= args.surface_pause_ms <= 10_000:
        raise SystemExit("settle/pause values are invalid")
    username = os.environ.get("MOBILE_PROXY_RELAY_USER", "")
    password = os.environ.get("MOBILE_PROXY_RELAY_PASSWORD", "")
    if not username or not password:
        raise SystemExit("MOBILE_PROXY_RELAY_USER and MOBILE_PROXY_RELAY_PASSWORD are required")
    credentials = f"{username}:{password}"
    report: dict[str, object] = {"format_version": 1, "modes": {}}
    with tempfile.TemporaryDirectory(prefix="mobile-proxy-topology-") as raw_temp:
        temp = Path(raw_temp)
        try:
            for mode in MODES:
                subprocess.run(switch_command(args, mode, temp / f"switch-{mode}.json"), check=True)
                time.sleep(args.settle_secs)
                report["modes"][mode] = probe_mode(args, credentials)
        finally:
            subprocess.run(
                switch_command(args, PRODUCTION_MODE, temp / "switch-restored.json"),
                check=True,
            )
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
