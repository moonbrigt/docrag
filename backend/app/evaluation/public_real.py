"""真实完整管线公开评测：bge-m3 嵌入 → bge-reranker 重排 → 生成式答案（Ollama）。

- 复用产品真实组件（app.core 的 EmbeddingService / RerankService / LLMClient），
  因此评测所用嵌入/重排/生成与 Chat 端到端为同一代码路径、同一权重快照。
  自检：嵌入向量与 Chat 同源（同 EmbeddingService + 同 HF 缓存快照），provenance 记录
  解析后的真实模型路径，可复核。
- 不修改确定性基线（public_runner）的字节可复现契约。
- 检索：纯 bge-m3 dense（L2 归一化余弦）→ 重排取 top_k → LLM 生成式答案。
- 每题保留逐条指标（per_query），概览聚合与明细同源（eval_metrics.evaluate），可逐条核对。

用法（容器内，真实后端需显式关 mock）：
  RAG_EMBED_MOCK=false RAG_RERANK_MOCK=false RAG_LLM_MOCK=false RAG_LLM_MODEL=qwen3:4b \
  python -m app.evaluation.public_real [--work-dir work] [--out public_nist_real_run.json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.core import accelerator, embeddings, llm, reranker, runtime_config
from app.evaluation import eval_metrics, public_dataset
from app.evaluation.public_runner import (
    DEFAULT_REPORT,
    DEFAULT_WORK_DIR,
    RERANK_TOP_K,
    KS,
    load_corpus,
)
from app.services import index_service, rerank_service

NO_ANSWER_TOKEN = "<no-answer>"
RETRIEVE_CANDIDATES = RERANK_TOP_K * 3  # 重排前的候选数
CTX_CHUNKS = 3  # 送入 LLM 的上下文片段数
PROVENANCE_RUN = {
    "docling": "NOT_RUN",  # 本评测语料为 pypdf 预提取（public_dataset），不走 docling
    "embedding_bge_m3": "RUN",
    "reranker_bge": "RUN",
    "llm": "RUN",
}


# ---------------- 检索 / 生成 ----------------

def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float32)
    if mat.ndim == 1:
        norm = float(np.linalg.norm(mat))
        return mat / norm if norm else mat
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


async def _consume_stream(stream) -> str:
    parts = []
    async for piece in stream:
        parts.append(piece)
    return "".join(parts)


class RealDenseRetriever:
    """纯 bge-m3 dense 检索：语料向量一次编码，L2 归一化后按余弦 top-k。"""

    def __init__(self, corpus: list[dict], emb: embeddings.EmbeddingService) -> None:
        self.corpus = corpus
        self.emb = emb
        dense, _ = emb.embed([c["text"] for c in corpus])
        self._vectors = _l2_normalize(np.asarray(dense, dtype=np.float32))

    def search(self, query: str, k: int) -> list[dict]:
        qv = _l2_normalize(np.asarray(self.emb.embed_one(query)[0], dtype=np.float32))
        scores = self._vectors @ qv  # 行已归一化 → 余弦
        order = np.argsort(-scores)
        out: list[dict] = []
        for idx in order:
            s = float(scores[idx])
            if s <= 0.0:
                break  # 零/负信号不冒充候选
            c = self.corpus[int(idx)]
            out.append(
                {"chunk_index": int(idx), "document_id": c["document_id"],
                 "physical_page": c["physical_page"], "score": s}
            )
            if len(out) >= k:
                break
        return out


_SYSTEM_PROMPT = (
    "你是一个精确的事实性问答助手。只能依据给定的文档片段回答；"
    "如果文档片段不足以回答问题，只输出 <no-answer>。"
    "用提问所用的语言，直接、简洁地回答，不要多余解释。"
)


def _is_no_answer(text: str) -> bool:
    t = (text or "").strip().lower()
    return NO_ANSWER_TOKEN in t or t in ("no-answer", "cannot answer", "无法回答",
                                         "没有足够信息", "文档中没有相关信息")


async def _generate(question: str, chunks: list[dict], llm_client) -> str:
    context = "\n".join(
        f"[{i + 1}] {c['text'][:4000]}" for i, c in enumerate(chunks[:CTX_CHUNKS])
    )
    user = f"文档片段：\n{context}\n\n问题：{question}\n\n请给出答案。"
    return await _consume_stream(llm_client.stream(_SYSTEM_PROMPT, user))


async def _predict_one(corpus, retriever, reranker_svc, llm_client, q) -> dict:
    candidates = retriever.search(q["query"], RETRIEVE_CANDIDATES)
    if candidates:
        passages = [corpus[c["chunk_index"]]["text"] for c in candidates]
        scores = reranker_svc.score(q["query"], passages)
        # 同分保持候选原始（检索）序，确定性
        top = [
            {**c, "score": float(s)}
            for s, c in sorted(zip(scores, candidates), key=lambda x: (-x[0], x[1]["chunk_index"]))
        ][:RERANK_TOP_K]
    else:
        top = []

    if q["unanswerable"]:
        # 弃答题：交由 LLM 判定；若拒绝 → 清空答案与引用（指标要求 citations 为空）。
        ans = await _generate(q["query"], [corpus[t["chunk_index"]] for t in top], llm_client)
        no_answer = _is_no_answer(ans)
        return {
            "query_id": q["id"],
            "retrieved": [{"document_id": c["document_id"], "physical_page": c["physical_page"],
                           "chunk_index": c["chunk_index"], "score": c["score"]} for c in top],
            "citations": [],
            "answer": "" if no_answer else ans,
            "no_answer": no_answer,
        }

    if not top:
        return {"query_id": q["id"], "retrieved": [], "citations": [], "answer": "",
                "no_answer": True}

    ans = await _generate(q["query"], [corpus[t["chunk_index"]] for t in top], llm_client)
    no_answer = _is_no_answer(ans)
    return {
        "query_id": q["id"],
        "retrieved": [{"document_id": c["document_id"], "physical_page": c["physical_page"],
                       "chunk_index": c["chunk_index"], "score": c["score"]} for c in top],
        "citations": [] if no_answer else [
            {"document_id": c["document_id"], "physical_page": c["physical_page"]} for c in top[:RERANK_TOP_K]
        ],
        "answer": "" if no_answer else ans,
        "no_answer": no_answer,
    }


def predict(
    corpus: list[dict],
    questions: list[dict],
    *,
    emb: embeddings.EmbeddingService | None = None,
    reranker_svc: reranker.RerankService | None = None,
    llm_client: llm.LLMClient | None = None,
) -> list[dict]:
    """运行真实管线，返回与 questions 同序的 predictions。三个服务可注入（测试用假件）。"""
    use_native = all(v is None for v in (emb, reranker_svc, llm_client))
    emb = emb or index_service.get_embedder()
    reranker_svc = reranker_svc or rerank_service.get_reranker()
    llm_client = llm_client or llm.LLMClient()
    # 只有走真实默认入口（build_report）才校验真实后端；注入假件（测试）不受全局 mock 状态约束
    if use_native:
        assert embeddings.effective_embed_config()["backend"] != "mock", \
            "评测要求真实嵌入后端（设置页关闭 mock，启用 bge-m3）"
        assert reranker.effective_rerank_config()["backend"] != "mock", \
            "评测要求真实重排后端（设置页关闭 mock，启用 bge-reranker-v2-m3）"
        assert llm_client.status()[0] != "mock", "评测要求真实 LLM 后端（RAG_LLM_MOCK=false）"

    retriever = RealDenseRetriever(corpus, emb)
    return asyncio.run(_predict_all(corpus, questions, retriever, reranker_svc, llm_client))


async def _predict_all(corpus, questions, retriever, reranker_svc, llm_client) -> list[dict]:
    return [await _predict_one(corpus, retriever, reranker_svc, llm_client, q) for q in questions]


# ---------------- 同源自检 + provenance ----------------

def _resolve_bgem3_path() -> str:
    """解析 EmbeddingService 真实加载到的本地权重目录（与 Chat 端到端同源）。"""
    emb = index_service.get_embedder()
    emb.is_ready()
    m = emb._model
    inner = getattr(m, "model", None) or m
    name_or_path = getattr(getattr(inner, "config", None), "_name_or_path", None)
    return str(name_or_path or getattr(inner, "name_or_path", "<unknown>"))


def build_provenance() -> dict:
    prov = dict(PROVENANCE_RUN)
    prov["device"] = accelerator.device()
    prov["use_fp16"] = accelerator.use_fp16()
    prov["embedding_resolved_path"] = _resolve_bgem3_path()
    cfg = llm.effective_llm_config()
    prov["llm_backend"] = cfg["backend"]
    prov["llm_base_url"] = cfg["base_url"]
    prov["llm_model"] = cfg["model"]
    same_source = (
        prov["embedding_resolved_path"].startswith("/models/hf_cache")
        and prov["embedding_resolved_path"] != "<unknown>"
    )
    prov["embedding_same_source_as_chat"] = same_source
    return prov


# ---------------- 报告 ----------------

def build_report(work_dir: Path, ks=KS) -> dict:
    data = load_corpus(work_dir)
    manifest = public_dataset.load_manifest()
    questions = public_dataset.load_questions()
    predictions = predict(data["corpus"], questions)
    result = eval_metrics.evaluate(predictions, questions, ks)
    return {
        "profile": manifest["profile"],
        "manifest": {"id": manifest["id"], "name": manifest["name"],
                     "version": manifest["version"],
                     "n_questions": manifest["n_questions"],
                     "answerable_count": manifest["answerable_count"],
                     "unanswerable_count": manifest["unanswerable_count"]},
        "corpus": {"documents": data["documents"], "n_chunks": data["n_chunks"],
                   "source_cache": str(work_dir / "source_cache")},
        "pipeline": {
            "name": "bge-m3 dense + bge-reranker-v2-m3 + qwen3:4b (generative)",
            "ks": list(ks), "rerank_top_k": RERANK_TOP_K,
            "candidate_k": RETRIEVE_CANDIDATES, "ctx_chunks": CTX_CHUNKS,
            "deterministic": False, "note": "llm.stream 固定 temperature=0",
        },
        "metrics": result["metrics"],
        "ci": result["ci"],
        "slices": result["slices"],
        "per_query": result["per_query"],
        "provenance": build_provenance(),
    }


def main(argv: list[str] | None = None) -> int:
    # CLI 为独立进程，需自行载入设置页写回的运行时覆盖（web 由 lifespan 加载）
    runtime_config.load_runtime_config()
    parser = argparse.ArgumentParser(prog="public_real",
                                     description="NIST 公开评测：真实完整管线（bge-m3+reranker+Ollama）")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--out", default=str(DEFAULT_REPORT).replace("_report", "_real_report"),
                        help="报告输出路径（相对 work-dir 或绝对路径）")
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
    print(f"real-run OK: recall@5={m['recall@5']:.3f} mrr={m['mrr']:.3f} "
          f"ndcg@5={m['ndcg@5']:.3f} citation_prec={m['citation_page_precision']:.3f} "
          f"answer_em={m['answer_em']:.3f} | eligible={m['eligible']}/{m['total']} "
          f"report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())