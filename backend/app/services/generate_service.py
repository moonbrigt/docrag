"""生成服务：组装 prompt + 双后端 LLM 流式生成 + 引用装配 + 无答案判定。

产出为 SSE 事件异步生成器，逐块 yield (event_type, payload)：
- ("stage", {stage})        阶段开始：retrieving / reranking / generating
- ("delta", text)           文本增量（先缓冲，校验存在有效引用后才泄出）
- ("citation", dict)        引用事件（docId/docName/page/bbox/snippet/sourceId/version…）
- ("no_answer", dict)       无有效证据（no_evidence）或无有效引用（not_supported）
- ("done", dict)            {selected_document_ids, trace_id}
- ("error", {message})      错误（检索空 / 模型未就绪 / LLM 失败）
- ("trace", dict)           管道追踪载荷（路由拦截落库，不转发给前端）

证据质量（P0）：
- 零分候选（faiss/fts 均无正分）不进入证据列表，更不冒充证据。
- rerank 请求但模型未就绪时 fail-closed（明确错误，不静默降级为截断）。
- 生成内容整体缓冲；无有效引用时以 no_answer 收尾，之前绝不泄出 delta。
"""
from __future__ import annotations

import time

from app import auth
from app.config import get_settings
from app.core.errors import ModelNotReadyError
from app.core.llm import LLMClient
from app.schemas import RetrievedChunk
from app.services import (
    citation_service,
    index_service,
    rerank_service,
    retrieve_service,
)

_settings = get_settings()
_llm = LLMClient()

SYS_PROMPT = (
    "你是严谨的文档问答助手。请严格依据下方提供的上下文回答用户问题，"
    "并在支撑句末用 [n] 标注引用编号，n 对应上下文的序号。"
    "若上下文不足以回答，请明确说明“根据现有文档无法回答该问题”。"
    "不要编造上下文之外的信息。"
)


def _build_prompt(query: str, ordered: list[RetrievedChunk]):
    ctx_lines: list[str] = []
    mock_ctx: list[dict] = []
    for i, rc in enumerate(ordered, start=1):
        ctx_lines.append(f"[{i}] (《{rc.doc_name}》第{rc.page_no}页) {rc.snippet}")
        mock_ctx.append({"index": i, "page": rc.page_no, "snippet": rc.snippet})
    user = "上下文：\n" + "\n".join(ctx_lines) + "\n\n问题：" + query
    return SYS_PROMPT, user, mock_ctx


def _has_signal(rc: RetrievedChunk) -> bool:
    """候选是否有真实检索信号（拒绝零分候选冒充证据）。"""
    return (rc.faiss_score or 0) > 0 or (rc.fts_score or 0) > 0


def _evidence_payload(chunk: RetrievedChunk) -> dict:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "doc_name": chunk.doc_name,
        "page_no": chunk.page_no,
        "snippet": chunk.snippet,
        "rrf_score": round(chunk.rrf_score, 6),
        "faiss_score": chunk.faiss_score,
        "fts_score": chunk.fts_score,
    }


def _provenance() -> dict:
    eb, _ = index_service.get_embedder().status()
    rb, _ = rerank_service.get_reranker().status()
    lb, _ = _llm.status()
    return {
        "embedding": eb,
        "rerank": rb,
        "llm": lb,
        "llm_model": _settings.LLM_MODEL,
    }


