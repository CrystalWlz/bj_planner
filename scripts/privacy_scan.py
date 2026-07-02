from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path


BLOCKED_PATH_PATTERNS = [
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pyc",
    ".env",
    ".env.*",
    "backend/.venv/*",
    "backend/**/__pycache__/*",
    "backend/.pytest_cache/*",
    "frontend/node_modules/*",
    "frontend/dist/*",
    "frontend/output/*",
    "frontend/*.tsbuildinfo",
]

PRIVATE_TEXT_PATTERNS = [
    "2001" + "-01",
    "1998" + "-01",
    "1975" + "-12",
    "\u52a9\u5b66\u8d37\u6b3e " + "20000",
    "\u52a9\u5b66\u8d37\u6b3e " + "25000",
    "\u5b9d",
    "\u59bb\u5b50",
    "\u6211\u65b9",
    "\u5b9d\u65b9",
    "52" + "000",
    "19" + "000",
    "240" + "000",
    "62" + "00",
    "23" + "00",
    "20" + "89",
    "\u4e94\u73af\u5185\u901a\u52e4\u6539\u5584",
    "\u6d77\u6dc0",
    "760" + "0000",
    "280" + "0000",
    "360" + "0000",
    "\u7236\u6bcd\u5bb6\u5ead\u82b1\u9500",
    "\u516c\u52a1\u5458",
    "2031" + "-07",
    "2031" + "-06",
    "remaining_months: " + "184",
    "remaining_months=" + "184",
]


def run_git(args: list[str]) -> bytes:
    result = subprocess.run(["git", *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout


def list_files(ref: str | None) -> list[str]:
    if ref:
        raw = run_git(["ls-tree", "-r", "-z", "--name-only", ref])
    else:
        raw = run_git(["ls-files", "-z"])
    return [item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item]


def read_file(path: str, ref: str | None) -> str | None:
    try:
        if ref:
            raw = run_git(["show", f"{ref}:{path}"])
        else:
            raw = Path(path).read_bytes()
    except (subprocess.CalledProcessError, OSError):
        return None

    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="ignore")


def is_blocked_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in BLOCKED_PATH_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked files for private household data before public push.")
    parser.add_argument("--ref", help="Git ref/commit to scan. Defaults to tracked working tree files.")
    args = parser.parse_args()

    findings: list[str] = []
    for path in list_files(args.ref):
        if is_blocked_path(path):
            findings.append(f"blocked path: {path}")
            continue

        content = read_file(path, args.ref)
        if content is None:
            continue
        for line_no, line in enumerate(content.splitlines(), start=1):
            for pattern in PRIVATE_TEXT_PATTERNS:
                if pattern in line:
                    findings.append(f"sensitive text: {path}:{line_no}: {pattern}")

    if findings:
        print("Privacy scan failed. Review these findings before pushing:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    target = args.ref or "tracked working tree"
    print(f"Privacy scan passed for {target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
