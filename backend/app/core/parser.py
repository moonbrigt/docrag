"""解析服务：Docling（DocumentConverter + HybridChunker）与 mock 降级。

- 真实路径：PDF -> Docling 文档 -> HybridChunker 结构化分块（按标题/段落/表格边界），
  每块保留 page_no（必带）与归一化 bbox（可选）与 section 元数据。
- Mock 路径：无 Docling / 离线时，基于文件名生成确定性合成分块，
  覆盖「上传 -> 分块 -> 索引 -> 检索 -> 评测」全链路，便于 CI 验证。
- PDF 解析失败（加密/损坏）应抛出明确异常，由流水线置 failed。
"""
from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass, field

from app.config import get_settings
from app.core import runtime_config
from app.core.embeddings import effective_embed_config

_settings = get_settings()


def effective_parse_backend() -> str:
    """当前生效的解析后端：运行时覆盖 > env 默认。"""
    if _settings.PARSE_MOCK and runtime_config.get("parse_backend") is None:
        return "mock"  # env 显式 RAG_PARSE_MOCK=true 时默认 mock
    return runtime_config.effective("parse_backend", _settings.PARSE_BACKEND)


@dataclass
class ParsedChunk:
    content: str
    page_no: int
    bbox: dict | None = None
    section: str | None = None


@dataclass
class ParseResult:
    page_count: int
    chunks: list[ParsedChunk] = field(default_factory=list)


def _normalize_docling_bbox(bbox, page_size) -> dict[str, float] | None:
    """将 Docling 页面坐标转换为前端使用的 top-left、0–1 坐标。"""
    try:
        page_width = float(page_size.width)
        page_height = float(page_size.height)
        left = float(bbox.l)
        top = float(bbox.t)
        right = float(bbox.r)
        bottom = float(bbox.b)
        coord_origin = getattr(bbox, "coord_origin", "TOPLEFT")
        origin = str(getattr(coord_origin, "value", coord_origin)).upper()
    except (AttributeError, TypeError, ValueError):
        return None

    values = (page_width, page_height, left, top, right, bottom)
    if (
        page_width <= 0
        or page_height <= 0
        or not all(math.isfinite(value) for value in values)
    ):
        return None

    if origin == "BOTTOMLEFT":
        top, bottom = page_height - top, page_height - bottom
    elif origin != "TOPLEFT":
        return None

    left, right = sorted((left / page_width, right / page_width))
    top, bottom = sorted((top / page_height, bottom / page_height))
    left, top, right, bottom = (
        min(1.0, max(0.0, value)) for value in (left, top, right, bottom)
    )
    if right <= left or bottom <= top:
        return None
    return {"left": left, "top": top, "right": right, "bottom": bottom}


