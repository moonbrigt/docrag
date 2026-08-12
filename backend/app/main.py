"""DocRAG 后端入口。

职责（仅装配，零业务逻辑）：
- 启动时初始化 SQLite 并从持久化重建 FAISS 内存索引。
- 注册路由与 CORS 中间件（前后端分离部署必备）。
- 暴露 ASGI app 供 uvicorn / gunicorn 拉起。
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.core.logging import configure_logging, get_logger
from app.core.metrics import get_metrics
from app.core import runtime_config
from app.routes import chat, config, documents, evaluation, meta, search, trace
from app.services import document_service, index_service

_log = get_logger("docrag.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    db.init_db()
    # 加载运行时配置覆盖（设置页写回，优先于 env 默认值）
    runtime_config.load_runtime_config()
    # 启动重建内存向量索引，保证与 SQLite 持久化一致
    await index_service.rebuild_faiss()
    # 启动恢复：瞬态状态（queued/parsing/chunking/embedding）-> failed
    # （reason=service_restart_interrupted），并清理 partial chunks
    await document_service.recover_interrupted()
    _log.info("startup.done")
    yield


app = FastAPI(title="DocRAG", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """记录每个请求的方法/路径/状态码/耗时，并暴露到指标。"""
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        get_metrics().observe("http_request_latency_ms", elapsed_ms)
        _log.info(
            "request.handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": round(elapsed_ms, 2),
            },
        )


def _cors_origins() -> list[str]:
    env = os.getenv("RAG_CORS_ORIGINS")
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]
    if env:
        defaults.extend([o.strip() for o in env.split(",") if o.strip()])
    return defaults


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # 安全约束：allow_headers 不得包含 X-Rag-*（身份头只允许可信反向代理
    # 注入，浏览器无法伪造）。RAG_TRUSTED_PROXY=true 时 nginx 负责设置。
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(documents.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(meta.router)
app.include_router(trace.router)
app.include_router(evaluation.router)
app.include_router(config.router)


@app.get("/")
async def root():
    return {"service": "DocRAG", "docs": "/docs", "api_prefix": "/api/v1"}
