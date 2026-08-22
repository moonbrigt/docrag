"""成熟度测试：ACL 与身份、租户隔离、检索范围（fail-closed）。

覆盖：trusted-proxy 身份头解析、本地模式忽略身份头、租户隔离、
撤权后检索 fail-closed、显式空 document_ids、document_ids 双路过滤、
ACL 端点、CORS 不暴露 X-Rag-*。
"""
from __future__ import annotations

PDF_BYTES = b"%PDF-1.4\n% fake pdf for offline test\n"


def _upload(client, filename="sample.pdf", headers=None):
    # 字节含文件名：同用例多次上传时 sha 唯一（内容去重不误伤）
    r = client.post(
        "/api/v1/documents",
        files={"file": (filename, PDF_BYTES + filename.encode(), "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def _h(tenant="default", user="local", groups=None):
    headers = {"X-Rag-Tenant": tenant, "X-Rag-User": user}
    if groups is not None:
        headers["X-Rag-Group"] = ",".join(groups)
    return headers


def _enable_trusted_proxy(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY", True)


def test_local_mode_ignores_identity_headers(client):
    """RAG_TRUSTED_PROXY=false（默认）：请求头身份一律忽略。"""
    headers = {"X-Rag-Tenant": "evil-tenant", "X-Rag-User": "evil-user"}
    doc_id = _upload(client, headers=headers)
    # 本地默认身份（default 租户）能看到
    r = client.get("/api/v1/documents")
    assert r.status_code == 200
    assert any(d["id"] == doc_id for d in r.json())
    assert client.get(f"/api/v1/documents/{doc_id}").status_code == 200


def test_trusted_proxy_tenant_isolation(client, monkeypatch):
    """trusted-proxy 下租户硬隔离：列表/详情/文件/检索全部 fail-closed。"""
    _enable_trusted_proxy(monkeypatch)
    doc_id = _upload(client, headers=_h(tenant="tenant-a", user="alice"))

    # 同租户可见
    r = client.get("/api/v1/documents", headers=_h("tenant-a", "alice"))
    assert [d["id"] for d in r.json()] == [doc_id]

    # 异租户：列表空、详情 404、文件 404、检索空
    r = client.get("/api/v1/documents", headers=_h("tenant-b", "bob"))
    assert r.json() == []
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("tenant-b", "bob")).status_code == 404
    assert client.get(f"/api/v1/documents/{doc_id}/file", headers=_h("tenant-b", "bob")).status_code == 404
    r = client.post(
        "/api/v1/search",
        json={"query": "sample"},
        headers=_h("tenant-b", "bob"),
    )
    assert r.json()["count"] == 0
    # 异租户 chat：范围为空 -> 409（不泄露存在性）
    r = client.post("/api/v1/chat", json={"query": "sample"}, headers=_h("tenant-b", "bob"))
    assert r.status_code == 409


def test_acl_revoke_fail_closed(client, monkeypatch):
    """撤权后详情/检索全部 fail-closed；授权组可访问；再撤权回到 404。"""
    _enable_trusted_proxy(monkeypatch)
    doc_id = _upload(client, headers=_h("default", "alice", groups=[]))
    from conftest import wait_indexed

    wait_indexed(client, doc_id, headers=_h("default", "alice"))

    # 未授权用户：不可见
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("default", "bob")).status_code == 404
    r = client.post("/api/v1/search", json={"query": "sample"}, headers=_h("default", "bob"))
    assert r.json()["count"] == 0

    # 属主授权给组 team -> bob 入组后可见且可检索
    r = client.put(
        f"/api/v1/documents/{doc_id}/acl",
        json={"tenant_id": "default", "owner_user_id": "alice", "groups": ["team"]},
        headers=_h("default", "alice"),
    )
    assert r.status_code == 200
    assert r.json()["groups"] == ["team"]
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("default", "bob", ["team"])).status_code == 200
    r = client.post(
        "/api/v1/search", json={"query": "sample"}, headers=_h("default", "bob", ["team"])
    )
    assert r.json()["count"] >= 1

    # 撤权（groups=[]）-> 再次 fail-closed
    r = client.put(
        f"/api/v1/documents/{doc_id}/acl",
        json={"tenant_id": "default", "owner_user_id": "alice", "groups": []},
        headers=_h("default", "alice"),
    )
    assert r.status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("default", "bob", ["team"])).status_code == 404
    r = client.post(
        "/api/v1/search", json={"query": "sample"}, headers=_h("default", "bob", ["team"])
    )
    assert r.json()["count"] == 0


