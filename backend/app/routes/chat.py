"""问答路由：SSE 流式生成，带页码引用（Spec §5 POST /chat）。

事件协议（前端按此契约对接）：
- event: stage    data: {"stage": "retrieving"|"reranking"|"generating"}  阶段开始
- event: delta    data: {"text": "..."}  文本增量（缓冲校验后泄出）
- event: citation data: {index,docId,docName,page,bbox?,snippet?,sourceId?,version?,title?,createdAt?,processingMs?}
- event: no_answer data: {"reason": "no_evidence"|"not_supported", "evidence_candidates": [...]}
                  （仅无有效证据时发，且之前不得有 delta/citation）
- event: done     data: {"selected_document_ids": [...], "trace_id": "..."}
- event: error    data: {"message": "..."}
内部事件 trace 由本路由拦截落库，不转发给前端。
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app import auth
from app.core.logging import get_logger
from app.core.metrics import get_metrics
from app.schemas import ChatRequest
from app.services import document_service, generate_service, trace_service

router = APIRouter(prefix="/api/v1", tags=["chat"])
_log = get_logger("docrag.routes.chat")


@router.post("/chat")
async def chat(
    req: ChatRequest,
    principal: auth.Principal = Depends(auth.get_principal),
):
    if not req.query or not req.query.strip():
        get_metrics().incr("errors_total")
        raise HTTPException(status_code=400, detail="query 不能为空")

    # 检索范围为空（空知识库 / 无可见文档 / 显式空范围）：明确 409，不进 SSE
    scope = await document_service.resolve_scope(principal, req.document_ids)
    if not scope:
        get_metrics().incr("errors_total")
        raise HTTPException(
            status_code=409,
            detail="知识库为空或当前账号无可访问的文档，请先上传文档后再提问。",
        )

    get_metrics().incr("queries_total")
    trace_id = uuid.uuid4().hex
    start = time.perf_counter()
    citation_count = 0

    async def event_gen():
        nonlocal citation_count
        try:
            async for etype, payload in generate_service.stream_answer(
                req.query, req.document_ids, req.rerank, principal, trace_id
            ):
                if etype == "stage":
                    yield f"event: stage\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif etype == "delta":
                    yield f"event: delta\ndata: {json.dumps({'text': payload}, ensure_ascii=False)}\n\n"
                elif etype == "citation":
                    citation_count += 1
                    yield f"event: citation\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif etype == "no_answer":
                    yield f"event: no_answer\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif etype == "done":
                    yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif etype == "trace":
                    # 内部事件：落库追踪，不转发给前端
                    await trace_service.save_trace(payload)
                elif etype == "error":
                    yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            get_metrics().incr("citations_returned_total", citation_count)
            get_metrics().observe("llm_latency_ms", elapsed_ms)
            _log.info(
                "chat.completed",
                extra={
                    "trace_id": trace_id,
                    "query_len": len(req.query),
                    "citations": citation_count,
                    "ms": round(elapsed_ms, 2),
                },
            )

    return StreamingResponse(event_gen(), media_type="text/event-stream")
