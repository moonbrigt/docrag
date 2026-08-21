"""检索服务：混合检索（FAISS 稠密 + FTS5 关键词）与 RRF(k=60) 融合。

范围与权限（P0 红线）：
- document_ids=None = 全部可见文档；[] = 显式空范围（零结果）；其余 = 交集。
- FAISS 全局检索后按 chunk->document 映射过滤，再按可见范围收窄，
  禁止泄漏无权限 / 范围外文档的分块。
- FTS 路以范围 IN 条件直查；两路都带范围过滤后才融合。
- 过滤后结果可能少于 top_k（范围小的私库常见），不注水。

缓存：LRU + TTL，键 = (query, frozenset(scope))，避免同租户不同用户共享缓存。
"""
from __future__ import annotations

import re
import time

from app import auth, db
from app.config import get_settings
from app.core.errors import ModelNotReadyError
from app.repositories import chunk_repo
from app.schemas import RetrievedChunk
from app.services import document_service, index_service

_settings = get_settings()
_SAFE = re.compile(r"[^0-9a-zA-Z一-鿿 ]")

# ---------- 查询缓存（LRU + TTL） ----------
_cache: dict[str, tuple[float, list[RetrievedChunk]]] = {}


def _cache_key(query: str, scope: frozenset[str]) -> str:
    """键 = query + resolved scope（已做 ACL 过滤的可见文档集）。"""
    return f"{query}|{'|'.join(sorted(scope))}"


def _cache_get(key: str) -> list[RetrievedChunk] | None:
    """命中且未过期则返回缓存结果，否则 None。"""
    if _settings.CACHE_TTL <= 0:
        return None
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, result = entry
    if (time.monotonic() - ts) > _settings.CACHE_TTL:
        _cache.pop(key, None)
        return None
    return result


def _cache_set(key: str, result: list[RetrievedChunk]) -> None:
    if _settings.CACHE_TTL <= 0:
        return
    _cache[key] = (time.monotonic(), result)
    # 简易 LRU：超 500 条时淘汰最早插入的 100 条
    if len(_cache) > 500:
        oldest = sorted(_cache, key=lambda k: _cache[k][0])[:100]
        for k in oldest:
            _cache.pop(k, None)


def invalidate_cache(tenant_id: str | None = None) -> None:
    """清除缓存。reindex / 文档删除 / 模型切换时调用。"""
    if tenant_id is None:
        _cache.clear()
    else:
        keys_to_remove = [k for k in _cache if k.endswith(f"|{tenant_id}") or "|" not in k]
        for k in keys_to_remove:
            _cache.pop(k, None)
    # 简化：reindex 时清全部缓存（文档集变化影响所有 scope）
    _cache.clear()

# FAISS 过采样倍数：全局 top-k 过滤到范围后可能损失候选，放大后取回
_FAISS_OVERSAMPLE = 3


def _short_query(q: str) -> bool:
    """1–2 字中文（或极短）查询，trigram 无法召回，走 LIKE 兜底。"""
    q = q.strip()
    return len(q) <= 2


def _fts_search(query: str, top_k: int, scope: set[str]) -> list[tuple[int, float]]:
    """FTS5 trigram / LIKE 检索，严格限定在检索范围内。"""
    if not scope:
        return []
    if _short_query(query):
        like = f"%{query.strip()}%"
        ph = ",".join("?" * len(scope))
        sql = (
            "SELECT id FROM chunks WHERE content LIKE ? "
            f"AND document_id IN ({ph}) LIMIT {top_k}"
        )
        rows = db.query(sql, (like, *sorted(scope)))
        # LIKE 无 bm25，按出现顺序给名义分（RRF 只看排名）
        return [(r["id"], 0.0) for r in rows]

    safe = _SAFE.sub(" ", query).strip()
    if not safe:
        return []
    match_expr = '"' + safe.replace('"', "") + '"'
    ph = ",".join("?" * len(scope))
    sql = (
        "SELECT f.rowid AS cid, bm25(chunk_fts) AS r FROM chunk_fts f "
        f"JOIN chunks c ON c.id=f.rowid AND c.document_id IN ({ph}) "
        "WHERE chunk_fts MATCH ? ORDER BY r LIMIT ?"
    )
    rows = db.query(sql, (*sorted(scope), match_expr, top_k))
    # bm25 越小越相关，转为正分便于阅读（融合只用排名，符号无关）
    return [(r["cid"], -float(r["r"])) for r in rows]


