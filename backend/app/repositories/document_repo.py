"""文档数据访问层（documents / document_events 表）。

覆盖 ACL 字段（tenant_id / owner_user_id / group_ids）、生命周期
（source_id / version / is_active / archived_at）与状态流转事件。
group_ids 以 JSON 文本落库，读取时解析为 list[str]。
"""
from __future__ import annotations

import json
import uuid

from app import db

# 瞬态（可取消）状态：流水线进行中
TRANSIENT_STATUSES = ("queued", "parsing", "chunking", "embedding")
# 可重试终态
RETRYABLE_STATUSES = ("failed", "warning", "cancelled")


def new_id() -> str:
    return uuid.uuid4().hex


def _groups_to_json(groups: list[str] | None) -> str:
    return json.dumps(list(groups or []), ensure_ascii=False)


def _groups_from_json(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return [g for g in value if isinstance(g, str)] if isinstance(value, list) else []
    except Exception:
        return []


def _row_to_doc(row: dict) -> dict:
    """把 DB 行规整为对外字典：group_ids 解析为列表、缺省字段补默认值。"""
    doc = dict(row)
    doc["group_ids"] = _groups_from_json(doc.get("group_ids"))
    doc["source_id"] = doc.get("source_id") or doc["id"]
    doc["version"] = doc.get("version") or 1
    doc["is_active"] = doc.get("is_active")
    if doc["is_active"] is None:
        doc["is_active"] = 1
    doc["tenant_id"] = doc.get("tenant_id") or "default"
    doc["owner_user_id"] = doc.get("owner_user_id") or "local"
    return doc


_SELECT_DOC = """
    SELECT d.*,
           (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
    FROM documents d
"""


async def insert_document(
    doc_id: str,
    filename: str,
    sha256: str | None,
    page_count: int,
    status: str,
    file_path: str | None,
    *,
    tenant_id: str = "default",
    owner_user_id: str = "local",
    group_ids: list[str] | None = None,
    source_id: str | None = None,
    version: int | None = None,
    is_active: int = 1,
) -> str:
    """插入文档行；source_id 缺省 = 自身 id（首个版本即源），version 缺省 1。"""
    source_id = source_id or doc_id
    version = 1 if version is None else version

    def _insert(c):
        c.execute(
            "INSERT INTO documents (id, filename, sha256, page_count, status, "
            "file_path, tenant_id, owner_user_id, group_ids, source_id, version, is_active) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                doc_id, filename, sha256, page_count, status, file_path,
                tenant_id, owner_user_id, _groups_to_json(group_ids),
                source_id, version, is_active,
            ),
        )

    await db.write(_insert)
    return doc_id


async def insert_version(
    source_doc_id: str,
    filename: str,
    sha256: str | None,
    file_path: str,
    new_id: str,
) -> str | None:
    """为 source 创建下一个版本（version=MAX+1 原子递增），is_active=0。"""
    def _insert(c):
        src = c.execute(
            "SELECT source_id, tenant_id, owner_user_id, group_ids FROM documents "
            "WHERE id=?",
            (source_doc_id,),
        ).fetchone()
        if src is None:
            return None
        max_v = c.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM documents WHERE source_id=?",
            (src["source_id"],),
        ).fetchone()["v"]
        c.execute(
            "INSERT INTO documents (id, filename, sha256, page_count, status, "
            "file_path, tenant_id, owner_user_id, group_ids, source_id, version, is_active) "
            "VALUES (?,?,?,0,'queued',?,?,?,?,?,?,0)",
            (
                new_id, filename, sha256, file_path,
                src["tenant_id"], src["owner_user_id"], src["group_ids"],
                src["source_id"], max_v + 1,
            ),
        )
        return new_id

    return await db.write(_insert)


async def promote_version(doc_id: str, source_id: str) -> None:
    """版本发布：旧 active 版本归档（is_active=0 + archived_at），新版本置 active。"""

    def _promote(c):
        c.execute(
            "UPDATE documents SET is_active=0, archived_at=datetime('now') "
            "WHERE source_id=? AND is_active=1 AND id<>?",
            (source_id, doc_id),
        )
        c.execute(
            "UPDATE documents SET is_active=1, archived_at=NULL WHERE id=?",
            (doc_id,),
        )

    await db.write(_promote)


async def get_document(doc_id: str) -> dict | None:
    row = db.query_one(_SELECT_DOC + "WHERE d.id=?", (doc_id,))
    return _row_to_doc(row) if row else None


