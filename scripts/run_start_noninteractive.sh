#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

today_in_shanghai() {
  TZ=Asia/Shanghai date +%F
}

has_today_data() {
  local python_bin
  if [[ -x "$PROJECT_ROOT/venv/bin/python" ]]; then
    python_bin="$PROJECT_ROOT/venv/bin/python"
  else
    python_bin="python3"
  fi

  "$python_bin" - <<'PY'
import sqlite3
from pathlib import Path
import os

today = os.environ["TODAY_STR"]
db_path = Path("data/news_data.db")
if not db_path.exists():
    raise SystemExit(1)

conn = sqlite3.connect(db_path)
try:
    cur = conn.execute(
        "SELECT COUNT(1) FROM news_articles WHERE collection_date = ?",
        (today,),
    )
    count = cur.fetchone()[0]
finally:
    conn.close()

raise SystemExit(0 if count > 0 else 1)
PY
}

TODAY_STR="$(today_in_shanghai)"
export TODAY_STR

if has_today_data; then
  responses=$'1\nn\nn\ny\n1\n1\nn\n'
else
  responses=$'1\ny\ny\n\ny\n1\n1\nn\n'
fi

printf '%s' "$responses" | bash "$PROJECT_ROOT/start.sh"
