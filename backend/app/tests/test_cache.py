"""查询缓存单元测试：命中、未命中、TTL 过期、失效、scope 隔离。"""
from __future__ import annotations

import time

from app.schemas import RetrievedChunk


def _make_result(doc_id: str = "doc1") -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=1,
            document_id=doc_id,
            doc_name="test.pdf",
            seq=1,
            page_no=1,
            snippet="test",
            rrf_score=0.5,
            faiss_score=0.3,
            fts_score=0.2,
        )
    ]


class TestCacheKey:
    def test_same_query_same_scope_same_key(self):
        from app.services.retrieve_service import _cache_key
        key1 = _cache_key("query", frozenset({"a", "b"}))
        key2 = _cache_key("query", frozenset({"b", "a"}))
        assert key1 == key2  # frozenset 无序

    def test_different_scope_different_key(self):
        from app.services.retrieve_service import _cache_key
        key1 = _cache_key("query", frozenset({"a"}))
        key2 = _cache_key("query", frozenset({"b"}))
        assert key1 != key2

    def test_different_query_different_key(self):
        from app.services.retrieve_service import _cache_key
        key1 = _cache_key("q1", frozenset({"a"}))
        key2 = _cache_key("q2", frozenset({"a"}))
        assert key1 != key2


class TestCacheOperations:
    def setup_method(self):
        from app.services import retrieve_service
        retrieve_service._cache.clear()

    def test_miss_on_empty(self):
        from app.services.retrieve_service import _cache_get
        assert _cache_get("nonexistent") is None

    def test_set_and_get(self):
        from app.services.retrieve_service import _cache_get, _cache_set
        result = _make_result()
        _cache_set("key1", result)
        cached = _cache_get("key1")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].document_id == "doc1"

    def test_ttl_expiry(self):
        from app.services import retrieve_service
        from app.services.retrieve_service import _cache_get, _cache_set
        # 临时设 TTL=0.1s
        original_ttl = retrieve_service._settings.CACHE_TTL
        try:
            retrieve_service._settings.CACHE_TTL = 0.1
            _cache_set("key1", _make_result())
            assert _cache_get("key1") is not None
            time.sleep(0.15)
            assert _cache_get("key1") is None
        finally:
            retrieve_service._settings.CACHE_TTL = original_ttl

    def test_cache_disabled_when_ttl_zero(self):
        from app.services import retrieve_service
        from app.services.retrieve_service import _cache_get, _cache_set
        original_ttl = retrieve_service._settings.CACHE_TTL
        try:
            retrieve_service._settings.CACHE_TTL = 0
            _cache_set("key1", _make_result())
            assert _cache_get("key1") is None  # TTL=0 → 不缓存
        finally:
            retrieve_service._settings.CACHE_TTL = original_ttl

    def test_invalidate_all(self):
        from app.services.retrieve_service import _cache_get, _cache_set, invalidate_cache
        _cache_set("key1", _make_result())
        assert _cache_get("key1") is not None
        invalidate_cache()
        assert _cache_get("key1") is None

    def test_lru_eviction(self):
        from app.services import retrieve_service
        from app.services.retrieve_service import _cache_set
        # 填充超过 500 条触发淘汰
        for i in range(502):
            _cache_set(f"key_{i}", _make_result(f"doc_{i}"))
        # 早期的 key 应被淘汰
        assert len(retrieve_service._cache) <= 500
