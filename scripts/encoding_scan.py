from __future__ import annotations

import argparse
import re
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "venv",
}

BINARY_EXTENSIONS = {
    ".db",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".map",
    ".pdf",
    ".png",
    ".sqlite",
    ".sqlite3",
    ".ttf",
    ".woff",
    ".woff2",
    ".zip",
}

TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

MOJIBAKE_PATTERNS = [
    "\ufffd",
    "\u951f\u65a4\u62f7",
    "\u951f",
    "\u65a4\u62f7",
    "\xef\xbf\xbd",
    "\xc3",
    "\xc2",
    "\xe2",
    "\u9225",
    "\u9286",
    "\u951b",
    "\u934f",
    "\u7ed7",
    "\u93c2",
    "\u7487",
    "\u9422",
    "\u5997",
    "\u5bf0",
    "\u7f02",
    "\u5bb8",
    "\u675e",
    "\u6fa7",
    "\u93b4",
    "\u6434",
    "\u59e3",
    "\u59af",
    "\u93cd",
    "\u7ecb",
    "\u95ab",
    "\u9428",
    "\u7039",
    "\u93c8",
    "\u54c4",
    "\u93c3",
]

MOJIBAKE_RE = re.compile("|".join(re.escape(item) for item in MOJIBAKE_PATTERNS))
PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")
MOJIBAKE_RUN_CHARS = "".join(
    chr(code)
    for code in [
        0x4E36,  # UTF-8 text decoded as GBK often starts with this family of characters.
        0x9359,
        0x935A,
        0x934A,
        0x9354,
        0x9429,
        0x93C8,
        0x7B5B,
        0x89D9,
        0x74A7,
        0x59AF,
        0x7F03,
        0x7A0B,
        0x6769,
        0x5B80,
        0x59DD,
        0x59E3,
        0x4EB2,
        0x52FC,
        0x7BFE,
        0x4F7A,
        0x72B2,
        0x7EF2,
        0x7BA1,
        0x9422,
        0x93C4,
        0x93C3,
        0x934F,
    ]
)
MOJIBAKE_RUN_RE = re.compile(f"[{re.escape(MOJIBAKE_RUN_CHARS)}]{{2,}}")


def iter_text_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in BINARY_EXTENSIONS or suffix not in TEXT_EXTENSIONS:
            continue
        files.append(path)
    return files


def scan_encoding(root: Path) -> list[str]:
    issues: list[str] = []
    for path in iter_text_files(root):
        relative = path.relative_to(root)
        data = path.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            issues.append(f"{relative}: invalid utf-8 at byte {exc.start}: {exc.reason}")
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if MOJIBAKE_RE.search(line) or PRIVATE_USE_RE.search(line) or MOJIBAKE_RUN_RE.search(line):
                issues.append(f"{relative}:{line_number}: suspicious mojibake text")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan text files for invalid UTF-8 and common mojibake markers.")
    parser.add_argument("--root", default=".", help="Repository root to scan.")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    issues = scan_encoding(root)
    for issue in issues:
        print(issue)
    if issues:
        print(f"encoding scan failed: {len(issues)} issue(s)")
        return 1
    print("encoding scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
