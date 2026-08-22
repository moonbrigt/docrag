"""文档管理冒烟测试：上传 -> 全流水线索引 -> 详情/分块 -> 原文文件 -> 删除。

默认 conftest 开启全部 mock，因此上传会在无大模型环境下跑通 解析->分块->嵌入->索引。
"""
from __future__ import annotations

import pathlib

PDF_BYTES = b"%PDF-1.4\n% fake pdf for offline test\n"


def _upload(client):
    r = client.post(
        "/api/v1/documents",
        files={"file": ("sample.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def test_list_empty(client):
    r = client.get("/api/v1/documents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_upload_pipeline_indexed(client):
    from conftest import wait_indexed

    doc_id = _upload(client)
    doc = wait_indexed(client, doc_id)
    assert doc is not None
    assert doc["status"] == "indexed", doc

    detail = client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["document"]["chunk_count"] > 0
    assert len(detail["chunks"]) == detail["document"]["chunk_count"]
    # 每块必须携带 page_no（F6 溯源硬约束）
    for ch in detail["chunks"]:
        assert isinstance(ch["page_no"], int) and ch["page_no"] >= 1


def test_upload_duplicate_409(client):
    """同内容重复上传被拒（409 带既有文档名）；不同内容正常 202。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    dup = client.post(
        "/api/v1/documents",
        files={"file": ("again.pdf", PDF_BYTES, "application/pdf")},
    )
    assert dup.status_code == 409, dup.text
    assert "sample.pdf" in dup.json()["detail"]

    fresh = client.post(
        "/api/v1/documents",
        files={"file": ("other.pdf", PDF_BYTES + b"v2", "application/pdf")},
    )
    assert fresh.status_code == 202, fresh.text


def test_detail_404(client):
    r = client.get("/api/v1/documents/nonexistent-id")
    assert r.status_code == 404
    assert client.get("/api/v1/documents/nonexistent-id/file").status_code == 404


def test_missing_file_404(client):
    from app.config import get_settings
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)
    (pathlib.Path(get_settings().DATA_DIR) / f"{doc_id}.pdf").unlink()

    assert client.get(f"/api/v1/documents/{doc_id}/file").status_code == 404


def test_file_served_and_delete(client):
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    p = client.get(f"/api/v1/documents/{doc_id}/file")
    assert p.status_code == 200
    assert p.headers["content-type"] == "application/pdf"
    assert p.content == PDF_BYTES
    assert "sample.pdf" in p.headers["content-disposition"]

    d = client.delete(f"/api/v1/documents/{doc_id}")
    assert d.status_code == 204
    # 删除后详情 404（向量/FTS 同步清理在 service 层完成）
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/file").status_code == 404
