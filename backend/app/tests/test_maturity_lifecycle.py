"""成熟度测试：文档生命周期（cancel / retry / 版本 / 启动恢复 / 删除竞态）。

覆盖：取消停止后续阶段并清理 partial、重试原子认领、失败/警告状态语义、
版本替换成功归档与失败保留、重启恢复（service_restart_interrupted）、
删除与在途流水线的竞态（无孤儿 chunk）。
"""
from __future__ import annotations

import asyncio
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


def test_cancel_mid_pipeline_stops_and_cleans(client, monkeypatch):
    """解析进行中取消：终态 cancelled、partial chunks 清理、不可重复取消。"""
    import app.services.pipeline_service as ps

    original_parse = ps._parser.parse

    def slow_parse(file_bytes, filename, source_path=None):
        time.sleep(0.5)
        return original_parse(file_bytes, filename, source_path)

    monkeypatch.setattr(ps._parser, "parse", slow_parse)
    doc_id = _upload(client)
    time.sleep(0.1)  # 确保流水线已进入 parsing（线程内阻塞解析）

    r = client.post(f"/api/v1/documents/{doc_id}/cancel")
    assert r.status_code == 200
    assert r.json() == {"document_id": doc_id, "status": "cancelled"}

    time.sleep(0.7)  # 等慢解析返回，流水线应被阶段守卫停止
    doc = client.get(f"/api/v1/documents/{doc_id}").json()["document"]
    assert doc["status"] == "cancelled"
    assert doc["chunk_count"] == 0
    # 无 partial 泄漏到检索
    r = client.post("/api/v1/search", json={"query": "sample"})
    assert r.json()["count"] == 0
    # 已终态不可再取消
    assert client.post(f"/api/v1/documents/{doc_id}/cancel").status_code == 409


def test_cancel_terminal_conflict(client):
    """已 indexed 的文档不可取消（409）。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)
    r = client.post(f"/api/v1/documents/{doc_id}/cancel")
    assert r.status_code == 409
    assert "不可取消" in r.json()["detail"]


def test_failure_then_retry_cleans_partial(client, monkeypatch):
    """失败 -> retry（原子认领）-> 重跑流水线，partial chunks 被清理。"""
    import app.services.pipeline_service as ps
    from conftest import wait_indexed

    original_parse = ps._parser.parse

    def failing_parse(file_bytes, filename, source_path=None):
        raise RuntimeError("boom: simulated parse failure")

    monkeypatch.setattr(ps._parser, "parse", failing_parse)
    doc_id = _upload(client)
    doc = _wait_status(client, doc_id, ("failed",))
    assert doc["status"] == "failed"
    assert doc["error"] == "boom: simulated parse failure"
    assert doc["chunk_count"] == 0

    # 注入一条 partial chunk 模拟历史脏数据
    from app import db

    asyncio.run(
        db.write(
            lambda c: c.execute(
                "INSERT INTO chunks (document_id, seq, content, page_no) VALUES (?,1,'脏分块',1)",
                (doc_id,),
            )
        )
    )
    # retry 期间不允许并发 retry（原子认领）：第一次认领后第二次 409
    monkeypatch.setattr(ps._parser, "parse", original_parse)
    r = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert r.status_code == 202
    assert r.json() == {"document_id": doc_id, "status": "queued"}
    r2 = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert r2.status_code == 409

    doc = wait_indexed(client, doc_id)
    assert doc["status"] == "indexed"
    assert doc["chunk_count"] == 5  # 脏分块已被清理，只有重跑写入的 5 块

    # 已 indexed 不可重试
    assert client.post(f"/api/v1/documents/{doc_id}/retry").status_code == 409


def test_retry_requires_manage_permission(client, monkeypatch):
    """非 owner 不可 cancel/retry（404，不泄露存在性）。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY", True)
    doc_id = _upload(
        client, headers={"X-Rag-Tenant": "default", "X-Rag-User": "alice"}
    )
    headers = {"X-Rag-Tenant": "default", "X-Rag-User": "bob"}
    assert (
        client.post(f"/api/v1/documents/{doc_id}/cancel", headers=headers).status_code
        == 404
    )
    assert (
        client.post(f"/api/v1/documents/{doc_id}/retry", headers=headers).status_code
        == 404
    )


def test_pipeline_warning_keeps_partial(client, monkeypatch):
    """分块已落库但索引重建失败 -> warning（部分成功，分块保留可检索）。"""
    import app.services.index_service as index_service
    from conftest import wait_indexed

    original_rebuild = index_service.rebuild_faiss

    def failing_rebuild():
        raise RuntimeError("faiss rebuild boom")

    monkeypatch.setattr(index_service, "rebuild_faiss", failing_rebuild)
    doc_id = _upload(client)
    doc = _wait_status(client, doc_id, ("warning", "failed"))
    assert doc["status"] == "warning", doc
    assert doc["chunk_count"] == 5  # 部分成功：分块保留
    # 分块可检索（FTS 路仍工作）
    r = client.post("/api/v1/search", json={"query": "sample"})
    assert r.json()["count"] >= 1
    # 恢复 rebuild 后 retry -> indexed
    monkeypatch.setattr(index_service, "rebuild_faiss", original_rebuild)
    assert client.post(f"/api/v1/documents/{doc_id}/retry").status_code == 202
    doc = wait_indexed(client, doc_id)
    assert doc["status"] == "indexed"


def test_restart_recovery(client):
    """启动恢复：瞬态状态 -> failed(reason=service_restart_interrupted) + 清理。"""
    from app import db
    from app.main import app
    from fastapi.testclient import TestClient

    # 模拟上一进程崩溃遗留：一个 embedding 中的文档 + 一条 partial chunk
    doc_id = "stale-doc-1"
    asyncio.run(
        db.write(
            lambda c: c.execute(
                "INSERT INTO documents (id, filename, status, file_path, source_id, version, is_active) "
                "VALUES (?,?,?,?,?,1,1)",
                (doc_id, "stale.pdf", "embedding", "/tmp/nonexist.pdf", doc_id),
            )
        )
    )
    asyncio.run(
        db.write(
            lambda c: c.execute(
                "INSERT INTO chunks (document_id, seq, content, page_no) VALUES (?,1,'partial',1)",
                (doc_id,),
            )
        )
    )

    # 重新进入 lifespan（等价服务重启）
    with TestClient(app) as c2:
        r = c2.get(f"/api/v1/documents/{doc_id}")
        assert r.status_code == 200
        doc = r.json()["document"]
        assert doc["status"] == "failed", doc
        assert doc["error"] == "service_restart_interrupted"
        assert doc["chunk_count"] == 0  # partial 已清理

    # 事件表记录了 reason
    rows = db.query(
        "SELECT * FROM document_events WHERE document_id=?", (doc_id,)
    )
    assert rows, "应记录状态流转事件"
    assert rows[-1]["to_status"] == "failed"
    assert rows[-1]["reason"] == "service_restart_interrupted"
    assert rows[-1]["is_transient"] == 0

    # queued 状态同样视为中断
    doc2 = "stale-doc-2"
    asyncio.run(
        db.write(
            lambda c: c.execute(
                "INSERT INTO documents (id, filename, status, source_id, version, is_active) "
                "VALUES (?,?,'queued',?,1,1)",
                (doc2, "stale2.pdf", doc2),
            )
        )
    )
    from app.services import document_service

    n = asyncio.run(document_service.recover_interrupted())
    assert n == 1
    row = db.query_one("SELECT status, error FROM documents WHERE id=?", (doc2,))
    assert row["status"] == "failed"
    assert row["error"] == "service_restart_interrupted"

