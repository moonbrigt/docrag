"""文档路由：上传 / 列表 / 详情 / 删除 / 原文文件 / 生命周期 / 版本 / ACL。

仅做参数校验、调用服务、组装响应，不含业务逻辑。
上传触发后台索引流水线（queued -> ... -> indexed）。
所有文档访问按 ACL fail-closed 过滤（无权限 = 404 / 空结果，不泄露存在性）。
"""
from __future__ import annotations

import asyncio
import pathlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import auth
from app.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import get_metrics
from app.repositories import document_repo
from app.schemas import AclPayload, DocumentDetailOut, DocumentOut, StatusOut, VersionCreateOut
from app.services import document_service, pipeline_service

_log = get_logger("docrag.routes.documents")

router = APIRouter(prefix="/api/v1", tags=["documents"])
_settings = get_settings()


@router.post("/documents", status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    principal: auth.Principal = Depends(auth.get_principal),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    filename = file.filename or "upload.pdf"
    pathlib.Path(_settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    doc_id = document_repo.new_id()
    pdf_path = pathlib.Path(_settings.DATA_DIR) / f"{doc_id}.pdf"
    await document_repo.insert_document(
        doc_id=doc_id,
        filename=filename,
        sha256=pipeline_service.sha256_bytes(data),
        page_count=0,
        status="queued",
        file_path=str(pdf_path),
        tenant_id=principal.tenant_id,
        owner_user_id=principal.user_id,
        group_ids=list(principal.groups),
    )
    pdf_path.write_bytes(data)
    get_metrics().incr("document_uploads_total")
    _log.info(
        "document.queued",
        extra={"doc_id": doc_id, "bytes": len(data), "tenant": principal.tenant_id},
    )
    asyncio.create_task(
        pipeline_service.run_pipeline(doc_id, data, filename, str(pdf_path))
    )
    return {"document_id": doc_id, "status": "queued"}


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    principal: auth.Principal = Depends(auth.get_principal),
):
    return await document_service.list_documents(principal)


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
async def get_document(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    doc = await document_service.get_visible_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    chunks = await document_service.get_chunks(doc_id)
    return {"document": doc, "chunks": chunks}


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    await document_service.delete_document(doc_id, principal)
    return None


@router.get("/documents/{doc_id}/file")
async def get_document_file(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    file_info = await document_service.get_document_file(doc_id, principal)
    if not file_info:
        raise HTTPException(
            status_code=404,
            detail="原文文件不存在：文档可能尚未解析完成或被删除",
        )
    path, filename = file_info
    return FileResponse(path, media_type="application/pdf", filename=filename)


# ---------------- 生命周期 ----------------
@router.post("/documents/{doc_id}/cancel", response_model=StatusOut)
async def cancel_document(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    return await document_service.cancel_document(doc_id, principal)


@router.post("/documents/{doc_id}/retry", status_code=202, response_model=StatusOut)
async def retry_document(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    doc_id, filename, data = await document_service.retry_document(doc_id, principal)
    # 认领成功：先清掉上一轮 partial chunks，再重跑流水线
    await document_service.cleanup_partial_chunks(doc_id)
    doc = await document_repo.get_document(doc_id)
    asyncio.create_task(
        pipeline_service.run_pipeline(doc_id, data, filename, doc["file_path"])
    )
    return {"document_id": doc_id, "status": "queued"}


@router.post("/documents/{doc_id}/versions", status_code=202, response_model=VersionCreateOut)
async def create_version(
    doc_id: str,
    file: UploadFile = File(...),
    principal: auth.Principal = Depends(auth.get_principal),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    filename = file.filename or "upload.pdf"
    created = await document_service.create_version(
        doc_id, filename, pipeline_service.sha256_bytes(data), data, principal
    )
    _log.info(
        "document.version_queued",
        extra={
            "source_doc_id": doc_id,
            "new_doc_id": created["document_id"],
            "version": created["version"],
            "bytes": len(data),
        },
    )
    asyncio.create_task(
        pipeline_service.run_pipeline(
            created["document_id"],
            data,
            filename,
            created["file_path"],
            promote_on_success=True,
        )
    )
    return {
        "document_id": created["document_id"],
        "version": created["version"],
        "status": "queued",
    }


@router.get("/documents/{doc_id}/versions", response_model=list[DocumentOut])
async def list_versions(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    """同一 source 的全部版本（可见性过滤）。"""
    doc = await document_service.get_visible_document(doc_id, principal)
    if not doc:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    rows = await document_repo.list_versions(doc["source_id"])
    return [r for r in rows if auth.doc_visible(principal, r)]


# ---------------- ACL ----------------
@router.get("/documents/{doc_id}/acl", response_model=AclPayload)
async def get_acl(
    doc_id: str,
    principal: auth.Principal = Depends(auth.get_principal),
):
    acl = await document_service.get_acl(doc_id, principal)
    if acl is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    return acl


@router.put("/documents/{doc_id}/acl", response_model=AclPayload)
async def update_acl(
    doc_id: str,
    payload: AclPayload,
    principal: auth.Principal = Depends(auth.get_principal),
):
    acl = await document_service.update_acl(doc_id, payload, principal)
    if acl is None:
        raise HTTPException(status_code=404, detail=f"文档不存在：{doc_id}")
    _log.info("document.acl_updated", extra={"doc_id": doc_id, "user": principal.user_id})
    return acl
