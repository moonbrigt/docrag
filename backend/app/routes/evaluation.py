"""评测路由：运行内置评测集并返回指标报告（Spec §5 POST /evaluation/run）。

- config.profile 默认 "public_nist"：真实公开评测（NIST PDF 语料，见
  app/evaluation/public_runner.py）；PDF 未 prepare 时返回 409 并提示脚本。
- 保留 "synthetic_smoke"：旧 runner（内嵌 mock 语料 22 条）离线可复现。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

from app import db
from app.evaluation import public_runner, runner
from app.schemas import EvaluationReport, EvaluationRunRequest

router = APIRouter(prefix="/api/v1", tags=["evaluation"])

DEFAULT_PROFILE = "public_nist"


@router.post("/evaluation/run", response_model=EvaluationReport)
async def run_evaluation(req: EvaluationRunRequest):
    config = req.config or {}
    profile = config.get("profile", DEFAULT_PROFILE)
    if profile == "synthetic_smoke":
        report = runner.run(config=config)
    elif profile == DEFAULT_PROFILE:
        work_dir = public_runner.DEFAULT_WORK_DIR
        if not (work_dir / public_runner.CORPUS_FILE).exists():
            raise HTTPException(
                status_code=409,
                detail=(
                    "public_nist 评测尚未 prepare：请先运行 "
                    "scripts/evaluation/prepare.sh（下载并校验 NIST PDF、构建语料、"
                    "验证 gold evidence），再重新调用本接口。"
                ),
            )
        try:
            report = public_runner.build_report(work_dir)
        except ValueError as exc:  # 缓存语料与 manifest 版本不符等
            raise HTTPException(
                status_code=409,
                detail=f"public_nist 语料不可用（{exc}），请重新运行 scripts/evaluation/prepare.sh",
            ) from exc
    else:
        raise HTTPException(
            status_code=400,
            detail=f"未知 profile: {profile!r}（可用: {DEFAULT_PROFILE!r}, 'synthetic_smoke'）",
        )

    metrics = {
        **report["metrics"],
        "profile": profile,
        "provenance": report.get("provenance", {}),
        "ci": report.get("ci", {}),
        "corpus": report.get("corpus", {}),
        "baseline": report.get("baseline", {}),
        "ablation": report.get("ablation", {}),
    }
    config_json = json.dumps(config, ensure_ascii=False)
    metrics_json = json.dumps(metrics, ensure_ascii=False)

    def _insert(c):
        c.execute(
            "INSERT INTO evaluations (config_json, metrics_json) VALUES (?, ?)",
            (config_json, metrics_json),
        )

    await db.write(_insert)
    return EvaluationReport(
        metrics=metrics,
        per_query=report["per_query"],
        config=config,
    )
