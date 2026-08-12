"""确定性无密钥基线：BM25 检索 + 词法重排 + 抽取式句子答案。

- 纯 Python + stdlib 实现，不依赖任何外部服务/密钥/模型权重，同输入必得同输出。
- 构造/调用接口只接收 corpus 与 query，gold 绝不进入管线。
- 中文 tokenize 采用字符级（每个汉字一个 token），英文按单词，兼容中英混合查询。
"""
from __future__ import annotations

import math
import re

# 中文按字、英文/数字按词；NFKC 展开全角与 ligature 后处理
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?|[^。！？!?；;\n]+$")


def stem(tok: str) -> str:
    """轻量词干化：-ly/-ing/-ed 后缀与常见复数（-ies→y、-s 去除）。

    有意保持简单：不追求语言学完备（如 processes→process 不做），
    只解决查询/文档最常见的形式差异（复数、进行时、副词）。
    """
    if not tok or tok.isdigit() or len(tok) <= 4:
        return tok
    if tok.endswith("ly") and len(tok) > 6:
        return tok[:-2]
    if tok.endswith("ing") and len(tok) > 6:
        return tok[:-3]
    if tok.endswith("ed") and len(tok) > 5:
        return tok[:-2]
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    if tok.endswith("s") and len(tok) > 3:
        return tok[:-1]
    return tok


def tokenize(text: str) -> list[str]:
    """中英混合分词（英文词干化；中文按字），供检索/重排/答案评估统一使用。"""
    return [stem(t) for t in _TOKEN_RE.findall(text.lower())]


class BM25Retriever:
    """经典 BM25（k1=1.5, b=0.75），语料为每页一个 chunk。"""

    def __init__(self, corpus: list[dict], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus = corpus
        self.k1, self.b = k1, b
        self.doc_tokens: list[list[str]] = [tokenize(c["text"]) for c in corpus]
        self.doc_lens = [len(toks) for toks in self.doc_tokens]
        self.avgdl = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 0.0
        self.df: dict[str, int] = {}
        for toks in self.doc_tokens:
            for tok in set(toks):
                self.df[tok] = self.df.get(tok, 0) + 1
        self.n = len(corpus)

    def _idf(self, tok: str) -> float:
        df = self.df.get(tok, 0)
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))

    def _score(self, toks: list[str], doc_toks: list[str], doc_len: int) -> float:
        tf: dict[str, int] = {}
        for t in doc_toks:
            tf[t] = tf.get(t, 0) + 1
        denom = self.k1 * (1.0 - self.b + self.b * doc_len / self.avgdl)
        return sum(
            self._idf(t) * (tf.get(t, 0) * (self.k1 + 1.0)) / (tf.get(t, 0) + denom)
            for t in set(toks)
        )

    def search(self, query: str, k: int) -> list[dict]:
        qtoks = tokenize(query)
        scored = [
            (self._score(qtoks, doc_toks, doc_len), idx)
            for idx, (doc_toks, doc_len) in enumerate(zip(self.doc_tokens, self.doc_lens))
        ]
        scored.sort(key=lambda x: (-x[0], x[1]))  # 确定性：同分按 chunk 序
        return [
            {
                "chunk_index": idx,
                "document_id": self.corpus[idx]["document_id"],
                "physical_page": self.corpus[idx]["physical_page"],
                "score": score,
            }
            for score, idx in scored[:k]
            if score > 0.0
        ]


class LexicalReranker:
    """词法重排：BM25 分数 × (1 + 查询词命中率)，命中率=候选文本中出现的查询 token 比例。

    词法信号只做小幅调制，不推翻 BM25 的全局统计序（对中文查询，单字 token
    命中是弱信号，纯词法排序会产生噪声）；tie 保持 chunk 序（确定性）。
    """

    def __init__(self, corpus: list[dict]) -> None:
        self.corpus = corpus

    def rerank(self, query: str, candidates: list[dict], k: int) -> list[dict]:
        qtoks = set(tokenize(query))
        if not qtoks or not candidates:
            return candidates[:k]
        ranked = []
        for cand in candidates:
            text = self.corpus[cand["chunk_index"]]["text"]
            hit = len(qtoks & set(tokenize(text))) / len(qtoks)
            score = cand.get("score", 0.0)
            ranked.append((-(score * (1.0 + hit)), cand["chunk_index"], cand))
        ranked.sort()
        return [cand for _, _, cand in ranked[:k]]


class ExtractiveAnswerer:
    """抽取式答案：对 numeric 题提取数字；其余返回与查询词重合度最高的句子。"""

    def answer(self, query: str, chunk: dict) -> str:
        text = chunk.get("text", "")
        qtoks = set(tokenize(query))
        if not text:
            return ""
        if any(t.isdigit() for t in qtoks):
            return self._best_sentence(text, qtoks)
        sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]
        if not sentences:
            return text[:500]
        best = max(
            sentences,
            key=lambda s: (len(qtoks & set(tokenize(s))), len(s)),
        )
        return best[:1000]

    @staticmethod
    def _best_sentence(text: str, qtoks: set[str]) -> str:
        sentences = [s.strip() for s in _SENTENCE_RE.findall(text) if s.strip()]
        if not sentences:
            return text[:1000]
        best = max(
            sentences,
            key=lambda s: (len(qtoks & set(tokenize(s))), len(s)),
        )
        return best[:1000]

    @staticmethod
    def extract_numbers(text: str) -> list[float]:
        """提取文本中的数字（含千分位/小数点），用于 numeric 题答案评估。"""
        out: list[float] = []
        for m in _NUMBER_RE.finditer(text):
            raw = m.group(0).replace(",", "")
            try:
                out.append(float(raw))
            except ValueError:
                continue
        return out