def test_acl_endpoints_permissions(client, monkeypatch):
    """ACL 读取需可见、修改需 owner/管理员；tenant_id 不可被 PUT 篡改。"""
    _enable_trusted_proxy(monkeypatch)
    doc_id = _upload(client, headers=_h("default", "alice"))

    # 读取：属主 OK；无权限 404
    r = client.get(f"/api/v1/documents/{doc_id}/acl", headers=_h("default", "alice"))
    assert r.status_code == 200
    assert r.json() == {"tenant_id": "default", "owner_user_id": "alice", "groups": []}
    assert client.get(f"/api/v1/documents/{doc_id}/acl", headers=_h("default", "bob")).status_code == 404

    # 修改：非 owner 404；owner 可改 owner/groups；tenant_id 篡改被忽略
    assert client.put(
        f"/api/v1/documents/{doc_id}/acl",
        json={"tenant_id": "default", "owner_user_id": "bob", "groups": ["x"]},
        headers=_h("default", "bob"),
    ).status_code == 404
    r = client.put(
        f"/api/v1/documents/{doc_id}/acl",
        json={"tenant_id": "evil", "owner_user_id": "carol", "groups": ["g1", "g2"]},
        headers=_h("default", "alice"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "default"  # 不可篡改租户
    assert body["owner_user_id"] == "carol"
    assert body["groups"] == ["g1", "g2"]
    # 新属主 carol 可见；原属主 alice 不再可见
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("default", "carol")).status_code == 200
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("default", "alice")).status_code == 404


def test_admin_bypasses_visibility(client, monkeypatch):
    """管理员（user=admin 或组 admins）跨用户可见，但受租户边界约束。"""
    _enable_trusted_proxy(monkeypatch)
    doc_id = _upload(client, headers=_h("tenant-a", "alice"))
    # 同租户 admin 用户可见
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("tenant-a", "admin")).status_code == 200
    # admins 组成员可见
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("tenant-a", "ops", ["admins"])).status_code == 200
    # 异租户管理员不可见（租户边界仍生效）
    assert client.get(f"/api/v1/documents/{doc_id}", headers=_h("tenant-b", "admin")).status_code == 404


def test_empty_document_ids_is_empty_scope(client):
    """显式空列表 [] = 空范围：检索零结果、chat 明确 409。"""
    doc_id = _upload(client)
    from conftest import wait_indexed

    wait_indexed(client, doc_id)

    r = client.post("/api/v1/search", json={"query": "sample", "document_ids": []})
    assert r.status_code == 200
    assert r.json()["count"] == 0

    r = client.post("/api/v1/chat", json={"query": "sample", "document_ids": []})
    assert r.status_code == 409
    assert r.json()["detail"]


def test_document_ids_scoped_both_retrieval_routes(client):
    """document_ids 过滤同时作用于 FTS 与 FAISS：范围外文档零泄漏。"""
    from conftest import wait_indexed

    doc_a = _upload(client, filename="sample.pdf")
    wait_indexed(client, doc_a)
    doc_b = _upload(client, filename="other.pdf")
    wait_indexed(client, doc_b)

    # "sample" 只存在于 doc_a；"other" 只存在于 doc_b
    # 范围过滤后即使零分候选也只允许来自范围内的文档（不跨文档泄漏）
    r = client.post("/api/v1/search", json={"query": "sample", "document_ids": [doc_b]})
    assert r.json()["count"] >= 0
    assert all(x["document_id"] == doc_b for x in r.json()["results"])
    r = client.post("/api/v1/search", json={"query": "other", "document_ids": [doc_a]})
    assert all(x["document_id"] == doc_a for x in r.json()["results"])
    r = client.post("/api/v1/search", json={"query": "sample", "document_ids": [doc_a]})
    assert r.json()["count"] >= 1
    assert all(x["document_id"] == doc_a for x in r.json()["results"])
    # 无范围：两文档都可命中（doc_a 有真实信号，doc_b 零分候选也可能入榜）
    r = client.post("/api/v1/search", json={"query": "sample", "top_k": 20})
    assert r.json()["count"] >= 1
    assert any(x["document_id"] == doc_a for x in r.json()["results"])
    r = client.post("/api/v1/search", json={"query": "other", "top_k": 20})
    assert any(x["document_id"] == doc_b for x in r.json()["results"])


def test_cors_does_not_allow_x_rag_headers(client):
    """CORS allow_headers 不含 X-Rag-*：带这些头的预检必须被拒（浏览器无法伪造身份）。"""
    r = client.options(
        "/api/v1/documents",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Rag-Tenant",
        },
    )
    assert r.status_code == 400
    r = client.options(
        "/api/v1/documents",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200


def test_document_list_contract_fields(client):
    """GET /documents 项含 status/page_count/chunk_count/version/source_id/is_active。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)
    items = client.get("/api/v1/documents").json()
    item = next(d for d in items if d["id"] == doc_id)
    assert item["status"] == "indexed"
    assert item["page_count"] == 5
    assert item["chunk_count"] == 5
    assert item["version"] == 1
    assert item["source_id"] == doc_id
    assert item["is_active"] == 1
    assert item["tenant_id"] == "default"
    assert item["owner_user_id"] == "local"
    assert item["group_ids"] == []
