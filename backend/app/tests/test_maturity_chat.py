"""成熟度测试：chat SSE 契约、no-answer、rerank fail-closed、trace/feedback。

覆盖：stage/delta/citation/no_answer/done/error 事件序列、无信号检索时
no_answer(no_evidence) 且 LLM 不调用、无有效引用 no_answer(not_supported)、
rerank 未就绪 fail-closed、空知识库 409、trace 不存 query 明文、feedback。
"""
from __future__ import annotations

import json

PDF_BYTES = b"%PDF-1.4\n% fake pdf for offline test\n"


def _upload(client, filename="sample.pdf", headers=None):
    r = client.post(
        "/api/v1/documents",
        files={"file": (filename, PDF_BYTES, "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def _read_events(resp_iter):
    """解析 SSE 流为 [(event, payload|None)]。"""
    out: list[tuple[str, dict | None]] = []
    current: str | None = None
    for line in resp_iter:
        if line.startswith("event:"):
            current = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and current:
            out.append((current, json.loads(line.split(":", 1)[1].strip())))
            current = None
    return out


def test_no_answer_no_evidence_llm_not_called(client, monkeypatch):
    """无信号检索：no_answer(no_evidence) + 空 candidates，LLM 绝不调用。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    called = {"n": 0}

    async def fake_stream(*args, **kwargs):
        called["n"] += 1
        yield "不该被调用"

    from app.services import generate_service

    monkeypatch.setattr(generate_service._llm, "stream", fake_stream)
    with client.stream("POST", "/api/v1/chat", json={"query": "绝无此词"}) as r:
        assert r.status_code == 200
        events = _read_events(r.iter_lines())
    assert called["n"] == 0, "无证据时 LLM 不应被调用"
    names = [e for e, _ in events]
    assert names == ["stage", "no_answer", "done"]
    assert events[0][1] == {"stage": "retrieving"}
    no_answer = events[1][1]
    assert no_answer["reason"] == "no_evidence"
    assert no_answer["evidence_candidates"] == []  # 零分候选不得冒充证据
    assert events[2][1]["selected_document_ids"] == []
    assert events[2][1]["trace_id"]


def test_no_answer_not_supported_when_no_valid_citation(client, monkeypatch):
    """生成内容无有效引用：缓冲校验后 no_answer(not_supported)，不泄出 delta。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    async def fake_stream(sys_prompt, user_prompt, mock_context=None):
        yield "这段回答没有任何引用标记。"

    from app.services import generate_service

    monkeypatch.setattr(generate_service._llm, "stream", fake_stream)
    with client.stream("POST", "/api/v1/chat", json={"query": "sample"}) as r:
        assert r.status_code == 200
        events = _read_events(r.iter_lines())
    names = [e for e, _ in events]
    assert names == ["stage", "stage", "stage", "no_answer", "done"]
    no_answer = [p for e, p in events if e == "no_answer"][0]
    assert no_answer["reason"] == "not_supported"
    assert no_answer["evidence_candidates"], "应列出候选证据"
    # 候选全部来自有信号的证据（不允许零分候选）
    assert all(c["faiss_score"] is not None or c["fts_score"] is not None for c in no_answer["evidence_candidates"])
    assert "delta" not in names and "citation" not in names
    assert events[-1][1]["selected_document_ids"] == []


def test_rerank_fail_closed(client, monkeypatch):
    """rerank 未就绪：chat 明确 error 事件、search 503，绝不静默降级。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    from app.services import rerank_service

    monkeypatch.setattr(rerank_service, "is_ready", lambda: False)

    with client.stream("POST", "/api/v1/chat", json={"query": "sample"}) as r:
        assert r.status_code == 200
        events = _read_events(r.iter_lines())
    names = [e for e, _ in events]
    assert names[-1] == "error"
    message = events[-1][1]["message"]
    assert "重排" in message
    assert "delta" not in names

    r = client.post("/api/v1/search", json={"query": "sample"})
    assert r.status_code == 503
    assert "重排" in r.json()["detail"]
    # 显式关闭 rerank 仍可用
    r = client.post("/api/v1/search", json={"query": "sample", "rerank": False})
    assert r.status_code == 200


def test_empty_kb_chat_409(client):
    """空知识库提问：明确 409 + message（不进 SSE）。"""
    r = client.post("/api/v1/chat", json={"query": "任何问题"})
    assert r.status_code == 409
    assert r.json()["detail"]


def test_sse_contract_full_flow(client):
    """完整对话：stage -> delta -> citation -> done，citation 元数据齐全。"""
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    with client.stream("POST", "/api/v1/chat", json={"query": "sample"}) as r:
        assert r.status_code == 200
        events = _read_events(r.iter_lines())
    names = [e for e, _ in events]
    # 顺序：3 个 stage -> delta -> citation*N -> done
    assert names[:4] == ["stage", "stage", "stage", "delta"]
    assert "citation" in names
    assert names[-1] == "done"
    assert [p["stage"] for e, p in events if e == "stage"] == [
        "retrieving", "reranking", "generating",
    ]
    citation = next(p for e, p in events if e == "citation")
    assert citation["docId"] == doc_id
    assert citation["docName"]
    assert citation["page"] >= 1
    assert citation["sourceId"] == doc_id
    assert citation["version"] == 1
    assert citation["title"] == "sample.pdf"
    assert citation["createdAt"]
    assert citation["processingMs"] is not None
    done = events[-1][1]
    assert done["selected_document_ids"] == [doc_id]
    assert done["trace_id"]


def test_trace_and_feedback_query_not_stored(client):
    """trace 落库：query 原文与可反查哈希不落库；feedback 校验 trace 归属。"""
    from app import db
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    secret = "sample zzq9xmarker"
    with client.stream("POST", "/api/v1/chat", json={"query": secret}) as r:
        events = _read_events(r.iter_lines())
    trace_id = next(p["trace_id"] for e, p in events if e == "done")

    r = client.get(f"/api/v1/trace/{trace_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["query_hash"] == "not_stored"
    assert body["status"] == "ok"
    assert body["rerank_used"] is True
    assert body["selected_document_ids"] == [doc_id]
    assert body["evidence"]
    assert body["citations"]
    assert body["stage_timings"].keys() >= {"retrieving_ms", "reranking_ms", "generating_ms", "total_ms"}
    assert body["model_provenance"].keys() >= {"embedding", "rerank", "llm", "llm_model"}

    # query 明文（含唯一标记）绝不落库
    rows = db.query("SELECT * FROM trace")
    assert len(rows) == 1
    blob = " ".join(str(v) for r in rows for v in r.values())
    assert "zzq9xmarker" not in blob
    assert secret not in blob

    # feedback 提交与校验
    r = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": trace_id,
            "rating": "not_useful",
            "issue_type": "wrong_source",
            "selected_text": "某句",
            "comment": "引用错了",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    row = db.query_one("SELECT * FROM feedback WHERE trace_id=?", (trace_id,))
    assert row["rating"] == "not_useful"
    assert row["issue_type"] == "wrong_source"
    assert row["selected_text"] == "某句"
    assert row["comment"] == "引用错了"

    # 未知 trace -> 404；非法 rating -> 422
    assert client.post("/api/v1/feedback", json={"trace_id": "nope", "rating": "useful"}).status_code == 404
    assert client.post("/api/v1/feedback", json={"trace_id": trace_id, "rating": "meh"}).status_code == 422
    assert client.get("/api/v1/trace/nope").status_code == 404


def test_trace_access_control(client, monkeypatch):
    """trace 仅属主可见：异用户/异租户 404。"""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY", True)
    alice = {"X-Rag-Tenant": "default", "X-Rag-User": "alice"}
    bob = {"X-Rag-Tenant": "default", "X-Rag-User": "bob"}
    doc_id = _upload(client, headers=alice)
    from conftest import wait_indexed

    wait_indexed(client, doc_id, headers=alice)
    with client.stream(
        "POST", "/api/v1/chat", json={"query": "sample"}, headers=alice
    ) as r:
        events = _read_events(r.iter_lines())
    trace_id = next(p["trace_id"] for e, p in events if e == "done")

    assert client.get(f"/api/v1/trace/{trace_id}", headers=alice).status_code == 200
    assert client.get(f"/api/v1/trace/{trace_id}", headers=bob).status_code == 404
    assert client.post(
        "/api/v1/feedback",
        json={"trace_id": trace_id, "rating": "useful"},
        headers=bob,
    ).status_code == 404
