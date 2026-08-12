#!/usr/bin/env bash
# 准备公开评测：下载+校验 PDF → 提取语料（每页一个 chunk）→ 验证全部 gold evidence。
# 用法: scripts/evaluation/prepare.sh [WORK_DIR]  默认 <repo>/work
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
$PY -m app.evaluation.public_runner --work-dir "$WORK_DIR" prepare
