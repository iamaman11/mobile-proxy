#!/usr/bin/env python3
"""Classify a Git diff as documentation-only or code-affecting."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")


def is_code_path(path: str) -> bool:
    return not path.lower().endswith(".md")


def changed_paths(base: str, head: str) -> list[str]:
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        return ["unknown-input"]
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{base}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
    )
    if present.returncode != 0:
        return ["missing-base"]
    output = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRTUXB", base, head],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    paths = [line for line in output.splitlines() if line]
    return paths or ["empty-diff"]


def requires_code_gate(paths: Sequence[str]) -> bool:
    return any(is_code_path(path) for path in paths)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    code = requires_code_gate(changed_paths(args.base, args.head))
    with args.github_output.open("a", encoding="utf-8") as output:
        output.write(f"code={str(code).lower()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
