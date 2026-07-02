param(
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$PublicBranch = "codex/public-release"
$PublicRoot = "63e4f4391d97dcb1b960d05d3936662f69746fa7"

$CurrentBranch = git branch --show-current
if ($CurrentBranch -ne $PublicBranch) {
  throw "Current branch is '$CurrentBranch'. Switch to '$PublicBranch' before public push."
}

git merge-base --is-ancestor $PublicRoot HEAD
if ($LASTEXITCODE -ne 0) {
  throw "HEAD is not based on the public root commit. Refusing to push possible private history."
}

python scripts/privacy_scan.py --ref HEAD
python scripts/privacy_scan.py

if (-not $SkipTests) {
  $Env:PYTHONPATH = "backend"
  python -m pytest backend/tests/test_api.py backend/tests/test_calculator.py -q -n auto
  Push-Location frontend
  try {
    npm run build
  } finally {
    Pop-Location
  }
}

git push --force-with-lease origin "$PublicBranch`:main"
