"""公开评测数据集：manifest 校验、DOI 确定性下载、PDF 文本提取、gold 验证。

职责边界：
- 只做数据准备与校验（fail-closed），不包含任何检索/生成逻辑，保证 gold 与管线隔离。
- 下载：DOI → urllib 跟随重定向 + User-Agent；临时文件 + 尺寸 + SHA-256 双重校验通过后
  rename 落盘；失败即删除，不留下半成品。
- 验证：answerable 题的每条 evidence 必须逐字出现在对应 physical_page 的 pypdf 提取
  文本中（归一化后子串匹配）；unanswerable 题的 unanswerable_keywords 必须在两份文档
  全文零命中。验证失败 = 数据集不合格，抛异常。
- 写入：JSONL 一律写临时文件后原子 rename，避免半截文件。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import urllib.request
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - 缺依赖时给出可读错误
    PdfReader = None  # type: ignore

_HERE = Path(__file__).resolve().parent
DATASET_DIR = _HERE / "datasets" / "nist_ai_rmf_public_v1"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
QUESTIONS_PATH = DATASET_DIR / "questions.jsonl"
USER_AGENT = "docrag-dataset-eval/1.0 (research; +https://github.com/moonbrigt/docrag)"

# manifest 必填字段（缺失即拒绝）
_REQUIRED_MANIFEST = {
    "id": str, "name": str, "description": str, "profile": str,
    "n_questions": int, "answerable_count": int, "unanswerable_count": int,
    "version": str, "created_by": str,
}
_REQUIRED_SOURCE = {
    "document_id": str, "filename": str, "doi": str, "url": str,
    "license": str, "license_url": str, "sha256": str,
    "size_bytes": int, "page_count": int,
}


def normalize_text(text: str) -> str:
    """归一化：NFKC（展开 ligature 等）+ 删除连字符及其相邻空白 + 空白折叠 + 小写。

    与 PDF 提取文本中 '-\n' 断行连字符保持一致的唯一可靠规则是同样删除连字符。
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s*-\s*", "", text)
    return " ".join(text.split()).lower()


# ---------------- manifest / questions 读取与校验 ----------------

def validate_manifest(manifest: dict) -> None:
    for field, ftype in _REQUIRED_MANIFEST.items():
        if field not in manifest or not isinstance(manifest[field], ftype):
            raise ValueError(f"manifest 缺少或类型错误的必填字段: {field}")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) == 0:
        raise ValueError("manifest.sources 必须是非空列表")
    for src in sources:
        for field, ftype in _REQUIRED_SOURCE.items():
            if field not in src or not isinstance(src[field], ftype):
                raise ValueError(f"manifest.sources 缺少必填字段: {field}")
        if len(src["sha256"]) != 64:
            raise ValueError(f"source {src['document_id']} 的 sha256 长度不是 64")
    counts = (
        manifest["n_questions"], manifest["answerable_count"],
        manifest["unanswerable_count"],
    )
    if counts[0] != counts[1] + counts[2]:
        raise ValueError("n_questions 必须等于 answerable_count + unanswerable_count")


def load_manifest(path: str | os.PathLike = MANIFEST_PATH) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_manifest(manifest)
    return manifest


def load_questions(path: str | os.PathLike = QUESTIONS_PATH) -> list[dict]:
    questions: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            questions.append(json.loads(line))
    return questions


def validate_questions(questions: list[dict], pages_by_doc: dict[str, list[str]]) -> None:
    """fail-closed 验证：evidence 必须在固定物理页；unanswerable 关键词全文零命中。"""
    ids: set[str] = set()
    for q in questions:
        if q["id"] in ids:
            raise ValueError(f"重复问题 id: {q['id']}")
        ids.add(q["id"])
        if q["unanswerable"]:
            pages_all = " ".join(" ".join(p) for p in pages_by_doc.values())
            for kw in q.get("unanswerable_keywords", []):
                if normalize_text(kw) in normalize_text(pages_all):
                    raise ValueError(
                        f"unanswerable 题 {q['id']} 关键词 {kw!r} 在文档中命中，验证失败"
                    )
            continue
        if not q["gold_pages"]:
            raise ValueError(f"answerable 题 {q['id']} 缺少 gold_pages")
        for gp in q["gold_pages"]:
            doc_pages = pages_by_doc.get(gp["document_id"])
            if doc_pages is None:
                raise ValueError(f"题 {q['id']} 引用了未知文档 {gp['document_id']}")
            page = gp["physical_page"]
            if not 1 <= page <= len(doc_pages):
                raise ValueError(
                    f"题 {q['id']} physical_page {page} 超出 {gp['document_id']} 范围"
                )
            if normalize_text(gp["evidence"]) not in normalize_text(doc_pages[page - 1]):
                raise ValueError(
                    f"题 {q['id']} 的 evidence 不在 {gp['document_id']} 物理页 {page} "
                    f"上（fail-closed，gold 不合格）"
                )


# ---------------- 下载与校验 ----------------

def _sha256_of(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download_file(url: str, dest: str | os.PathLike, expected_sha256: str,
                  expected_size: int) -> None:
    """DOI 确定性下载：临时文件 + 尺寸 + SHA-256 双重校验，失败即清理并抛错。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        with open(tmp, "wb") as f:
            f.write(data)
        if len(data) != expected_size:
            raise ValueError(
                f"尺寸校验失败: 期望 {expected_size} bytes, 实际 {len(data)} bytes"
            )
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha256:
            raise ValueError(
                f"SHA-256 校验失败: 期望 {expected_sha256}, 实际 {actual_sha}"
            )
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()


def ensure_sources(cache_dir: str | os.PathLike, manifest: dict | None = None) -> dict[str, Path]:
    """确保所有 source PDF 已下载且校验通过；返回 {document_id: Path}。"""
    manifest = manifest or load_manifest()
    cache_dir = Path(cache_dir)
    paths: dict[str, Path] = {}
    for src in manifest["sources"]:
        dest = cache_dir / src["filename"]
        if dest.exists():
            if _sha256_of(dest) != src["sha256"]:
                raise ValueError(
                    f"缓存 {dest} 的 SHA-256 与 manifest 不符，请删除后重新下载"
                )
        else:
            download_file(src["doi"], dest, src["sha256"], src["size_bytes"])
        paths[src["document_id"]] = dest
    return paths


# ---------------- PDF 文本提取与语料 ----------------

def extract_pages(pdf_path: str | os.PathLike) -> list[str]:
    if PdfReader is None:  # pragma: no cover
        raise RuntimeError("缺少依赖 pypdf，请安装 requirements-eval.txt")
    reader = PdfReader(str(pdf_path))
    return [(page.extract_text() or "") for page in reader.pages]


def build_corpus(pdf_path: str | os.PathLike, document_id: str,
                 start_page: int = 1) -> list[dict]:
    """每页一个 chunk，只含文本与页号，不含任何 gold 信息。

    start_page：正文起始物理页（封面/扉页/目录等无正文内容页不进入检索语料，
    但 gold 验证与 unanswerable 扫描仍覆盖全页）。
    """
    return [
        {"document_id": document_id, "physical_page": i, "text": text}
        for i, text in enumerate(extract_pages(pdf_path), start=1)
        if i >= start_page
    ]


# ---------------- 原子写入 ----------------

def atomic_write_jsonl(path: str | os.PathLike, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
