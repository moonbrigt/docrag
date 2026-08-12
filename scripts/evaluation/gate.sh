#!/usr/bin/env bash
# 评测质量门禁：prepare → run → verify → 指标断言（CI 与本地通用）。
# 阈值基于 public_nist v1 的 observed 结果（BENCHMARK_CARD §3/§6.1），
# 用于防回归：检索/引用/确定性任一跌破阈值即非零退出。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT/backend"

VENV="${EVAL_VENV:-/tmp/docrag-gate-venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r requirements.txt -r requirements-dev.txt -r requirements-eval.txt
fi

echo "[gate] prepare"
"$VENV/bin/python" -m app.evaluation.public_runner prepare
echo "[gate] run"
"$VENV/bin/python" -m app.evaluation.public_runner run

REPORT="$ROOT/work/eval_reports/public_nist_report.json"
[ -f "$REPORT" ] || { echo "报告不存在: $REPORT"; exit 1; }

"$VENV/bin/python" - "$REPORT" <<'PYEOF'
import json, sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
m = report["metrics"]
gate = {
    "recall@5": (0.80, "召回@5 跌破门禁（observed 0.844）"),
    "mrr": (0.70, "MRR 跌破门禁（observed 0.747）"),
    "citation_recall": (0.80, "引用召回跌破门禁（observed 0.844）"),
}
fails = []
for key, (floor, why) in gate.items():
    v = m.get(key)
    if v is None:
        fails.append(f"{key}: 指标缺失")
    elif v < floor:
        fails.append(f"{key}={v:.4f} < {floor}；{why}")
if m.get("eligible", 0) < 15:
    fails.append(f"eligible={m.get('eligible')} < 15")
if not report.get("determinism", {}).get("verified"):
    fails.append("确定性自检未通过")
if fails:
    print("[gate] FAIL")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print(f"[gate] PASS recall@5={m.get('recall@5')} mrr={m.get('mrr')} "
      f"citation_recall={m.get('citation_recall')} eligible={m.get('eligible')}/{m.get('total')}")
PYEOF