async def stream_answer(
    query: str,
    document_ids: list[str] | None = None,
    rerank: bool = True,
    principal: auth.Principal | None = None,
    trace_id: str = "unknown",
):
    principal = principal or auth.default_principal()
    t0 = time.perf_counter()
    trace: dict = {
        "trace_id": trace_id,
        "tenant_id": principal.tenant_id,
        "user_id": principal.user_id,
        "query_hash": "not_stored",  # 隐私契约：query 原文与可反查哈希一律不落库
        "rerank_used": bool(rerank),
        "evidence": [],
        "citations": [],
        "selected_document_ids": [],
        "stage_timings": {},
        "model_provenance": _provenance(),
        "status": "ok",
        "error_message": None,
    }

    def finish(status: str, error: str | None = None):
        trace["status"] = status
        trace["error_message"] = error
        trace["stage_timings"]["total_ms"] = round(
            (time.perf_counter() - t0) * 1000.0, 2
        )
        return ("trace", dict(trace))

    yield ("stage", {"stage": "retrieving"})
    try:
        retrieved = await retrieve_service.hybrid_retrieve(query, document_ids, principal)
    except ModelNotReadyError as exc:
        yield ("error", {"message": str(exc)})
        yield finish("error", str(exc))
        return
    t_retrieving = (time.perf_counter() - t0) * 1000.0

    # 过滤零分候选；无信号 -> no_answer（LLM 不调用）
    evidence = [rc for rc in retrieved if _has_signal(rc)]
    trace["evidence"] = [_evidence_payload(rc) for rc in evidence]
    trace["stage_timings"]["retrieving_ms"] = round(t_retrieving, 2)
    if not evidence:
        yield (
            "no_answer",
            {"reason": "no_evidence", "evidence_candidates": []},
        )
        yield ("done", {"selected_document_ids": [], "trace_id": trace_id})
        yield finish("no_answer")
        return

    if rerank:
        yield ("stage", {"stage": "reranking"})
        if not rerank_service.is_ready():
            backend, _ = rerank_service.get_reranker().status()
            message = (
                f"重排模型未就绪（{backend}），已按 fail-closed 拒绝本次问答。"
                "请配置 bge-reranker-v2-m3 权重或开启 RAG_RERANK_MOCK。"
            )
            yield ("error", {"message": message})
            yield finish("error", message)
            return
        try:
            ordered = await rerank_service.rerank(query, evidence)
        except ModelNotReadyError as exc:
            yield ("error", {"message": str(exc)})
            yield finish("error", str(exc))
            return
    else:
        ordered = evidence[:_settings.RERANK_TOP_K]
    t_reranking = (time.perf_counter() - t0) * 1000.0
    trace["stage_timings"]["reranking_ms"] = round(t_reranking, 2)

    yield ("stage", {"stage": "generating"})
    if not _llm.is_ready():
        backend, _ = _llm.status()
        message = (
            f"LLM 后端未就绪（{backend}）。请配置 Ollama 或 OpenAI 兼容端点，"
            "或开启 RAG_LLM_MOCK。"
        )
        yield ("error", {"message": message})
        yield finish("error", message)
        return

    sys_p, user_p, mock_ctx = _build_prompt(query, ordered)
    full: list[str] = []
    try:
        async for delta in _llm.stream(SYS_PROMPT, user_p, mock_context=mock_ctx):
            full.append(delta)
    except RuntimeError as exc:
        message = str(exc)
        yield ("error", {"message": message})
        yield finish("error", message)
        return
    t_generating = (time.perf_counter() - t0) * 1000.0
    trace["stage_timings"]["generating_ms"] = round(t_generating, 2)

    # 缓冲校验：无有效引用 -> no_answer(not_supported)，绝不泄出无支撑 delta
    text = "".join(full)
    citations = citation_service.build_citations(
        text, ordered, processing_ms=(time.perf_counter() - t0) * 1000.0
    )
    if not citations:
        yield (
            "no_answer",
            {
                "reason": "not_supported",
                "evidence_candidates": [_evidence_payload(rc) for rc in ordered],
            },
        )
        yield ("done", {"selected_document_ids": [], "trace_id": trace_id})
        yield finish("no_answer")
        return

    yield ("delta", text)
    for c in citations:
        yield ("citation", c)
    selected = sorted({c["docId"] for c in citations})
    trace["citations"] = citations
    trace["selected_document_ids"] = selected
    yield ("done", {"selected_document_ids": selected, "trace_id": trace_id})
    yield finish("ok")
