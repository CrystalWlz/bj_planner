param(
  [ValidateSet("quick", "api", "contracts", "slow", "encoding", "full")]
  [string]$Layer = "quick"
)

$ErrorActionPreference = "Stop"
$Env:PYTHONPATH = "backend"
$Env:PYTHONIOENCODING = "utf-8"

switch ($Layer) {
  "quick" {
    python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py backend/tests/test_encoding_scan.py -q -m "not slow and not integration and not frontend_contract and not architecture"
  }
  "api" {
    python -m pytest backend/tests/test_api.py -q -m "integration and not slow"
  }
  "contracts" {
    python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q -m "frontend_contract or architecture"
  }
  "slow" {
    python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q -m "slow"
  }
  "encoding" {
    python -m pytest backend/tests/test_encoding_scan.py -q
    python scripts/encoding_scan.py
  }
  "full" {
    python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q -n auto
  }
}
