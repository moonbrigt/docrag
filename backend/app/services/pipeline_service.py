"""流水线服务：上传后异步执行 解析 -> 分块 -> 嵌入 -> 索引，并更新状态机。

状态机：queued -> parsing -> chunking -> embedding -> indexed
                          -> warning（部分阶段成功但有问题，分块保留可检索）
                          -> failed（清理 partial chunks）
                          -> cancelled（终态，停止后续阶段）

设计说明：
- Docling 解析在独立线程（asyncio.to_thread）执行，API 不被解析阻塞。
- 取消无法强杀进行中的原生 OCR / 解析线程（原生代码不在事件循环内），
  只能通过阶段间的状态守卫停止后续阶段——这是文档化限制。
- 每个阶段前检查文档是否仍存活（存在且未被取消），已取消则不继续流转。
- 版本替换：promote_on_success=True 时，索引成功后才把旧 active 版本归档。
"""
from __future__ import annotations

import asyncio
import hashlib
import time

from app.core.errors import ModelNotReadyError, PipelineError
from app.core.logging import get_logger
from app.core.metrics import get_metrics
from app.core.parser import ParseService
from app.repositories import chunk_repo, document_repo
from app.services import document_service, index_service

_parser = ParseService()
_log = get_logger("docrag.pipeline")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _alive(doc_id: str) -> bool:
    """文档仍存活：存在且未被取消。"""
    status = await document_repo.get_status(doc_id)
    return status is not None and status != "cancelled"


async def _fail(doc_id: str, message: str) -> None:
    """置 failed 并清理 partial chunks（不覆盖已取消的终态）。"""
    await document_repo.update_status(doc_id, "failed", message)
    if await _alive(doc_id):
        await document_service.cleanup_partial_chunks(doc_id)


async def _warn(doc_id: str, message: str) -> None:
    """置 warning：部分阶段成功（分块已落库）但有问题，保留分块供重试。"""
    await document_repo.update_status(doc_id, "warning", message)


async def run_pipeline(
    doc_id: str,
    file_bytes: bytes,
    filename: str,
    source_path,
    promote_on_success: bool = False,
) -> int:
    """执行完整索引流水线，返回写入的分块数。异常时置文档 failed/warning。"""
    start = time.perf_counter()
    try:
        if not await _alive(doc_id):
            return 0
        await document_repo.update_status(doc_id, "parsing")

        # Docling 解析放线程池：API 不被解析阻塞；取消无法强杀进行中的
        # 原生解析线程，只能等待其返回后由阶段守卫停止。
        result = await asyncio.to_thread(
            _parser.parse, file_bytes, filename, source_path
        )
        if not await _alive(doc_id):
            return 0
        await document_repo.update_page_count(doc_id, result.page_count)
        if not result.chunks:
            raise PipelineError("解析结果为空，没有可索引的分块")

        await document_repo.update_status(doc_id, "chunking")
        if not await _alive(doc_id):
            return 0
        await document_repo.update_status(doc_id, "embedding")
        if not await _alive(doc_id):
            return 0

        n = await index_service.index_parsed_chunks(doc_id, result.chunks)
        if not await _alive(doc_id):
            # 索引期间被取消：清理刚写入的 partial chunks
            await document_service.cleanup_partial_chunks(doc_id)
            return 0

        await document_repo.update_status(doc_id, "indexed")
        if promote_on_success:
            await _promote(doc_id)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        get_metrics().incr("documents_indexed_total")
        get_metrics().observe("pipeline_latency_ms", elapsed_ms)
        _log.info(
            "pipeline.indexed",
            extra={"doc_id": doc_id, "chunks": n, "ms": round(elapsed_ms, 2)},
        )
        return n
    except ModelNotReadyError as exc:
        await _fail(doc_id, str(exc))
        get_metrics().incr("documents_failed_total")
        _log.warning(
            "pipeline.failed", extra={"doc_id": doc_id, "reason": "model_not_ready"}
        )
        raise
    except PipelineError as exc:
        await _fail(doc_id, str(exc))
        get_metrics().incr("documents_failed_total")
        _log.warning("pipeline.failed", extra={"doc_id": doc_id, "reason": str(exc)})
        raise
    except Exception as exc:  # 嵌入 / 落库 / FAISS 重建失败
        message = str(exc)
        # 分块已部分落库 -> warning（部分阶段成功，保留可检索分块）；否则 failed
        if await chunk_repo.count_chunks_for_doc(doc_id) > 0:
            await _warn(doc_id, message)
            _log.warning(
                "pipeline.warning",
                extra={"doc_id": doc_id, "reason": message, "partial": True},
            )
        else:
            await _fail(doc_id, message)
            get_metrics().incr("documents_failed_total")
            _log.warning("pipeline.failed", extra={"doc_id": doc_id, "reason": message})
        raise PipelineError(message)


async def _promote(doc_id: str) -> None:
    """版本发布：把同 source 的旧 active 版本归档，当前版本置 active。"""
    doc = await document_repo.get_document(doc_id)
    if not doc:
        return
    await document_repo.promote_version(doc_id, doc["source_id"])
    _log.info("pipeline.version_promoted", extra={"doc_id": doc_id, "source_id": doc["source_id"]})
