#!/usr/bin/env bash
# 运行公开评测：确定性 BM25 基线 + 指标/CI/切片 + 报告 JSON（原子写入，可复现）。
# 用法: scripts/evaluation/run.sh [WORK_DIR]  默认 <repo>/work
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK_DIR="${1:-$REPO_ROOT/work}"

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
$PY -m app.evaluation.public_runner --work-dir "$WORK_DIR" run
