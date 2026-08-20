"""评测路由：运行内置评测集并返回指标报告（Spec §5 POST /evaluation/run）。

- config.profile 默认 "public_nist"：真实公开评测（NIST PDF 语料，见
  app/evaluation/public_runner.py）；PDF 未 prepare 时返回 409 并提示脚本。
- 保留 "synthetic_smoke"：旧 runner（内嵌 mock 语料 22 条）离线可复现。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app import db
from app.evaluation import public_real, public_runner, runner
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
            # 真实完整管线：bge-m3 嵌入 + bge-reranker-v2-m3 重排 + Ollama 生成式答案
            report = await run_in_threadpool(public_real.build_report, work_dir)
        except AssertionError as exc:  # mock 后端未关闭 / 真实模型未加载
            raise HTTPException(
                status_code=503,
                detail=(
                    "public_nist 评测要求真实完整管线，请先在设置页关闭 mock、启用 "
                    "bge-m3 / bge-reranker-v2-m3 / Ollama，再重试"
                ),
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"public_nist 真实管线评测失败：{exc}"
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
