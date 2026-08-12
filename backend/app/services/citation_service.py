"""引用服务：解析回答中的 [n] 标记，映射到重排后上下文的页码 / bbox。

- 模型被要求用 [n] 引用第 n 个上下文片段（n 从 1 起，对应重排后顺序）。
- 扫描全文按出现顺序去重提取引用编号，装配 citation 事件
  （docId/docName/page/bbox/snippet/sourceId/version/title/createdAt/processingMs）。
- 编号越界（>上下文数）视为无效，跳过（不报错，保证流式不中断）。
"""
from __future__ import annotations

import re

from app.schemas import RetrievedChunk

_CITE_RE = re.compile(r"\[(\d+)\]")


def parse_citation_indices(text: str) -> list[int]:
    return [int(m) for m in _CITE_RE.findall(text)]


def build_citations(
    text: str, ordered: list[RetrievedChunk], processing_ms: float | None = None
) -> list[dict]:
    """返回 citation 事件列表（按引用首次出现顺序去重）。"""
    out: list[dict] = []
    seen: set[int] = set()
    for idx in parse_citation_indices(text):
        if idx < 1 or idx > len(ordered) or idx in seen:
            continue
        seen.add(idx)
        rc = ordered[idx - 1]
        out.append(
            {
                "index": idx,
                "docId": rc.document_id,
                "docName": rc.doc_name,
                "page": rc.page_no,
                "bbox": rc.bbox,
                "snippet": rc.snippet,
                # 成熟度：citation 元数据（sourceId/version/title/createdAt 实现后必填）
                "sourceId": rc.source_id,
                "version": rc.version,
                "title": rc.title,
                "createdAt": rc.created_at,
                "processingMs": round(processing_ms, 2) if processing_ms is not None else None,
            }
        )
    return out
