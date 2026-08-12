"""索引服务：嵌入 + 持久化 + FAISS 增量构建。

- 将解析分块批量嵌入（dense BLOB 入 chunks.embedding，sparse 关键词入 chunk_fts）。
- 同步把 dense 向量加入常驻内存的 FAISS 索引。
- 启动时从 SQLite 重建 FAISS（rebuild_faiss），保证内存与持久化一致。
"""
from __future__ import annotations

import numpy as np

from app.core.embeddings import EmbeddingService
from app.core.errors import ModelNotReadyError
from app.core.faiss_store import FaissStore
from app.repositories import chunk_repo

_embedder = EmbeddingService()
_faiss = FaissStore()


def get_embedder() -> EmbeddingService:
    return _embedder


def get_faiss() -> FaissStore:
    return _faiss


def _assert_ready() -> None:
    backend, ready = _embedder.status()
    if not ready:
        raise ModelNotReadyError(
            f"嵌入模型未就绪（当前后端：{backend}）。请配置 BAAI/bge-m3 权重，"
            f"或设置 RAG_EMBED_MOCK=true 以离线验证。"
        )


async def rebuild_faiss() -> None:
    """启动 / 删除后重建内存向量索引。"""
    rows = await chunk_repo.get_all_embeddings()
    _faiss.build_from(rows)


async def index_parsed_chunks(document_id: str, parsed_chunks: list) -> int:
    """嵌入并落库一批分块，返回写入的分块数。

    parsed_chunks: list[app.core.parser.ParsedChunk]
    """
    _assert_ready()
    if not parsed_chunks:
        return 0
    contents = [c.content for c in parsed_chunks]
    dense, sparse = _embedder.embed(contents)
    for seq, (ch, vec, sp) in enumerate(zip(parsed_chunks, dense, sparse), start=1):
        blob = np.asarray(vec, dtype=np.float32).tobytes()
        # sparse 词表前 50 个高频词补入 FTS，增强关键词召回
        top_terms = " ".join(k for k, _ in sorted(sp.items(), key=lambda kv: -kv[1])[:50])
        await chunk_repo.insert_chunk(
            document_id=document_id,
            seq=seq,
            content=ch.content,
            page_no=ch.page_no,
            bbox=ch.bbox,
            section=ch.section,
            embedding_blob=blob,
            fts_extra=top_terms,
        )
    # 统一从持久化重建内存索引，保证 chunk id 对齐
    await rebuild_faiss()
    return len(parsed_chunks)
