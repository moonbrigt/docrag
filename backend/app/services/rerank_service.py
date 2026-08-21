"""重排服务：包装 core.reranker，对混合检索结果用 bge-reranker-v2-m3 精排。

- 输入 RetrievedChunk 列表（RRF 融合序），截断候选池后用全文重排，输出 top-K。
- 模型未就绪且非 mock 时抛 ModelNotReadyError（503）。
"""
from __future__ import annotations

from app.config import get_settings
from app.core.errors import ModelNotReadyError
from app.core.reranker import RerankService
from app.repositories import chunk_repo
from app.schemas import RetrievedChunk

_settings = get_settings()
_reranker = RerankService()


def get_reranker() -> RerankService:
    return _reranker


def is_ready() -> bool:
    return _reranker.is_ready()


async def rerank(
    query: str, chunks: list[RetrievedChunk], top_k: int | None = None
) -> list[RetrievedChunk]:
    top_k = top_k or _settings.RERANK_TOP_K
    backend, ready = _reranker.status()
    if not ready:
        raise ModelNotReadyError(
            f"重排模型未就绪（当前后端：{backend}）。请配置 BAAI/bge-reranker-v2-m3，"
            f"或设置 RAG_RERANK_MOCK=true。"
        )
    if not chunks:
        return []
    # 候选池截断（chunks 为 RRF 融合序）：CPU 重排延迟与候选数线性相关
    pool = chunks[: _settings.RERANK_CANDIDATES]
    # 重排用全文而非 snippet（snippet 仅 200 字符，相关性信号不足）
    rows = await chunk_repo.get_chunks_by_ids([c.chunk_id for c in pool])
    content = {r["id"]: r["content"] or "" for r in rows}
    passages = [content.get(c.chunk_id) or c.snippet for c in pool]
    scores = _reranker.score(query, passages)
    ranked = sorted(zip(pool, scores), key=lambda x: -x[1])
    return [c for c, _ in ranked[:top_k]]
