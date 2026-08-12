"""追踪与反馈路由：POST /feedback 与 GET /trace/{trace_id}。

- trace 只对同租户同用户（或管理员）可见，其余一律 404（不泄露存在性）。
- feedback 提交前校验 trace 归属；query 原文与可反查哈希不落库。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import auth
from app.core.logging import get_logger
from app.schemas import FeedbackIn, TraceOut
from app.services import trace_service

router = APIRouter(prefix="/api/v1", tags=["trace"])
_log = get_logger("docrag.routes.trace")


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackIn,
    principal: auth.Principal = Depends(auth.get_principal),
):
    await trace_service.submit_feedback(
        req.trace_id,
        principal,
        rating=req.rating,
        issue_type=req.issue_type,
        selected_text=req.selected_text,
        comment=req.comment,
    )
    return {"ok": True}


@router.get("/trace/{trace_id}", response_model=TraceOut)
async def get_trace(
    trace_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    trace = await trace_service.get_trace(trace_id, principal)
    if not trace:
        raise HTTPException(status_code=404, detail=f"追踪记录不存在：{trace_id}")
    return trace
