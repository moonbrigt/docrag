"""文档服务：ACL 感知的列表 / 详情 / 删除 / 原文文件 + 生命周期操作。

- 可见性 fail-closed：无权限一律 404 / 空结果，不泄露文档存在性。
- 删除：事务内清 FTS + chunks + events + 文档行，随后重建 FAISS 并删物理文件。
- 生命周期：cancel（终态停止）/ retry（原子认领 + 清理 partial）/ 版本替换。
- 启动恢复：瞬态状态（queued/parsing/chunking/embedding）→ failed
  （reason=service_restart_interrupted），并清理 partial chunks。
"""
from __future__ import annotations

import pathlib

from fastapi import HTTPException

from app import auth
from app.config import get_settings
from app.core.logging import get_logger
from app.repositories import chunk_repo, document_repo
from app.services import index_service
from app.schemas import AclPayload

_log = get_logger("docrag.document_service")


# ---------------- 可见性 ----------------
async def list_visible_document_ids(principal: auth.Principal) -> set[str]:
    """当前身份可见（且 active）的文档 id 集合——检索范围的基础。"""
    rows = await document_repo.list_active_ids(principal.tenant_id)
    return {r["id"] for r in rows if auth.doc_visible(principal, r)}


async def resolve_scope(
    principal: auth.Principal, document_ids: list[str] | None
) -> set[str]:
    """解析检索范围：None=全部可见；[]=显式空范围（零结果）；其余=交集。"""
    visible = await list_visible_document_ids(principal)
    if document_ids is None:
        return visible
    if not document_ids:
        return set()
    return visible & set(document_ids)


async def get_visible_document(
    doc_id: str, principal: auth.Principal
) -> dict | None:
    """按 ACL 过滤的文档详情；无权限/不存在均返回 None（404，不泄露存在性）。"""
    doc = await document_repo.get_document(doc_id)
    if not doc or not auth.doc_visible(principal, doc):
        return None
    return doc


async def get_manageable_document(
    doc_id: str, principal: auth.Principal
) -> dict | None:
    """按管理权限过滤（删除 / ACL 修改 / cancel / retry / 版本替换）。"""
    doc = await document_repo.get_document(doc_id)
    if not doc or not auth.doc_manageable(principal, doc):
        return None
    return doc


async def list_documents(principal: auth.Principal) -> list[dict]:
    rows = await document_repo.list_documents(principal.tenant_id)
    return [r for r in rows if auth.doc_visible(principal, r)]


async def find_duplicate(sha256: str, principal: auth.Principal) -> dict | None:
    """上传去重：同租户、对当前身份可见、仍在服役的同内容文档；不存在返回 None。

    不可见的重复不返回（fail-closed：不泄露无权文档的存在性）。
    """
    rows = await document_repo.find_active_by_sha(sha256, principal.tenant_id)
    return next((r for r in rows if auth.doc_visible(principal, r)), None)


async def get_chunks(doc_id: str) -> list[dict]:
    return await chunk_repo.list_chunks_by_doc(doc_id)


# ---------------- 删除 ----------------
async def delete_document(doc_id: str, principal: auth.Principal) -> None:
    """删除文档（含同步清理向量/FTS/文件），仅 owner/管理员。"""
    doc = await get_manageable_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    # DB 侧在同一事务内清理 chunk_fts + chunks + events + 文档行
    await document_repo.delete_document(doc_id)
    # 内存 FAISS 与物理文件在事务提交后清理
    await index_service.rebuild_faiss()
    raw_path = doc.get("file_path")
    if raw_path:
        try:
            pathlib.Path(raw_path).unlink(missing_ok=True)
        except OSError as exc:  # pragma: no cover - 文件系统异常不影响主流程
            _log.warning("delete.file_failed", extra={"doc_id": doc_id, "exc": str(exc)})


async def get_document_file(
    doc_id: str, principal: auth.Principal
) -> tuple[str, str] | None:
    """ACL 过滤的原文文件定位；记录/文件缺失或无权时返回 None。"""
    doc = await get_visible_document(doc_id, principal)
    if not doc:
        return None
    raw_path = doc.get("file_path")
    if not raw_path:
        return None
    path = pathlib.Path(raw_path)
    if not path.is_file():
        return None
    return str(path), doc["filename"]


