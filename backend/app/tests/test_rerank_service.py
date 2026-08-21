"""rerank_service 单元测试：候选池截断 + 全文回查（重排不使用 200 字符 snippet）。"""
from __future__ import annotations

import asyncio

from app.schemas import RetrievedChunk


def _chunks(n: int) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=i + 1,
            document_id="doc-rerank-test",
            doc_name="test.pdf",
            seq=i + 1,
            page_no=1,
            snippet=f"snippet-{i+1}",
            rrf_score=1.0 - i * 0.01,
            faiss_score=0.5,
            fts_score=0.4,
        )
        for i in range(n)
    ]


def _setup_db():
    from app import db

    def seed(conn):
        conn.execute(
            "INSERT OR REPLACE INTO documents (id, filename, page_count, status) "
            "VALUES (?, ?, ?, ?)",
            ("doc-rerank-test", "test.pdf", 1, "indexed"),
        )
        for i in range(20):
            conn.execute(
                "INSERT OR REPLACE INTO chunks (id, document_id, seq, content, page_no) "
                "VALUES (?, ?, ?, ?, ?)",
                (i + 1, "doc-rerank-test", i + 1, f"FULLTEXT-{i+1} " + "x" * 300, 1),
            )

    asyncio.run(db.write(seed))


def test_rerank_truncates_candidates_and_uses_fulltext():
    _setup_db()
    from app.services import rerank_service

    captured: dict = {}

    def fake_score(query, passages):
        captured["n"] = len(passages)
        captured["first"] = passages[0]
        return [float(p.split("-")[1].split(" ")[0]) for p in passages]  # FULLTEXT-n → 分数 n

    original = rerank_service._reranker.score
    rerank_service._reranker.score = fake_score
    try:
        out = asyncio.run(rerank_service.rerank("query", _chunks(20)))
    finally:
        rerank_service._reranker.score = original

    assert captured["n"] == 15  # 候选池 20 → 截断 RERANK_CANDIDATES=15
    assert captured["first"].startswith("FULLTEXT-1")  # 全文而非 snippet-1
    assert len(out) == 5  # RERANK_TOP_K
    assert out[0].chunk_id == 15  # 最高分（FULLTEXT-15）排最前


def test_rerank_small_pool_passthrough():
    from app.services import rerank_service

    captured: dict = {}

    def fake_score(query, passages):
        captured["n"] = len(passages)
        return [1.0] * len(passages)

    original = rerank_service._reranker.score
    rerank_service._reranker.score = fake_score
    try:
        out = asyncio.run(rerank_service.rerank("query", _chunks(3)))
    finally:
        rerank_service._reranker.score = original

    assert captured["n"] == 3  # 不足候选上限时全量送入
    assert len(out) == 3