async def _faiss_scoped(
    faiss, vec, scope: set[str], k: int
) -> list[tuple[int, float]]:
    """FAISS 全局 top-k 检索 -> chunk->document 映射 -> 范围过滤。

    已知局限（文档化）：范围过滤发生在全局 top-k 之后；若范围内文档极少而
    库内异文档极多，召回可能被截断。本地部署体量下接受，且绝不泄漏范围外条目。
    """
    if not scope:
        return []
    raw = faiss.search(vec, k * _FAISS_OVERSAMPLE)
    if not raw:
        return []
    mapping = await chunk_repo.get_doc_ids_for_chunks([cid for cid, _ in raw])
    out: list[tuple[int, float]] = []
    for cid, score in raw:
        if mapping.get(cid) in scope:
            out.append((cid, score))
            if len(out) >= k:
                break
    return out


def _rrf(lists: list[list[tuple[int, float]]], k: int) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for lst in lists:
        for rank, (cid, _) in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


async def hybrid_retrieve(
    query: str,
    document_ids: list[str] | None = None,
    principal: auth.Principal | None = None,
) -> list[RetrievedChunk]:
    """混合检索：FAISS + FTS 双路均限定在「可见 & 范围内」文档。"""
    principal = principal or auth.default_principal()
    scope = await document_service.resolve_scope(principal, document_ids)
    if not scope:
        return []

    # 缓存命中检查（键用 resolved scope，避免越权）
    ck = _cache_key(query, scope)
    cached = _cache_get(ck)
    if cached is not None:
        return cached

    embedder = index_service.get_embedder()
    faiss = index_service.get_faiss()
    if not embedder.is_ready():
        raise ModelNotReadyError(
            "嵌入模型未就绪，无法执行检索。请配置 BAAI/bge-m3 或开启 RAG_EMBED_MOCK。"
        )
    vec, _ = embedder.embed_one(query)
    faiss_res = await _faiss_scoped(faiss, vec, scope, _settings.FAISS_TOP_K)
    fts_res = _fts_search(query, _settings.FTS_TOP_K, scope)
    fused = _rrf([faiss_res, fts_res], _settings.RRF_K)

    ids = [cid for cid, _ in fused]
    if not ids:
        return []
    chunk_rows = await chunk_repo.get_chunks_by_ids(ids)
    faiss_score = {cid: s for cid, s in faiss_res}
    fts_score = {cid: s for cid, s in fts_res}

    # 元数据 join 天然限定在范围内（范围=可见文档），不泄露范围外文档名
    doc_ids = list({r["document_id"] for r in chunk_rows})
    names: dict[str, dict] = {}
    if doc_ids:
        ph = ",".join("?" * len(doc_ids))
        drows = db.query(
            "SELECT id, filename, source_id, version, created_at FROM documents "
            f"WHERE id IN ({ph})",
            tuple(doc_ids),
        )
        names = {r["id"]: r for r in drows}

    row_by_id = {r["id"]: r for r in chunk_rows}
    result: list[RetrievedChunk] = []
    for cid, rrf in fused:
        r = row_by_id.get(cid)
        if not r:
            continue
        meta = names.get(r["document_id"], {})
        result.append(
            RetrievedChunk(
                chunk_id=cid,
                document_id=r["document_id"],
                doc_name=meta.get("filename") or "",
                seq=r["seq"],
                page_no=r["page_no"],
                bbox=r["bbox"],
                section=r["section"],
                snippet=(r["content"] or "")[:200],
                rrf_score=rrf,
                faiss_score=faiss_score.get(cid),
                fts_score=fts_score.get(cid),
                source_id=meta.get("source_id"),
                version=meta.get("version"),
                title=meta.get("filename"),
                created_at=meta.get("created_at"),
            )
        )
    _cache_set(ck, result)
    return result
