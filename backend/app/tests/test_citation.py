"""citation_service 单元测试：引用解析、去重、越界跳过、分数传递。"""
from __future__ import annotations

from app.schemas import RetrievedChunk
from app.services.citation_service import build_citations, parse_citation_indices


def _make_chunk(idx: int, **overrides) -> RetrievedChunk:
    """构造测试用 RetrievedChunk。"""
    defaults = {
        "chunk_id": idx,
        "document_id": f"doc_{idx}",
        "doc_name": f"doc_{idx}.pdf",
        "seq": idx,
        "page_no": idx,
        "bbox": None,
        "section": None,
        "snippet": f"snippet {idx}",
        "rrf_score": 0.1 * idx,
        "faiss_score": 0.05 * idx if idx % 2 == 0 else None,
        "fts_score": 0.03 * idx if idx % 3 == 0 else None,
        "source_id": f"src_{idx}",
        "version": 1,
        "title": f"doc_{idx}.pdf",
        "created_at": "2026-01-01T00:00:00",
    }
    defaults.update(overrides)
    return RetrievedChunk(**defaults)


class TestParseCitationIndices:
    def test_basic(self):
        assert parse_citation_indices("See [1] and [2]") == [1, 2]

    def test_no_citations(self):
        assert parse_citation_indices("No references here") == []

    def test_out_of_range_number(self):
        # parse 只提取数字，不校验范围
        assert parse_citation_indices("[99]") == [99]

    def test_zero_index(self):
        assert parse_citation_indices("[0]") == [0]

    def test_duplicate_indices(self):
        assert parse_citation_indices("[1] [1] [1]") == [1, 1, 1]

    def test_mixed_text(self):
        assert parse_citation_indices("abc[3]def[7]ghi") == [3, 7]


class TestBuildCitations:
    def test_empty_text(self):
        chunks = [_make_chunk(1)]
        assert build_citations("", chunks) == []

    def test_no_citations_in_text(self):
        chunks = [_make_chunk(1)]
        assert build_citations("No refs", chunks) == []

    def test_single_citation(self):
        chunks = [_make_chunk(1), _make_chunk(2)]
        result = build_citations("Answer [1]", chunks)
        assert len(result) == 1
        assert result[0]["index"] == 1
        assert result[0]["docId"] == "doc_1"
        assert result[0]["page"] == 1

    def test_dedup_preserves_first_occurrence(self):
        chunks = [_make_chunk(1), _make_chunk(2)]
        result = build_citations("[2] some text [2] more [1]", chunks)
        # [2] appears twice but only one citation; [1] appears once
        assert len(result) == 2
        assert result[0]["index"] == 2
        assert result[1]["index"] == 1

    def test_out_of_bounds_index_skipped(self):
        chunks = [_make_chunk(1)]
        result = build_citations("[1] and [99]", chunks)
        # [99] > len(chunks) → skipped
        assert len(result) == 1
        assert result[0]["index"] == 1

    def test_zero_index_skipped(self):
        chunks = [_make_chunk(1)]
        result = build_citations("[0] and [1]", chunks)
        # [0] < 1 → skipped
        assert len(result) == 1
    def test_negative_index_skipped(self):
        chunks = [_make_chunk(1)]
        result = build_citations("[-1] and [1]", chunks)
        # [-1] won't be extracted by regex (no负号 in pattern)
        assert len(result) == 1

    def test_scores_included(self):
        chunks = [_make_chunk(1), _make_chunk(2)]
        result = build_citations("[1]", chunks)
        cit = result[0]
        assert "rrfScore" in cit
        assert "faissScore" in cit
        assert "ftsScore" in cit
        # chunk 1: rrf=0.1, faiss=None (odd), fts=None (1%3!=0)
        assert cit["rrfScore"] == 0.1
        assert cit["faissScore"] is None
        assert cit["ftsScore"] is None

    def test_scores_chunk2(self):
        chunks = [_make_chunk(1), _make_chunk(2)]
        result = build_citations("[2]", chunks)
        cit = result[0]
        # chunk 2: rrf=0.2, faiss=0.1 (even), fts=None (2%3!=0)
        assert cit["rrfScore"] == 0.2
        assert cit["faissScore"] == 0.1
        assert cit["ftsScore"] is None

    def test_scores_chunk3(self):
        chunks = [_make_chunk(1), _make_chunk(2), _make_chunk(3)]
        result = build_citations("[3]", chunks)
        cit = result[0]
        # chunk 3: rrf=0.3, faiss=None (odd), fts=0.09 (3%3==0)
        assert cit["rrfScore"] == 0.3
        assert cit["faissScore"] is None
        assert cit["ftsScore"] == 0.09

    def test_processing_ms_passed(self):
        chunks = [_make_chunk(1)]
        result = build_citations("[1]", chunks, processing_ms=123.456)
        assert result[0]["processingMs"] == 123.46

    def test_processing_ms_none(self):
        chunks = [_make_chunk(1)]
        result = build_citations("[1]", chunks)
        assert result[0]["processingMs"] is None

    def test_metadata_fields(self):
        chunks = [_make_chunk(5)]
        result = build_citations("[1]", chunks)
        cit = result[0]
        assert cit["sourceId"] == "src_5"
        assert cit["version"] == 1
        assert cit["title"] == "doc_5.pdf"
        assert cit["createdAt"] == "2026-01-01T00:00:00"
