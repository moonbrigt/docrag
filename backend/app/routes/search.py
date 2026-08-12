"""检索调试路由：非流式返回混合检索 + 重排候选。

供前端调试与评测对照使用（Spec §5 POST /search）。
检索范围按 ACL fail-closed（空范围返回空结果）；rerank 未就绪时 503 明确报错，
不静默降级。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app import auth
from app.core.errors import ModelNotReadyError
from app.core.logging import get_logger
from app.core.metrics import get_metrics
from app.schemas import SearchRequest
from app.services import rerank_service, retrieve_service

router = APIRouter(prefix="/api/v1", tags=["search"])
_log = get_logger("docrag.routes.search")


@router.post("/search")
async def search(
    req: SearchRequest,
    principal: auth.Principal = Depends(auth.get_principal),
):
    import time

    start = time.perf_counter()
    try:
        retrieved = await retrieve_service.hybrid_retrieve(
            req.query, req.document_ids, principal
        )
    except ModelNotReadyError as exc:
        get_metrics().incr("errors_total")
        raise HTTPException(status_code=503, detail=str(exc))

    if req.rerank:
        if not rerank_service.is_ready():
            get_metrics().incr("errors_total")
            raise HTTPException(
                status_code=503,
                detail="重排模型未就绪，已按 fail-closed 拒绝检索。请配置权重或开启 RAG_RERANK_MOCK。",
            )
        try:
            retrieved = await rerank_service.rerank(req.query, retrieved, req.top_k)
        except ModelNotReadyError as exc:
            get_metrics().incr("errors_total")
            raise HTTPException(status_code=503, detail=str(exc))
    else:
        retrieved = retrieved[: req.top_k]

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    get_metrics().observe("retrieve_latency_ms", elapsed_ms)
    _log.info(
        "search.done",
        extra={
            "query_len": len(req.query),
            "rerank": req.rerank,
            "count": len(retrieved),
            "ms": round(elapsed_ms, 2),
        },
    )
    return {
        "query": req.query,
        "rerank": req.rerank,
        "count": len(retrieved),
        "results": [r.model_dump() for r in retrieved],
    }
