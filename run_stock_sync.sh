#!/bin/bash
# 품고 재고 2h 수집 — 사무실 맥 launchd 에서 호출.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HOME/Library/Logs/even-inventory-sync.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "───── $(date '+%Y-%m-%d %H:%M:%S') 시작"

# 자격: 링 시스템과 같은 env 재사용 + 품고 토큰
[ -f "$HOME/.even_ring.env" ] && source "$HOME/.even_ring.env"
[ -f "$HOME/.even_inventory.env" ] && source "$HOME/.even_inventory.env"

VENV="$ROOT/.venv"
if [ ! -x "$VENV/bin/python3" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/python3" -m pip -q install --upgrade pip
  "$VENV/bin/python3" -m pip -q install -r "$ROOT/requirements.txt"
fi
"$VENV/bin/python3" "$ROOT/scripts/stock_sync.py"
echo "───── $(date '+%H:%M:%S') 종료 (exit $?)"
