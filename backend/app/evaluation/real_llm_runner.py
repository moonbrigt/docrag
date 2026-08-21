"""真实 LLM 评测：mock 检索 + 真实 LLM 生成 + 质量评分。

目的：量化 LLM 在 RAG 管线中的真实输出质量（不是抽取式答案器）。
复用 public_runner 的 mock 检索链路，只替换生成环节为真实 LLM。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.core import llm as llm_mod
from app.core import runtime_config
from app.evaluation import ablation, eval_metrics, public_dataset
from app.evaluation.public_runner import (
    DEFAULT_WORK_DIR,
    KS,
    RERANK_TOP_K,
    load_corpus,
    run_ablation,
)

# 生成式答案的上下文片段数
CTX_CHUNKS = 3

_SYSTEM_PROMPT = (
    "你是一个精确的事实性问答助手。只能依据给定的文档片段回答；"
    "如果文档片段不足以回答问题，只输出 <no-answer>。"
    "用提问所用的语言，直接、简洁地回答，不要多余解释。"
)

_NO_ANSWER_TOKENS = {"<no-answer>", "no-answer", "cannot answer",
                     "无法回答", "没有足够信息", "文档中没有相关信息"}


def _extract_final_answer(text: str) -> str:
    """从 reasoning 模型输出中提取最终答案（最后一段非推理文本）。"""
    if not text:
        return ""
    # 推理模型的输出模式：推理步骤 + 最终答案
    # 最终答案通常是最后一段独立文本（不含 ** 编号标记）
    lines = text.strip().split("\n")
    # 找最后一个非空、非推理步骤的行
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        # 跳过推理步骤行（以数字+** 开头，或含特定推理关键词）
        if line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.")):
            continue
        if "**" in line and ("分析" in line or "识别" in line or "扫描" in line or "综合" in line or "构建" in line):
            continue
        return line
    # fallback：整段文本
    return text.strip()


def _is_no_answer(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(tok in t for tok in _NO_ANSWER_TOKENS)


async def _consume_stream(stream) -> str:
    parts = []
    async for piece in stream:
        parts.append(piece)
    return "".join(parts)


def _predict_with_llm(
    corpus: list[dict],
    questions: list[dict],
    retriever,
    reranker,
    llm_client: llm_mod.LLMClient,
) -> list[dict]:
    """检索（mock）→ 重排（mock）→ LLM 生成式答案。"""
    async def _gen(q: dict, top: list[dict], top_chunks: list[dict]) -> dict:
        if not top_chunks:
            return {
                "query_id": q["id"], "retrieved": [],
                "citations": [], "answer": "", "no_answer": True,
            }

        context = "\n".join(
            f"[{i+1}] {c['text'][:4000]}" for i, c in enumerate(top_chunks[:CTX_CHUNKS])
        )
        user_msg = f"文档片段：\n{context}\n\n问题：{q['query']}\n\n请给出答案。"

        try:
            raw = await _consume_stream(
                llm_client.stream(_SYSTEM_PROMPT, user_msg)
            )
        except (RuntimeError, OSError, ValueError) as exc:
            raw = f"<LLM_ERROR: {exc}>"

        # reasoning 模型输出含推理过程，提取最后一段作为最终答案
        ans = _extract_final_answer(raw)
        no_answer = _is_no_answer(ans)
        citations = (
            []
            if no_answer
            else [
                {"document_id": c["document_id"], "physical_page": c["physical_page"]}
                for c in top[:RERANK_TOP_K]
            ]
        )
        return {
            "query_id": q["id"], "retrieved": [
                {"document_id": t["document_id"], "physical_page": t["physical_page"],
                 "chunk_index": t["chunk_index"], "score": t.get("score", 0.0)}
                for t in top
            ],
            "citations": citations,
            "answer": "" if no_answer else ans,
            "no_answer": no_answer,
        }

    async def _run_all():
        results = []
        for q in questions:
            candidates = retriever.search(q["query"], RERANK_TOP_K * 3)
            if candidates:
                scores = reranker.rerank(q["query"], candidates, RERANK_TOP_K)
                top = [
                    {**c, "score": s}
                    for c, s in zip(candidates, scores)
                ][:RERANK_TOP_K]
            else:
                top = []
            top_chunks = [corpus[t["chunk_index"]] for t in top]
            r = await _gen(q, top, top_chunks)
            results.append(r)
        return results

    return asyncio.run(_run_all())


def build_report(work_dir: Path, ks=KS) -> dict:
    data = load_corpus(work_dir)
    manifest = public_dataset.load_manifest()
    questions = public_dataset.load_questions()

    # 用 BM25 检索（与 mock 基线同口径）+ 词法重排
    retriever, reranker, _ = ablation.VARIANT_SPECS["bm25"](data["corpus"])

    # LLM 客户端
    runtime_config.load_runtime_config()
    client = llm_mod.LLMClient()
    backend, ready = client.status()
    if not ready:
        raise RuntimeError(f"LLM 未就绪（{backend}），请先在设置页配置真实 LLM 后端")

    predictions = _predict_with_llm(data["corpus"], questions, retriever, reranker, client)
    result = eval_metrics.evaluate(predictions, questions, ks)

    # 消融对比（与 mock 基线同口径）
    ablation_predictions = run_ablation(data["corpus"], questions)
    ablation_table = {}
    for variant, preds in ablation_predictions.items():
        res = eval_metrics.evaluate(preds, questions, ks)
        ablation_table[variant] = {
            "name": ablation.VARIANT_SPECS[variant](data["corpus"])[2],
            "metrics": {
                k: res["metrics"][k]
                for k in ("recall@1", "recall@3", "recall@5", "mrr", "ndcg@5",
                          "citation_recall", "citation_page_precision",
                          "answer_em", "answer_f1", "unanswerable_correct")
            },
        }

    return {
        "profile": manifest["profile"],
        "manifest": {
            "id": manifest["id"], "name": manifest["name"],
            "version": manifest["version"],
            "n_questions": manifest["n_questions"],
            "answerable_count": manifest["answerable_count"],
            "unanswerable_count": manifest["unanswerable_count"],
        },
        "corpus": {
            "documents": data["documents"], "n_chunks": data["n_chunks"],
            "source_cache": str(work_dir / "source_cache"),
        },
        "pipeline": {
            "name": f"BM25 + lexical-rerank + {backend}:{llm_mod.effective_llm_config()['model']} (generative)",
            "ks": list(ks), "rerank_top_k": RERANK_TOP_K,
            "ctx_chunks": CTX_CHUNKS,
            "deterministic": False,
        },
        "metrics": result["metrics"],
        "ci": result["ci"],
        "slices": result["slices"],
        "ablation": ablation_table,
        "per_query": result["per_query"],
        "predictions": predictions,
        "provenance": {
            "docling": "NOT_RUN",
            "embedding_bge_m3": "NOT_RUN",
            "reranker_bge": "NOT_RUN",
            "llm": "RUN",
            "llm_backend": backend,
            "llm_model": llm_mod.effective_llm_config()["model"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    runtime_config.load_runtime_config()
    parser = argparse.ArgumentParser(
        prog="public_real_llm",
        description="NIST 公开评测：mock 检索 + 真实 LLM 生成式答案",
    )
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument(
        "--out", default="public_nist_real_llm_report.json",
        help="报告输出路径（相对 work-dir 或绝对路径）",
    )
    args = parser.parse_args(argv)
    work_dir = Path(args.work_dir)
    report = build_report(work_dir)
    report["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = Path(args.out)
    if not out.is_absolute():
        out = work_dir / out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out)
    m = report["metrics"]
    print(
        f"real-llm OK: recall@5={m['recall@5']:.3f} mrr={m['mrr']:.3f} "
        f"answer_em={m['answer_em']:.3f} answer_f1={m['answer_f1']:.3f} "
        f"unanswerable={m.get('unanswerable_correct', '?')} | "
        f"eligible={m['eligible']}/{m['total']} report -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
