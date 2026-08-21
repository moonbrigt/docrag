"""真实模型全链路评测：bge-m3 + bge-reranker-v2-m3 + 真实 LLM。

五路变体见 all_variants；hybrid_rerank_prod_llm 复现生产重排参数（10 候选/256 token）。
词法重排统一用 baselines.LexicalReranker（与生产 mock 重排同实现，保证口径一致）。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.core import llm as llm_mod
from app.core import runtime_config
from app.evaluation import eval_metrics, public_dataset
from app.evaluation.public_runner import DEFAULT_WORK_DIR, KS, RERANK_TOP_K, load_corpus
from app.evaluation.real_llm_runner import (
    _SYSTEM_PROMPT,
    CTX_CHUNKS,
    _consume_stream,
    _extract_final_answer,
    _is_no_answer,
)


# ---------------------------------------------------------------------------
# Real bge-m3 dense retriever
# ---------------------------------------------------------------------------
class RealDenseRetriever:
    """bge-m3 稠密向量检索：真实嵌入 → 余弦 top-k。"""

    def __init__(self, corpus: list[dict]) -> None:
        t0 = time.time()
        self.corpus = corpus
        from FlagEmbedding import BGEM3FlagModel

        self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        texts = [c["text"] for c in corpus]
        print(f"  [bge-m3] embedding {len(texts)} chunks...")
        out = self._model.encode(texts, batch_size=32)
        self._vectors = np.asarray(out["dense_vecs"], dtype=np.float32)
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._vectors = self._vectors / norms
        print(f"  [bge-m3] done in {time.time()-t0:.1f}s, dim={self._vectors.shape[1]}")

    def search(self, query: str, k: int) -> list[dict]:
        qv = np.asarray(
            self._model.encode([query])["dense_vecs"], dtype=np.float32
        ).squeeze()
        qv = qv / (np.linalg.norm(qv) or 1.0)
        scores = self._vectors @ qv
        order = np.argsort(-scores)
        out: list[dict] = []
        for idx in order:
            s = float(scores[idx])
            if s <= 0.0:
                break
            out.append({
                "chunk_index": int(idx),
                "document_id": self.corpus[int(idx)]["document_id"],
                "physical_page": self.corpus[int(idx)]["physical_page"],
                "score": s,
            })
            if len(out) >= k:
                break
        return out


class RealReranker:
    """bge-reranker-v2-m3 CrossEncoder 重排；模型懒加载（未用到的实例不占内存）。

    pool/max_length 复现生产重排参数（RAG_RERANK_CANDIDATES / MAX_TOKENS）；
    默认 None = 候选全量、模型默认 512 token（§12.2 基线口径）。
    """

    def __init__(self, corpus: list[dict], max_length: int | None = None,
                 pool: int | None = None) -> None:
        self.corpus = corpus
        self.max_length = max_length
        self.pool = pool
        self._model = None

    def _ensure(self):
        if self._model is None:
            t0 = time.time()
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cpu")
            print(f"  [reranker] loaded in {time.time()-t0:.1f}s")

    def rerank(self, query: str, candidates: list[dict], k: int) -> list[dict]:
        if not candidates:
            return []
        if self.pool:
            candidates = candidates[: self.pool]
        self._ensure()
        passages = [self.corpus[c["chunk_index"]]["text"][:4000] for c in candidates]
        pairs = [(query, p) for p in passages]
        kwargs = {"max_length": self.max_length} if self.max_length else {}
        raw_scores = self._model.predict(pairs, show_progress_bar=False, **kwargs)
        scored = list(zip(candidates, [float(s) for s in raw_scores]))
        scored.sort(key=lambda x: -x[1])
        return [c for c, _ in scored[:k]]


class IdentityReranker:
    def rerank(self, query: str, candidates: list[dict], k: int) -> list[dict]:
        return candidates[:k]


def rrf_fuse(bm25, dense, corpus, query, k, rrf_k=60):
    fused: dict[int, float] = {}
    for rank, cand in enumerate(bm25.search(query, k * 5)):
        fused[cand["chunk_index"]] = fused.get(cand["chunk_index"], 0.0) + 1.0 / (
            rrf_k + rank + 1
        )
    for rank, cand in enumerate(dense.search(query, k * 5)):
        fused[cand["chunk_index"]] = fused.get(cand["chunk_index"], 0.0) + 1.0 / (
            rrf_k + rank + 1
        )
    ordered = sorted(fused.items(), key=lambda x: (-x[1], x[0]))
    return [
        {
            "chunk_index": idx,
            "document_id": corpus[idx]["document_id"],
            "physical_page": corpus[idx]["physical_page"],
            "score": score,
        }
        for idx, score in ordered[:k]
    ]


def _hybrid(bm25, dense, corpus):
    return type("R", (), {"search": lambda self, q, k: rrf_fuse(bm25, dense, corpus, q, k)})()


# ---------------------------------------------------------------------------
# LLM answer generation
# ---------------------------------------------------------------------------
async def _gen_answer(q, top_candidates, llm_client, corpus):
    """top_candidates: list of dicts with chunk_index, document_id, physical_page, score."""
    if not top_candidates:
        return {
            "query_id": q["id"], "retrieved": [],
            "citations": [], "answer": "", "no_answer": True,
        }
    top_chunks = [corpus[c["chunk_index"]] for c in top_candidates[:CTX_CHUNKS]]
    context = "\n".join(
        f"[{i+1}] {c['text'][:4000]}" for i, c in enumerate(top_chunks)
    )
    user_msg = f"文档片段：\n{context}\n\n问题：{q['query']}\n\n请给出答案。"
    try:
        raw = await asyncio.wait_for(
            asyncio.ensure_future(_consume_stream(llm_client.stream(_SYSTEM_PROMPT, user_msg))),
            timeout=120,
        )
    except (asyncio.TimeoutError, RuntimeError, OSError, ValueError) as exc:
        raw = f"<LLM_ERROR: {exc}>"

    ans = _extract_final_answer(raw)
    no_answer = _is_no_answer(ans)
    citations = (
        [] if no_answer
        else [{"document_id": c["document_id"], "physical_page": c["physical_page"]}
              for c in top_candidates[:RERANK_TOP_K]]
    )
    return {
        "query_id": q["id"],
        "retrieved": [
            {"document_id": c["document_id"], "physical_page": c["physical_page"],
             "chunk_index": c["chunk_index"], "score": c.get("score", 0.0)}
            for c in top_candidates
        ],
        "citations": citations,
        "answer": "" if no_answer else ans,
        "no_answer": no_answer,
    }


def predict(corpus, questions, retriever, reranker, llm_client, variant_name=""):
    async def _run():
        results = []
        total = len(questions)
        for i, q in enumerate(questions):
            t0 = time.time()
            candidates = retriever.search(q["query"], RERANK_TOP_K * 3)
            if candidates:
                top = reranker.rerank(q["query"], candidates, RERANK_TOP_K)
            else:
                top = []
            r = await _gen_answer(q, top, llm_client, corpus)
            results.append(r)
            elapsed = time.time() - t0
            ans_preview = r['answer'][:60].replace(chr(10), ' ') if r['answer'] else ('NO_ANSWER' if r.get('no_answer') else 'EMPTY')
            print(f"  [{variant_name}] {i+1}/{total} ({elapsed:.1f}s) {q['id']}: {ans_preview}...", flush=True)
        return results
    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    import argparse

    parser = argparse.ArgumentParser(description="真实模型全链路评测")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR))
    parser.add_argument("--variants", nargs="*", default=None,
                        help="指定变体（默认全部）")
    parser.add_argument("--out", default="real_full_report.json")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    data = load_corpus(work_dir)
    questions = public_dataset.load_questions()
    corpus = data["corpus"]

    # LLM
    runtime_config.load_runtime_config()
    client = llm_mod.LLMClient()
    backend, ready = client.status()
    if not ready:
        print(f"LLM 未就绪（{backend}）")
        sys.exit(1)
    print(f"LLM: {backend}")

    # 预加载真实模型
    from app.evaluation.baselines import BM25Retriever, LexicalReranker

    print("\n=== 加载真实模型 ===")
    bm25 = BM25Retriever(corpus)
    real_dense = RealDenseRetriever(corpus)
    lexical = LexicalReranker(corpus)
    identity = IdentityReranker()

    all_variants = {
        "bm25_real_llm": ("BM25 + 词法重排 + 真实 LLM", bm25, lexical),
        "hybrid_real_llm": (
            "RRF(BM25 + bge-m3) + 无重排 + 真实 LLM", _hybrid(bm25, real_dense, corpus), identity,
        ),
        "hybrid_lexical_llm": (
            "RRF(BM25 + bge-m3) + 词法重排 + 真实 LLM", _hybrid(bm25, real_dense, corpus), lexical,
        ),
        "hybrid_rerank_llm": (
            "RRF(BM25 + bge-m3) + bge-reranker + 真实 LLM", _hybrid(bm25, real_dense, corpus),
            RealReranker(corpus),
        ),
        "hybrid_rerank_prod_llm": (
            "RRF(BM25 + bge-m3) + bge-reranker(生产参数) + 真实 LLM",
            _hybrid(bm25, real_dense, corpus),
            RealReranker(corpus, max_length=get_settings().RERANK_MAX_TOKENS,
                         pool=get_settings().RERANK_CANDIDATES),
        ),
    }

    targets = args.variants or list(all_variants.keys())
    results_all = {}

    for vname in targets:
        desc, retriever, reranker = all_variants[vname]
        print(f"\n{'='*60}")
        print(f"变体: {desc}")
        print(f"{'='*60}")

        t0 = time.time()
        predictions = predict(corpus, questions, retriever, reranker, client, variant_name=vname)
        elapsed = time.time() - t0

        result = eval_metrics.evaluate(predictions, questions, KS)
        m = result["metrics"]
        print(f"\n结果 ({elapsed:.1f}s):")
        print(f"  recall@5={m.get('recall@5', 0):.4f}  MRR={m.get('mrr', 0):.4f}  "
              f"answer_em={m.get('answer_em', 0):.4f}  answer_f1={m.get('answer_f1', 0):.4f}")

        results_all[vname] = {
            "description": desc,
            "metrics": {k: round(v, 4) for k, v in m.items()},
            "eligible": result.get("eligible", 0),
            "total": result.get("total", len(questions)),
            "wall_time_s": round(elapsed, 1),
            "predictions": predictions,
        }

    # 保存
    report = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "variants": results_all}
    out_path = work_dir / args.out
    tmp = out_path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    print(f"\n报告: {out_path}")


if __name__ == "__main__":
    main()
