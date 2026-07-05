from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_encoding_scan_module():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "encoding_scan.py"
    spec = importlib.util.spec_from_file_location("encoding_scan", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_text_files_are_utf8_without_common_mojibake() -> None:
    root = Path(__file__).resolve().parents[2]
    encoding_scan = _load_encoding_scan_module()

    assert encoding_scan.scan_encoding(root) == []
