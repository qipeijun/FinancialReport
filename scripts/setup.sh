#!/usr/bin/env bash
set -euo pipefail

echo "==> Detecting Python..."
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v py >/dev/null 2>&1; then
  PY=py
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python not found. Please install Python 3.10+." >&2
  exit 1
fi

echo "==> Python: $($PY --version)"

echo "==> Creating venv (.venv)"
$PY -m venv .venv
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate

echo "==> Upgrading pip"
pip install --upgrade pip

echo "==> Installing requirements"
pip install -r requirements.txt

echo "==> Creating config/config.yml if missing"
mkdir -p config
if [ ! -f config/config.yml ]; then
  cp config/config.example.yml config/config.yml || true
  echo "Created config/config.yml from example. Please edit your API key."
fi

echo "==> Setup completed. You can run:"
echo "    source .venv/bin/activate   # or .venv\\Scripts\\activate on Windows"
echo "    python3 scripts/interactive_runner.py"


