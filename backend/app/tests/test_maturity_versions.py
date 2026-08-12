"""成熟度测试：版本替换与删除竞态。

覆盖：新版本索引成功后才归档旧版本（active 唯一）、失败版本不影响旧版本、
归档版本不可检索（零泄漏）、版本列表、非 active 版本不可发起替换、
删除与在途流水线竞态（无孤儿 chunk/FTS/文件）、删除权限。
"""
from __future__ import annotations

import time

PDF_BYTES = b"%PDF-1.4\n% fake pdf for offline test\n"


def _upload(client, filename="sample.pdf", headers=None):
    r = client.post(
        "/api/v1/documents",
        files={"file": (filename, PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def _wait_status(client, doc_id, statuses, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/v1/documents/{doc_id}")
        if r.status_code == 200:
            last = r.json()["document"]
            if last["status"] in statuses:
                return last
        time.sleep(0.05)
    return last


def test_versions_promote_on_success_and_archive(client, monkeypatch):
    """新版本索引成功后才归档旧版本；失败时旧版本保持 active。"""
    from conftest import wait_indexed

    v1_id = _upload(client, filename="sample.pdf")
    wait_indexed(client, v1_id)

    # 上传 v2（不同文件名 -> 不同内容）
    r = client.post(
        f"/api/v1/documents/{v1_id}/versions",
        files={"file": ("other.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 202, r.text
    v2_id = r.json()["document_id"]
    assert r.json()["version"] == 2
    assert r.json()["status"] == "queued"

    v2 = wait_indexed(client, v2_id)
    assert v2["status"] == "indexed"
    assert v2["is_active"] == 1
    assert v2["source_id"] == v1_id

    v1 = client.get(f"/api/v1/documents/{v1_id}").json()["document"]
    assert v1["is_active"] == 0
    assert v1["archived_at"], "旧版本应记录归档时间"

    # 版本列表
    rows = client.get(f"/api/v1/documents/{v1_id}/versions").json()
    assert [r["version"] for r in rows] == [1, 2]

    # 检索只命中 active 版本（v2 内容 other.pdf）；归档的 v1 零泄漏
    r = client.post("/api/v1/search", json={"query": "other"})
    assert r.json()["count"] >= 1
    assert all(x["document_id"] == v2_id for x in r.json()["results"])
    r = client.post("/api/v1/search", json={"query": "sample"})
    assert all(x["document_id"] == v2_id for x in r.json()["results"])

    # 失败的新版本不影响旧版本（新版本必须基于当前 active 版本上传）
    import app.services.pipeline_service as ps

    original_parse = ps._parser.parse

    def failing_parse(file_bytes, filename, source_path=None):
        raise RuntimeError("v3 parse boom")

    monkeypatch.setattr(ps._parser, "parse", failing_parse)
    # v1 已归档（非 active），不可再作为版本源
    r = client.post(
        f"/api/v1/documents/{v1_id}/versions",
        files={"file": ("v3.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 409
    r = client.post(
        f"/api/v1/documents/{v2_id}/versions",
        files={"file": ("v3.pdf", PDF_BYTES, "application/pdf")},
    )
    v3_id = r.json()["document_id"]
    _wait_status(client, v3_id, ("failed",))
    v1 = client.get(f"/api/v1/documents/{v1_id}").json()["document"]
    v2 = client.get(f"/api/v1/documents/{v2_id}").json()["document"]
    assert v1["is_active"] == 0
    assert v2["is_active"] == 1  # 旧 active 保持
    monkeypatch.setattr(ps._parser, "parse", original_parse)


def test_delete_race_no_orphan_chunks(client, monkeypatch):
    """删除与在途流水线竞态：删除后不允许流水线再写入孤儿 chunk。"""
    import pathlib

    import app.services.pipeline_service as ps
    from app import db
    from app.config import get_settings

    original_parse = ps._parser.parse

    def slow_parse(file_bytes, filename, source_path=None):
        time.sleep(0.5)
        return original_parse(file_bytes, filename, source_path)

    monkeypatch.setattr(ps._parser, "parse", slow_parse)
    doc_id = _upload(client)
    time.sleep(0.1)

    r = client.delete(f"/api/v1/documents/{doc_id}")
    assert r.status_code == 204
    time.sleep(0.7)  # 慢解析返回后，流水线守卫应发现文档已删除

    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    row = db.query_one("SELECT COUNT(*) AS n FROM chunks WHERE document_id=?", (doc_id,))
    assert row["n"] == 0, "不得残留孤儿 chunk"
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM chunk_fts f JOIN chunks c ON c.id=f.rowid "
        "WHERE c.document_id=?",
        (doc_id,),
    )
    assert row["n"] == 0, "不得残留孤儿 FTS 条目"
    # 物理文件已清理
    pdf = pathlib.Path(get_settings().DATA_DIR) / f"{doc_id}.pdf"
    assert not pdf.exists()
    # FAISS 内存索引无残留
    from app.services import index_service

    assert index_service.get_faiss().size == 0


def test_delete_non_owner_404(client, monkeypatch):
    """删除仅 owner/管理员：他人删除返回 404（不泄露存在性）。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY", True)
    doc_id = _upload(
        client, headers={"X-Rag-Tenant": "default", "X-Rag-User": "alice"}
    )
    r = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"X-Rag-Tenant": "default", "X-Rag-User": "bob"},
    )
    assert r.status_code == 404
    # 属主可删
    r = client.delete(
        f"/api/v1/documents/{doc_id}",
        headers={"X-Rag-Tenant": "default", "X-Rag-User": "alice"},
    )
    assert r.status_code == 204


def test_versions_require_manage_permission(client, monkeypatch):
    """非 owner 不可上传版本（404，不泄露存在性）。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY", True)
    doc_id = _upload(
        client, headers={"X-Rag-Tenant": "default", "X-Rag-User": "alice"}
    )
    r = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("v2.pdf", PDF_BYTES, "application/pdf")},
        headers={"X-Rag-Tenant": "default", "X-Rag-User": "bob"},
    )
    assert r.status_code == 404
    # 属主可传
    r = client.post(
        f"/api/v1/documents/{doc_id}/versions",
        files={"file": ("v2.pdf", PDF_BYTES, "application/pdf")},
        headers={"X-Rag-Tenant": "default", "X-Rag-User": "alice"},
    )
    assert r.status_code == 202


def test_delete_cleans_events_and_trace_consistency(client):
    """删除后事件记录一并清理（事务内），不残留 document_events。"""
    from conftest import wait_indexed

    from app import db

    doc_id = _upload(client)
    wait_indexed(client, doc_id)
    assert db.query("SELECT COUNT(*) AS n FROM document_events WHERE document_id=?",
                    (doc_id,))[0]["n"] >= 1
    client.delete(f"/api/v1/documents/{doc_id}")
    assert db.query("SELECT COUNT(*) AS n FROM document_events WHERE document_id=?",
                    (doc_id,))[0]["n"] == 0
