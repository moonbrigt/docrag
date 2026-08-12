"""检索消融变体（用于评测对比表）：BM25 / mock-dense / 混合 RRF / 混合+词法重排。

- mock-dense 复用 app.core.embeddings 的确定性 mock 嵌入（离线、无密钥、可复现），
  与生产 mock 后端同源；报告中显式标注为 mock 稠密向量，不冒充真实 bge-m3。
- 混合检索 = RRF(k=60) 融合 BM25 与 mock-dense 两路候选（与生产 retrieve 同口径）。
- 全部只接收 corpus 与 query，gold 绝不进入管线。
"""
from __future__ import annotations

import numpy as np

from app.core import embeddings as emb_mod
from app.evaluation import baselines


class MockDenseRetriever:
    """确定性 mock 稠密检索：mock 嵌入（1024 维）→ 余弦 top-k。"""

    def __init__(self, corpus: list[dict]) -> None:
        self.corpus = corpus
        svc = emb_mod.EmbeddingService()
        svc._mock = True
        svc._model = None
        svc._backend_name = "mock"
        self._svc = svc
        dense, _ = svc.embed([c["text"] for c in corpus])
        self._vectors = np.asarray(dense, dtype=np.float32)

    def search(self, query: str, k: int) -> list[dict]:
        qv = np.asarray(self._svc.embed_one(query)[0], dtype=np.float32)
        scores = self._vectors @ qv  # 已归一化 → 余弦
        order = np.argsort(-scores)
        out: list[dict] = []
        for idx in order:
            s = float(scores[idx])
            if s <= 0.0:
                break  # 零/负信号不冒充候选（与生产证据层同规则）
            out.append(
                {
                    "chunk_index": int(idx),
                    "document_id": self.corpus[int(idx)]["document_id"],
                    "physical_page": self.corpus[int(idx)]["physical_page"],
                    "score": s,
                }
            )
            if len(out) >= k:
                break
        return out


class HybridRetriever:
    """RRF(k=60) 融合 BM25 与 mock-dense 双路（与生产混合检索同口径）。"""

    def __init__(self, corpus: list[dict], rrf_k: int = 60) -> None:
        self.corpus = corpus
        self.rrf_k = rrf_k
        self._bm25 = baselines.BM25Retriever(corpus)
        self._dense = MockDenseRetriever(corpus)

    def search(self, query: str, k: int) -> list[dict]:
        fused: dict[int, float] = {}
        for rank, cand in enumerate(self._bm25.search(query, k * 5)):
            fused[cand["chunk_index"]] = fused.get(cand["chunk_index"], 0.0) + 1.0 / (
                self.rrf_k + rank + 1
            )
        for rank, cand in enumerate(self._dense.search(query, k * 5)):
            fused[cand["chunk_index"]] = fused.get(cand["chunk_index"], 0.0) + 1.0 / (
                self.rrf_k + rank + 1
            )
        ordered = sorted(fused.items(), key=lambda x: (-x[1], x[0]))
        return [
            {
                "chunk_index": idx,
                "document_id": self.corpus[idx]["document_id"],
                "physical_page": self.corpus[idx]["physical_page"],
                "score": score,
            }
            for idx, score in ordered[:k]
        ]


class IdentityReranker:
    """无重排：原样截断（用于 dense / hybrid 变体）。"""

    def __init__(self, corpus: list[dict]) -> None:
        self.corpus = corpus

    def rerank(self, query: str, candidates: list[dict], k: int) -> list[dict]:
        return candidates[:k]


VARIANT_SPECS = {
    "bm25": lambda corpus: (
        baselines.BM25Retriever(corpus),
        baselines.LexicalReranker(corpus),
        "BM25 + 词法重排 + 抽取式答案",
    ),
    "dense_mock": lambda corpus: (
        MockDenseRetriever(corpus),
        IdentityReranker(corpus),
        "mock 稠密向量（确定性 mock 嵌入） + 抽取式答案",
    ),
    "hybrid": lambda corpus: (
        HybridRetriever(corpus),
        IdentityReranker(corpus),
        "RRF 混合（BM25 + mock 稠密） + 抽取式答案",
    ),
    "hybrid_rerank": lambda corpus: (
        HybridRetriever(corpus),
        baselines.LexicalReranker(corpus),
        "RRF 混合 + 词法重排 + 抽取式答案",
    ),
}
