"""追踪与反馈服务：管道 trace 落库 / 查询（ACL 过滤）与 feedback 提交。

隐私契约：query 原文与可反查哈希一律不落库（query_hash 固定 "not_stored"）。
trace 访问控制：仅同租户同用户或管理员可读；feedback 提交同理。
"""
from __future__ import annotations

from app import auth
from app.repositories import trace_repo


async def save_trace(payload: dict) -> None:
    """由 chat 路由拦截 ("trace", payload) 事件时调用，落库后不转发前端。"""
    await trace_repo.insert_trace(payload)


async def get_trace(trace_id: str, principal: auth.Principal) -> dict | None:
    row = await trace_repo.get_trace(trace_id)
    if not row:
        return None
    owner_ok = (
        row["tenant_id"] == principal.tenant_id and row["user_id"] == principal.user_id
    )
    if not owner_ok and not principal.is_admin():
        return None
    return row


async def submit_feedback(
    trace_id: str,
    principal: auth.Principal,
    rating: str,
    issue_type: str | None = None,
    selected_text: str | None = None,
    comment: str | None = None,
) -> None:
    """提交反馈：先校验 trace 存在且对当前身份可见（无权限抛 404，不泄露存在性）。"""
    row = await get_trace(trace_id, principal)
    if not row:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"追踪记录不存在：{trace_id}")
    await trace_repo.insert_feedback(trace_id, rating, issue_type, selected_text, comment)
