"""重排服务：包装 core.reranker，对混合检索结果用 bge-reranker-v2-m3 精排。

- 输入 RetrievedChunk 列表（通常 top-20），输出按相关分降序截断 top-K。
- 模型未就绪且非 mock 时抛 ModelNotReadyError（503）。
"""
from __future__ import annotations

from app.config import get_settings
from app.core.errors import ModelNotReadyError
from app.core.reranker import RerankService
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
    passages = [c.snippet for c in chunks]
    scores = _reranker.score(query, passages)
    ranked = sorted(zip(chunks, scores), key=lambda x: -x[1])
    return [c for c, _ in ranked[:top_k]]
