#!/usr/bin/env bash
# 下载两份 NIST PDF 并做 SHA-256 + 尺寸校验（fail-closed）。
# 用法: scripts/evaluation/download.sh [WORK_DIR]  默认 <repo>/work
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK_DIR="${1:-$REPO_ROOT/work}"
export WORK_DIR
mkdir -p "$WORK_DIR/source_cache"

# Python 选择：VENV_PY 环境变量 > 后端 .venv（Linux/WSL） > .venv/Scripts（Windows） > python3
if [ -n "${VENV_PY:-}" ]; then
    PY="$VENV_PY"
elif [ -x "$REPO_ROOT/backend/.venv/bin/python" ]; then
    PY="$REPO_ROOT/backend/.venv/bin/python"
elif [ -x "$REPO_ROOT/backend/.venv/Scripts/python.exe" ]; then
    PY="$REPO_ROOT/backend/.venv/Scripts/python.exe"
else
    PY="python3"
fi
cd "$REPO_ROOT/backend"

# 通过 public_dataset.ensure_sources 复用 manifest 中的 DOI/hash/尺寸（单一事实来源）
$PY - <<'PYEOF'
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")
from app.evaluation import public_dataset

paths = public_dataset.ensure_sources(Path(os.environ["WORK_DIR"]) / "source_cache")
for doc_id, p in paths.items():
    print(f"OK {doc_id}: {p} ({p.stat().st_size} bytes)")
PYEOF
