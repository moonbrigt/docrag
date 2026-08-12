"""评测运行器：基于 dataset.json 的内嵌语料离线计算检索质量指标。

流程：
1. 将语料每页作为一个分块，用确定性 mock 嵌入（不下载大模型）构建内存 FAISS 索引。
2. 对每个问答执行「稠密 + 关键词」混合检索（RRF 融合），取页码有序列表。
3. 计算 Citation Accuracy（页码命中率）、Recall@K、Hit Rate@K、MRR。
4. 返回 {metrics, per_query} 供 POST /evaluation/run 落库并返回。

真实部署下可将 embed 切换为 bge-m3（设置 EMBED_MOCK=false 并挂载权重），
检索逻辑与指标口径不变。
"""
from __future__ import annotations

import json
import os
import re

from app.config import get_settings
from app.core.embeddings import EmbeddingService
from app.core.faiss_store import FaissStore

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DATASET = os.path.join(_HERE, "dataset.json")
_TOKEN_RE = re.compile(r"[\w一-鿿]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def load_dataset(path: str | None = None) -> dict:
    path = path or _DEFAULT_DATASET
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run(dataset: dict | None = None, config: dict | None = None) -> dict:
    dataset = dataset or load_dataset()
    settings = get_settings()

    # 确定性 mock 嵌入，保证离线可复现
    embed = EmbeddingService()
    embed._mock = True
    embed._model = None
    embed._backend_name = "mock"

    # 构建语料分块
    chunks: list[dict] = []
    cid = 0
    for doc in dataset["corpus"]:
        for page in doc["pages"]:
            chunks.append(
                {
                    "chunk_id": cid,
                    "doc_id": doc["doc_id"],
                    "doc_name": doc["doc_name"],
                    "page_no": page["page_no"],
                    "text": page["text"],
                }
            )
            cid += 1

    dense, _ = embed.embed([c["text"] for c in chunks])
    store = FaissStore()
    for c, v in zip(chunks, dense):
        store.add(c["chunk_id"], v)

    def retrieve(query: str, k: int) -> list[dict]:
        vec, _ = embed.embed_one(query)
        faiss_res = store.search(vec, k)
        qtok = _tokenize(query)
        kw: dict[int, float] = {}
        for c in chunks:
            t = c["text"].lower()
            score = sum(1 for tok in qtok if tok and tok in t)
            if score > 0:
                kw[c["chunk_id"]] = float(score)
        kw_sorted = sorted(kw.items(), key=lambda x: -x[1])
        fused: dict[int, float] = {}
        for rank, (cidn, _) in enumerate(faiss_res):
            fused[cidn] = fused.get(cidn, 0.0) + 1.0 / (settings.RRF_K + rank + 1)
        for rank, (cidn, _) in enumerate(kw_sorted):
            fused[cidn] = fused.get(cidn, 0.0) + 1.0 / (settings.RRF_K + rank + 1)
        ordered = sorted(fused.items(), key=lambda x: -x[1])
        pages: list[dict] = []
        seen: set[int] = set()
        for cidn, _ in ordered:
            c = chunks[cidn]
            if c["page_no"] not in seen:
                seen.add(c["page_no"])
                pages.append({"page_no": c["page_no"], "doc_name": c["doc_name"]})
        return pages

    Ks = [5, 10]
    cite_K = settings.RERANK_TOP_K
    n = len(dataset["qa"])
    recall_sum = {k: 0.0 for k in Ks}
    hit_sum = {k: 0.0 for k in Ks}
    cite_hit = 0.0
    mrr_sum = 0.0
    per_query: list[dict] = []

    for q in dataset["qa"]:
        pages = retrieve(q["query"], 20)
        page_nos = [p["page_no"] for p in pages]
        E = set(q["expected_pages"])
        top_set = set(page_nos[:cite_K])
        hit = bool(E & top_set)
        cite_hit += 1.0 if hit else 0.0
        for k in Ks:
            topk = set(page_nos[:k])
            inter = len(E & topk)
            recall_sum[k] += inter / len(E) if E else 0.0
            hit_sum[k] += 1.0 if inter > 0 else 0.0
        rank = next((i for i, pn in enumerate(page_nos, start=1) if pn in E), None)
        mrr_sum += 1.0 / rank if rank else 0.0
        per_query.append(
            {
                "id": q["id"],
                "query": q["query"],
                "expected_pages": q["expected_pages"],
                "retrieved_pages": page_nos[:cite_K],
                "hit": hit,
            }
        )

    metrics = {
        "citation_accuracy": cite_hit / n if n else 0.0,
        "recall_at_k": {k: recall_sum[k] / n for k in Ks},
        "hit_rate_at_k": {k: hit_sum[k] / n for k in Ks},
        "mrr": mrr_sum / n if n else 0.0,
        "num_queries": n,
        "embedding_backend": embed._backend_name,
    }
    return {"metrics": metrics, "per_query": per_query}


if __name__ == "__main__":
    import pprint

    pprint.pprint(run())
