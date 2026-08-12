"""API 请求/响应数据模型（pydantic v2）。

仅描述契约，不含业务逻辑。字段命名与 Spec §5/§6 对齐。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------- 文档 ----------------
class DocumentOut(BaseModel):
    id: str
    filename: str
    sha256: Optional[str] = None
    page_count: int = 0
    status: str
    error: Optional[str] = None
    created_at: Optional[str] = None
    chunk_count: int = 0
    # 成熟度：ACL 与生命周期
    tenant_id: str = "default"
    owner_user_id: str = "local"
    group_ids: list[str] = []
    source_id: Optional[str] = None
    version: int = 1
    is_active: int = 1
    archived_at: Optional[str] = None


class DocumentDetailOut(BaseModel):
    document: DocumentOut
    chunks: list["ChunkOut"]


class ChunkOut(BaseModel):
    id: int
    document_id: str
    seq: int
    content: str
    page_no: int
    bbox: Optional[dict] = None
    section: Optional[str] = None


# ---------------- 生命周期操作 ----------------
class StatusOut(BaseModel):
    document_id: str
    status: str


class VersionCreateOut(BaseModel):
    document_id: str
    version: int
    status: str


# ---------------- ACL ----------------
class AclPayload(BaseModel):
    """GET/PUT /documents/{id}/acl 同构体。PUT 时 tenant_id 不可修改（忽略）。"""

    tenant_id: str
    owner_user_id: str
    groups: list[str] = []


# ---------------- 检索 ----------------
class RetrievedChunk(BaseModel):
    chunk_id: int
    document_id: str
    doc_name: str
    seq: int
    page_no: int
    bbox: Optional[dict] = None
    section: Optional[str] = None
    snippet: str
    rrf_score: float
    faiss_score: Optional[float] = None
    fts_score: Optional[float] = None
    # 成熟度：citation 元数据（sourceId/version/title/createdAt）
    source_id: Optional[str] = None
    version: Optional[int] = None
    title: Optional[str] = None
    created_at: Optional[str] = None


# ---------------- 请求体 ----------------
class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户问题，空查询不触发检索")
    document_ids: Optional[list[str]] = None
    rerank: bool = True


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    rerank: bool = True
    document_ids: Optional[list[str]] = None


class EvaluationRunRequest(BaseModel):
    config: Optional[dict] = None


# ---------------- 反馈 / 追踪 ----------------
class FeedbackIn(BaseModel):
    trace_id: str = Field(..., min_length=1)
    # 兼容两种提交形式：rating 枚举（旧契约）或 useful 布尔（前端实现）
    rating: Optional[Literal["useful", "not_useful"]] = None
    useful: Optional[bool] = None
    issue_type: Optional[
        Literal["wrong_source", "unsupported", "stale", "missing", "bad_answer"]
    ] = None
    selected_text: Optional[str] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def _resolve_rating(self):
        if self.rating is None and self.useful is not None:
            self.rating = "useful" if self.useful else "not_useful"
        if self.rating is None:
            raise ValueError("rating 或 useful 至少提供一个")
        return self


class TraceOut(BaseModel):
    trace_id: str
    created_at: Optional[str] = None
    query_hash: str = "not_stored"
    status: str
    rerank_used: bool = False
    selected_document_ids: list[str] = []
    evidence: list[dict] = []
    citations: list[dict] = []
    stage_timings: dict = {}
    model_provenance: dict = {}
    error_message: Optional[str] = None


# ---------------- 后端状态 / 健康 ----------------
class BackendItem(BaseModel):
    backend: str
    ready: bool
    detail: str = ""


class BackendStatus(BaseModel):
    llm: BackendItem
    rerank: BackendItem
    embedding: BackendItem


class HealthOut(BaseModel):
    status: str
    db: bool
    models: dict


# ---------------- 评测报告 ----------------
class EvaluationReport(BaseModel):
    metrics: dict
    per_query: list[dict]
    config: dict
