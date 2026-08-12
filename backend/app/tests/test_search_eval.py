"""检索 / 问答 SSE / 评测冒烟测试。

mock 解析器生成的语料包含「风险」「结论」「治理」等词，故用这些词做检索/问答，
可稳定命中（确定性 mock 嵌入按词元重叠）。
"""
from __future__ import annotations

import json

PDF_BYTES = b"%PDF-1.4\n% fake pdf for offline test\n"


def _upload(client):
    r = client.post(
        "/api/v1/documents",
        files={"file": ("sample.pdf", PDF_BYTES, "application/pdf")},
    )
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def test_search_returns_hits(client):
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    r = client.post("/api/v1/search", json={"query": "风险", "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    # mock 语料第 4 页含「风险」
    assert body["results"][0]["page_no"] == 4
    assert body["rerank"] is True


def test_search_empty_kb(client):
    # 全新 client 知识库为空，search 应返回 200 与空结果（不崩溃）
    r = client.post("/api/v1/search", json={"query": "任意问题"})
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_chat_sse(client):
    from conftest import wait_indexed

    doc_id = _upload(client)
    wait_indexed(client, doc_id)

    # 契约变化：零信号查询（如 2 字 "风险" 在 mock 嵌入下无正分）现在返回
    # no_answer；本用例用有真实信号的 token（文件名 "sample"，每块都含）验证
    # 完整生成链路 delta/citation/done 与 stage 阶段事件。
    with client.stream("POST", "/api/v1/chat", json={"query": "sample"}) as r:
        assert r.status_code == 200
        events: list[str] = []
        citation_payloads: list[dict] = []
        current_event: str | None = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                events.append(current_event)
            elif current_event == "citation" and line.startswith("data:"):
                citation_payloads.append(json.loads(line.split(":", 1)[1].strip()))
                current_event = None
        assert "stage" in events
        assert "delta" in events
        assert "citation" in events
        assert "done" in events
        assert citation_payloads
        bbox = citation_payloads[0]["bbox"]
        assert set(bbox) == {"left", "top", "right", "bottom"}
        assert all(0 <= value <= 1 for value in bbox.values())


def test_evaluation_run(client):
    # 契约变化：默认 profile 已改为 public_nist（未 prepare 时 409）；
    # 本用例显式选择 synthetic_smoke 保留原断言语义（离线 22 条内嵌语料）。
    r = client.post(
        "/api/v1/evaluation/run", json={"config": {"profile": "synthetic_smoke"}}
    )
    assert r.status_code == 200
    body = r.json()
    m = body["metrics"]
    assert m["num_queries"] >= 20
    assert "citation_accuracy" in m
    assert "recall_at_k" in m
    assert "hit_rate_at_k" in m
    assert "mrr" in m
    assert isinstance(body["per_query"], list) and len(body["per_query"]) >= 20
