"""Docling 坐标到 F6 引用坐标契约的纯转换测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.parser import ParseResult, ParseService, _normalize_docling_bbox


def test_parse_lazily_initializes_real_docling_path(monkeypatch):
    service = ParseService()
    service._mock = False
    service._converter = None
    expected = ParseResult(page_count=1)
    calls: list[object] = []

    def fake_ensure():
        calls.append("ensure")
        service._converter = object()
        return service._converter

    def fake_docling_parse(source):
        calls.append(source)
        return expected

    monkeypatch.setattr(service, "_ensure", fake_ensure)
    monkeypatch.setattr(service, "_docling_parse", fake_docling_parse)

    assert service.parse(b"pdf", "sample.pdf", source_path="sample.pdf") is expected
    assert calls == ["ensure", "sample.pdf"]


@pytest.mark.parametrize(
    ("bbox", "expected"),
    [
        (
            SimpleNamespace(l=20, t=10, r=180, b=30, coord_origin="TOPLEFT"),
            {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
        ),
        (
            SimpleNamespace(l=20, t=90, r=180, b=70, coord_origin="BOTTOMLEFT"),
            {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
        ),
        (
            SimpleNamespace(l=-5, t=-5, r=205, b=105, coord_origin="TOPLEFT"),
            {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0},
        ),
    ],
)
def test_normalize_docling_bbox(bbox, expected):
    page_size = SimpleNamespace(width=200, height=100)

    assert _normalize_docling_bbox(bbox, page_size) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("bbox", "page_size"),
    [
        (
            SimpleNamespace(l=1, t=1, r=2, b=2, coord_origin="UNKNOWN"),
            SimpleNamespace(width=10, height=10),
        ),
        (
            SimpleNamespace(l=1, t=1, r=2, b=2, coord_origin="TOPLEFT"),
            SimpleNamespace(width=0, height=10),
        ),
        (
            SimpleNamespace(l=1, t=1, r=1, b=2, coord_origin="TOPLEFT"),
            SimpleNamespace(width=10, height=10),
        ),
    ],
)
def test_normalize_docling_bbox_rejects_invalid_geometry(bbox, page_size):
    assert _normalize_docling_bbox(bbox, page_size) is None
