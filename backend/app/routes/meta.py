"""运维路由：健康检查与双后端就绪状态（Spec §5 GET /health, /config/backends）。"""
from __future__ import annotations

from fastapi import APIRouter

from app import db
from app.core.metrics import get_metrics
from app.schemas import BackendItem, BackendStatus, HealthOut
from app.services import index_service, rerank_service
from app.core.llm import LLMClient

router = APIRouter(prefix="/api/v1", tags=["meta"])
_llm = LLMClient()


@router.get("/health", response_model=HealthOut)
async def health():
    try:
        db.query_one("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    eb, eready = index_service.get_embedder().status()
    rb, rready = rerank_service.get_reranker().status()
    lb, lready = _llm.status()
    models = {
        "embed": {"backend": eb, "status": "ready" if eready else "loading"},
        "rerank": {"backend": rb, "status": "ready" if rready else "loading"},
        "llm": {"backend": lb, "status": "ready" if lready else "loading"},
    }
    return {"status": "ok" if db_ok else "degraded", "db": db_ok, "models": models}


@router.get("/config/backends", response_model=BackendStatus)
async def backends():
    eb, eready = index_service.get_embedder().status()
    rb, rready = rerank_service.get_reranker().status()
    lb, lready = _llm.status()
    return BackendStatus(
        llm=BackendItem(
            backend=lb,
            ready=lready,
            detail="Ollama/OpenAI 兼容端点已配置" if lready else "未配置 RAG_LLM_BACKEND 或 Mock",
        ),
        rerank=BackendItem(
            backend=rb,
            ready=rready,
            detail="bge-reranker-v2-m3 已加载" if rready else "权重未就绪或 Mock",
        ),
        embedding=BackendItem(
            backend=eb,
            ready=eready,
            detail="bge-m3 已加载" if eready else "权重未就绪或 Mock",
        ),
    )


@router.get("/metrics")
async def metrics():
    """导出进程内可观测性指标（计数器 + 延迟直方图）。"""
    return get_metrics().snapshot()