class ParseService:
    def __init__(self) -> None:
        self._converter = None
        self._lock = threading.Lock()

    def status(self) -> tuple[str, bool]:
        if effective_parse_backend() == "mock":
            return ("mock", True)
        try:
            self._ensure()
            return (effective_parse_backend(), True)
        except Exception:
            return (effective_parse_backend(), False)

    def is_ready(self) -> bool:
        return self.status()[1]

    def reload(self) -> None:
        """丢弃已加载的 Docling 转换器，下次调用按最新后端重建。"""
        self._converter = None

    def _ensure(self):
        if self._converter is not None:
            return self._converter
        if effective_parse_backend() == "mock":
            return None
        with self._lock:
            if self._converter is None:
                from docling.document_converter import DocumentConverter

                self._converter = DocumentConverter()
        return self._converter

    def parse(self, file_bytes: bytes, filename: str, source_path=None) -> ParseResult:
        """解析 PDF 字节流 / 路径，返回分页分块结果。

        file_bytes 与 source_path 二选一；source_path 优先（Docling 直接吃路径）。
        """
        if effective_parse_backend() == "mock":
            return self._mock_parse(file_bytes, filename)
        self._ensure()
        return self._docling_parse(source_path or file_bytes)

    # ---------------- 真实路径 ----------------
    def _docling_parse(self, source) -> ParseResult:
        from docling.chunking import HybridChunker

        conv = self._ensure()
        try:
            result = conv.convert(source)
        except Exception as exc:
            raise RuntimeError(f"PDF 解析失败：文件可能加密或损坏（{exc}）") from exc
        doc = result.document
        page_count = len(doc.pages) if hasattr(doc, "pages") else 1
        chunker = HybridChunker(tokenizer=effective_embed_config()["model"], max_tokens=512)
        chunks: list[ParsedChunk] = []
        try:
            raw_chunks = list(chunker.chunk(doc))
        except Exception:
            # 个别文档 HybridChunker 异常时退回按页文本切分
            raw_chunks = []
            for pno, page in enumerate(doc.pages, start=1):
                text = page.text or ""
                if text.strip():
                    raw_chunks.append(_PlainChunk(text, pno, None))

        for ch in raw_chunks:
            page_nos = set()
            bboxes_by_page: dict[int, dict[str, float]] = {}
            headings = getattr(ch.meta, "headings", None) or []
            for item in getattr(ch.meta, "doc_items", []):
                for prov in getattr(item, "prov", []) or []:
                    prov_page_no = getattr(prov, "page_no", None)
                    if prov_page_no is not None:
                        page_nos.add(prov_page_no)
                    b = getattr(prov, "bbox", None)
                    if (
                        b is not None
                        and prov_page_no is not None
                        and prov_page_no not in bboxes_by_page
                    ):
                        page = doc.pages.get(prov_page_no)
                        if page is not None:
                            normalized = _normalize_docling_bbox(
                                b, getattr(page, "size", None)
                            )
                            if normalized is not None:
                                bboxes_by_page[prov_page_no] = normalized
            page_no = min(page_nos) if page_nos else 1
            bbox = bboxes_by_page.get(page_no)
            section = " > ".join(headings) if headings else None
            chunks.append(
                ParsedChunk(
                    content=getattr(ch, "text", str(ch)),
                    page_no=page_no,
                    bbox=bbox,
                    section=section,
                )
            )
        return ParseResult(page_count=page_count, chunks=chunks)

    # ---------------- mock 路径 ----------------
    def _mock_parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        seed = int(hashlib.md5(filename.encode("utf-8")).hexdigest(), 16)
        pages = [
            "引言：本文档介绍产品背景与目标读者。第一章概述系统架构。",
            "第二章讨论数据流水线与解析流程，强调页码溯源的重要性。",
            "第三章给出核心结论与性能评测结果，验证了混合检索的有效性。",
            "第四章列出风险与合规要求，包括数据加密与访问控制。",
            "第五章为治理与组织架构，明确各委员会职责。",
        ]
        n = 5
        chunks: list[ParsedChunk] = []
        for i, text in enumerate(pages):
            # 用文件名种子做轻微扰动，保证同一文件可复现
            content = f"[{filename}] {text}"
            chunks.append(
                ParsedChunk(
                    content=content,
                    page_no=i + 1,
                    bbox={
                        "left": 0.1,
                        "top": 0.1 + i * 0.15,
                        "right": 0.9,
                        "bottom": 0.2 + i * 0.15,
                    },
                    section=f"第{i + 1}章",
                )
            )
        _ = seed
        return ParseResult(page_count=n, chunks=chunks)


class _PlainChunk:
    """Docling 不可用时的兜底分块对象，结构与 Chunk 的最小接口对齐。"""

    def __init__(self, text: str, page_no: int, headings):
        self.text = text
        self.meta = _Meta(page_no, headings)


class _Meta:
    def __init__(self, page_no, headings):
        self.doc_items = [_Item(page_no)]
        self.headings = headings or []


class _Item:
    def __init__(self, page_no):
        self.prov = [_Prov(page_no)]


class _Prov:
    def __init__(self, page_no):
        self.page_no = page_no
        self.bbox = None
