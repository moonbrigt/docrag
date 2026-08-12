"""追踪与反馈数据访问层（trace / feedback 表）。

隐私契约：query 原文及可反查哈希一律不落库，query_hash 固定 "not_stored"。
JSON 字段（evidence/citations/selected_document_ids/…）以文本存储，读取时解析。
"""
from __future__ import annotations

import json

from app import db


def _dumps(value) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


async def insert_trace(payload: dict) -> None:
    """落库一条管道追踪记录（payload 由服务层组装）。"""

    def _insert(c):
        c.execute(
            "INSERT INTO trace (trace_id, tenant_id, user_id, query_hash, status, "
            "rerank_used, selected_document_ids, evidence, citations, "
            "stage_timings, model_provenance, error_message) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                payload["trace_id"],
                payload["tenant_id"],
                payload["user_id"],
                payload.get("query_hash", "not_stored"),
                payload["status"],
                1 if payload.get("rerank_used") else 0,
                _dumps(payload.get("selected_document_ids", [])),
                _dumps(payload.get("evidence", [])),
                _dumps(payload.get("citations", [])),
                _dumps(payload.get("stage_timings", {})),
                _dumps(payload.get("model_provenance", {})),
                payload.get("error_message"),
            ),
        )

    await db.write(_insert)


async def get_trace(trace_id: str) -> dict | None:
    row = db.query_one("SELECT * FROM trace WHERE trace_id=?", (trace_id,))
    if not row:
        return None
    return {
        "trace_id": row["trace_id"],
        "created_at": row["created_at"],
        "tenant_id": row["tenant_id"],
        "user_id": row["user_id"],
        "query_hash": row["query_hash"],
        "status": row["status"],
        "rerank_used": bool(row["rerank_used"]),
        "selected_document_ids": _loads(row["selected_document_ids"], []),
        "evidence": _loads(row["evidence"], []),
        "citations": _loads(row["citations"], []),
        "stage_timings": _loads(row["stage_timings"], {}),
        "model_provenance": _loads(row["model_provenance"], {}),
        "error_message": row["error_message"],
    }


async def insert_feedback(
    trace_id: str,
    rating: str,
    issue_type: str | None,
    selected_text: str | None,
    comment: str | None,
) -> None:
    def _insert(c):
        c.execute(
            "INSERT INTO feedback (trace_id, rating, issue_type, selected_text, comment) "
            "VALUES (?,?,?,?,?)",
            (trace_id, rating, issue_type, selected_text, comment),
        )

    await db.write(_insert)
