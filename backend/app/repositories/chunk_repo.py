"""分块数据访问层（chunks + chunk_fts）。

- chunks.embedding 以 float32(1024) BLOB 持久化。
- chunk_fts 为 FTS5 trigram 虚拟表，rowid 与 chunks.id 对齐（Spec §6 契约）。
- 写入分块时同步写入 FTS 条目，保证向量与关键词索引一致。
"""
from __future__ import annotations

import json

from app import db


def _bbox_to_json(bbox: dict | None) -> str | None:
    return json.dumps(bbox, ensure_ascii=False) if bbox else None


def _json_to_bbox(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def insert_chunk(
    document_id: str,
    seq: int,
    content: str,
    page_no: int,
    bbox: dict | None,
    section: str | None,
    embedding_blob: bytes | None,
    fts_extra: str = "",
) -> int:
    """插入一个分块及其 FTS 条目，返回 chunk id。"""
    bbox_json = _bbox_to_json(bbox)

    def _insert(c):
        cur = c.execute(
            "INSERT INTO chunks (document_id, seq, content, page_no, bbox, section, embedding) "
            "VALUES (?,?,?,?,?,?,?)",
            (document_id, seq, content, page_no, bbox_json, section, embedding_blob),
        )
        cid = cur.lastrowid
        fts_text = content + (" " + fts_extra if fts_extra else "")
        c.execute("INSERT INTO chunk_fts (rowid, content) VALUES (?, ?)", (cid, fts_text))
        return cid

    return await db.write(_insert)


async def list_chunks_by_doc(document_id: str) -> list[dict]:
    rows = db.query(
        "SELECT id, document_id, seq, content, page_no, bbox, section "
        "FROM chunks WHERE document_id=? ORDER BY seq",
        (document_id,),
    )
    for r in rows:
        r["bbox"] = _json_to_bbox(r.get("bbox"))
    return rows


async def get_chunk(chunk_id: int) -> dict | None:
    row = db.query_one(
        "SELECT id, document_id, seq, content, page_no, bbox, section FROM chunks WHERE id=?",
        (chunk_id,),
    )
    if row:
        row["bbox"] = _json_to_bbox(row.get("bbox"))
    return row


async def get_chunks_by_ids(chunk_ids: list[int]) -> list[dict]:
    if not chunk_ids:
        return []
    placeholders = ",".join("?" * len(chunk_ids))
    rows = db.query(
        f"SELECT id, document_id, seq, content, page_no, bbox, section FROM chunks "
        f"WHERE id IN ({placeholders})",
        tuple(chunk_ids),
    )
    by_id = {r["id"]: r for r in rows}
    out = []
    for cid in chunk_ids:
        r = by_id.get(cid)
        if r:
            r["bbox"] = _json_to_bbox(r.get("bbox"))
            out.append(r)
    return out


async def get_all_embeddings() -> list[tuple[int, bytes]]:
    """返回全部 (chunk_id, embedding_blob)，用于启动重建 FAISS。"""
    rows = db.query("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL")
    return [(r["id"], r["embedding"]) for r in rows]


async def count_chunks() -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM chunks")
    return row["n"] if row else 0


async def count_chunks_for_doc(document_id: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM chunks WHERE document_id=?", (document_id,)
    )
    return row["n"] if row else 0


async def delete_chunks_by_doc(document_id: str) -> None:
    """事务内删除某文档的全部分块与 FTS 条目（取消/失败清理用）。"""

    def _delete(c):
        c.execute(
            "DELETE FROM chunk_fts WHERE rowid IN "
            "(SELECT id FROM chunks WHERE document_id=?)",
            (document_id,),
        )
        c.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))

    await db.write(_delete)


async def get_doc_ids_for_chunks(chunk_ids: list[int]) -> dict[int, str]:
    """chunk_id -> document_id 映射（FAISS 结果按文档范围过滤用）。"""
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" * len(chunk_ids))
    rows = db.query(
        f"SELECT id, document_id FROM chunks WHERE id IN ({placeholders})",
        tuple(chunk_ids),
    )
    return {r["id"]: r["document_id"] for r in rows}