async def list_documents(tenant_id: str | None = None) -> list[dict]:
    """按租户返回全部文档行（含归档版本）；可见性过滤在服务层完成。"""
    if tenant_id is None:
        rows = db.query(_SELECT_DOC + "ORDER BY d.created_at DESC")
    else:
        rows = db.query(
            _SELECT_DOC + "WHERE d.tenant_id=? ORDER BY d.created_at DESC",
            (tenant_id,),
        )
    return [_row_to_doc(r) for r in rows]


async def list_versions(source_id: str) -> list[dict]:
    rows = db.query(
        _SELECT_DOC + "WHERE d.source_id=? ORDER BY d.version",
        (source_id,),
    )
    return [_row_to_doc(r) for r in rows]


async def list_active_ids(tenant_id: str) -> list[dict]:
    """租户内所有 active 文档的最小行（ACL 检索范围计算用）。"""
    rows = db.query(
        "SELECT id, tenant_id, owner_user_id, group_ids FROM documents "
        "WHERE tenant_id=? AND is_active=1",
        (tenant_id,),
    )
    return [_row_to_doc(r) for r in rows]


async def list_by_statuses(statuses: tuple[str, ...]) -> list[dict]:
    ph = ",".join("?" * len(statuses))
    rows = db.query(_SELECT_DOC + f"WHERE d.status IN ({ph})", tuple(statuses))
    return [_row_to_doc(r) for r in rows]


async def update_status(
    doc_id: str,
    status: str,
    error: str | None = None,
    reason: str | None = None,
) -> None:
    """更新状态并写入 document_events 流转事件（同一事务）。

    已 cancelled 的文档拒绝再次流转（终态，除非显式 retry 认领）。
    """

    def _update(c):
        row = c.execute(
            "SELECT status, source_id, version FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        if row is None:
            return
        if row["status"] == "cancelled" and status != "cancelled":
            return
        c.execute(
            "UPDATE documents SET status=?, error=? WHERE id=?",
            (status, error, doc_id),
        )
        c.execute(
            "INSERT INTO document_events (document_id, source_id, version, "
            "from_status, to_status, reason, is_transient) VALUES (?,?,?,?,?,?,?)",
            (
                doc_id, row["source_id"], row["version"], row["status"], status,
                reason, 1 if status in TRANSIENT_STATUSES else 0,
            ),
        )

    await db.write(_update)


async def transition_status(
    doc_id: str, to_status: str, allowed_from: tuple[str, ...], error: str | None = None
) -> tuple[str, str] | None:
    """条件状态流转（cancel / retry 的原子认领）。

    返回 (result, from_status)：result ∈ {"ok", "conflict"}；文档不存在返回 None。
    """

    def _transition(c):
        row = c.execute(
            "SELECT status, source_id, version FROM documents WHERE id=?", (doc_id,)
        ).fetchone()
        if row is None:
            return None
        if row["status"] not in allowed_from:
            return ("conflict", row["status"])
        c.execute(
            "UPDATE documents SET status=?, error=? WHERE id=?",
            (to_status, error, doc_id),
        )
        c.execute(
            "INSERT INTO document_events (document_id, source_id, version, "
            "from_status, to_status, reason, is_transient) VALUES (?,?,?,?,?,?,?)",
            (
                doc_id, row["source_id"], row["version"], row["status"], to_status,
                None, 1 if to_status in TRANSIENT_STATUSES else 0,
            ),
        )
        return ("ok", row["status"])

    return await db.write(_transition)


async def update_page_count(doc_id: str, page_count: int) -> None:
    await db.write(
        lambda c: c.execute(
            "UPDATE documents SET page_count=? WHERE id=?", (page_count, doc_id)
        )
    )


async def update_acl(
    doc_id: str, owner_user_id: str, groups: list[str]
) -> bool:
    """更新属主与授权组，返回文档是否存在。"""

    def _update(c):
        cur = c.execute(
            "UPDATE documents SET owner_user_id=?, group_ids=? WHERE id=?",
            (owner_user_id, _groups_to_json(groups), doc_id),
        )
        return cur.rowcount > 0

    return await db.write(_update)


async def get_status(doc_id: str) -> str | None:
    row = db.query_one("SELECT status FROM documents WHERE id=?", (doc_id,))
    return row["status"] if row else None


async def delete_document(doc_id: str) -> None:
    """事务内同步清理：FTS 条目 + 分块 + 事件 + 文档行（防孤儿 chunk 竞态）。"""

    def _delete(c):
        c.execute(
            "DELETE FROM chunk_fts WHERE rowid IN "
            "(SELECT id FROM chunks WHERE document_id=?)",
            (doc_id,),
        )
        c.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
        c.execute("DELETE FROM document_events WHERE document_id=?", (doc_id,))
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))

    await db.write(_delete)
