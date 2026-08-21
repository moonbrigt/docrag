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
        detail = (
            f"嵌入模型未就绪（当前后端：{backend}）。\n"
            "- http 后端：在设置页配置 OpenAI 兼容 /v1/embeddings 的 Endpoint 与模型名；\n"
            "- bge-m3：请配置 BAAI/bge-m3 权重；\n"
            "- 或设置 RAG_EMBED_MOCK=true 以离线验证。"
        )
        raise ModelNotReadyError(detail)


async def rebuild_faiss() -> None:
    """启动 / 删除后重建内存向量索引。"""
    rows = await chunk_repo.get_all_embeddings()
    _faiss.build_from(rows)


async def reindex_all() -> int:
    """按当前嵌入后端重编码全部 chunk 向量（换模型后调用，保证维度一致）。"""
    _assert_ready()
    rows = await chunk_repo.get_all_material()
    if not rows:
        await rebuild_faiss()
        return 0
    n = 0
    for i in range(0, len(rows), 64):
        batch = rows[i : i + 64]
        ids = [cid for cid, _ in batch]
        texts = [t for _, t in batch]
        dense, _ = _embedder.embed(texts)
        items = [
            (cid, np.asarray(v, dtype=np.float32).tobytes()) for cid, v in zip(ids, dense)
        ]
        await chunk_repo.update_embeddings_bulk(items)
        n += len(items)
    await rebuild_faiss()
    return n


async def index_parsed_chunks(document_id: str, parsed_chunks: list) -> int:
    """嵌入并落库一批分块，返回写入的分块数。

    parsed_chunks: list[app.core.parser.ParsedChunk]
    """
    _assert_ready()
    if not parsed_chunks:
        return 0
    contents = [c.content for c in parsed_chunks]
    dense, sparse = _embedder.embed(contents)
    # 批量写库：单事务插入所有分块 + FTS 条目，减少 N 次 db.write 为 1 次
    items = []
    for seq, (ch, vec, sp) in enumerate(zip(parsed_chunks, dense, sparse), start=1):
        blob = np.asarray(vec, dtype=np.float32).tobytes()
        top_terms = " ".join(k for k, _ in sorted(sp.items(), key=lambda kv: -kv[1])[:50])
        items.append({
            "document_id": document_id,
            "seq": seq,
            "content": ch.content,
            "page_no": ch.page_no,
            "bbox": ch.bbox,
            "section": ch.section,
            "embedding_blob": blob,
            "fts_extra": top_terms,
        })
    await chunk_repo.insert_chunks_bulk(items)
    # 统一从持久化重建内存索引，保证 chunk id 对齐
    await rebuild_faiss()
    return len(parsed_chunks)