# ---------------- 生命周期 ----------------
async def cancel_document(doc_id: str, principal: auth.Principal) -> dict:
    """取消文档：仅瞬态（queued/parsing/chunking/embedding）可取消。"""
    doc = await get_manageable_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    result = await document_repo.transition_status(
        doc_id, "cancelled", document_repo.TRANSIENT_STATUSES
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    kind, from_status = result
    if kind == "conflict":
        raise HTTPException(
            status_code=409,
            detail=f"文档当前状态 {from_status} 不可取消（仅处理中的文档可取消）",
        )
    await cleanup_partial_chunks(doc_id)
    return {"document_id": doc_id, "status": "cancelled"}


async def retry_document(
    doc_id: str, principal: auth.Principal
) -> tuple[str, str, bytes]:
    """原子认领重试：failed/warning/cancelled -> queued，返回 (id, filename, bytes)。

    认领成功后调用方负责清理 partial chunks 并重新跑流水线。
    """
    doc = await get_manageable_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    # 先确认原文文件存在，再原子认领（避免认领后才发现文件缺失卡在 queued）
    raw_path = doc.get("file_path")
    if not raw_path or not pathlib.Path(raw_path).is_file():
        raise HTTPException(
            status_code=409, detail="原文文件缺失，无法重试，请重新上传"
        )
    result = await document_repo.transition_status(
        doc_id, "queued", document_repo.RETRYABLE_STATUSES
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    kind, from_status = result
    if kind == "conflict":
        raise HTTPException(
            status_code=409,
            detail=f"文档当前状态 {from_status} 不可重试（仅 failed/warning/cancelled）",
        )
    data = pathlib.Path(raw_path).read_bytes()
    return doc_id, doc["filename"], data


async def cleanup_partial_chunks(doc_id: str) -> None:
    """取消/失败/重试时清理该文档版本的 partial chunks 与 FAISS 条目。"""
    await chunk_repo.delete_chunks_by_doc(doc_id)
    await index_service.rebuild_faiss()


async def create_version(
    doc_id: str, filename: str, sha256: str, data: bytes, principal: auth.Principal
) -> dict:
    """上传新版本：创建 is_active=0 的新行（原子 version+1），后台索引。

    仅 owner/管理员可操作；目标文档必须是 active 版本。
    """
    doc = await get_manageable_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    if not doc.get("is_active"):
        raise HTTPException(
            status_code=409, detail="只有 active 版本可以发起新版本替换"
        )
    settings = get_settings()
    pathlib.Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    new_id = document_repo.new_id()
    pdf_path = pathlib.Path(settings.DATA_DIR) / f"{new_id}.pdf"
    created = await document_repo.insert_version(
        doc_id,
        filename=filename,
        sha256=sha256,
        file_path=str(pdf_path),
        new_id=new_id,
    )
    if created is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    pdf_path.write_bytes(data)
    row = await document_repo.get_document(new_id)
    return {
        "document_id": new_id,
        "file_path": str(pdf_path),
        "version": row["version"] if row else 1,
        "status": "queued",
    }


async def recover_interrupted() -> int:
    """启动恢复：瞬态文档 -> failed（service_restart_interrupted）+ 清理 partial。

    返回处理的文档数。queued 也视为中断（新进程内无在途任务）。
    """
    rows = await document_repo.list_by_statuses(document_repo.TRANSIENT_STATUSES)
    recovered = 0
    for row in rows:
        await document_repo.update_status(
            row["id"],
            "failed",
            error="service_restart_interrupted",
            reason="service_restart_interrupted",
        )
        await cleanup_partial_chunks(row["id"])
        recovered += 1
    if rows:
        await index_service.rebuild_faiss()
    if recovered:
        _log.warning(
            "recovery.interrupted",
            extra={"count": recovered, "reason": "service_restart_interrupted"},
        )
    return recovered


async def get_acl(doc_id: str, principal: auth.Principal) -> AclPayload | None:
    doc = await get_visible_document(doc_id, principal)
    if not doc:
        return None
    return AclPayload(
        tenant_id=doc["tenant_id"],
        owner_user_id=doc["owner_user_id"],
        groups=list(doc.get("group_ids") or []),
    )


async def update_acl(
    doc_id: str, payload: AclPayload, principal: auth.Principal
) -> AclPayload | None:
    """仅 owner/管理员可改 ACL；tenant_id 不可修改（忽略请求值）。"""
    doc = await get_manageable_document(doc_id, principal)
    if not doc:
        return None
    await document_repo.update_acl(doc_id, payload.owner_user_id, payload.groups)
    return AclPayload(
        tenant_id=doc["tenant_id"],
        owner_user_id=payload.owner_user_id,
        groups=list(payload.groups),
    )
