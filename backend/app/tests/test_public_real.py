"""真实管线评测逻辑自检（注入假服务，不加载真实模型）。

守护的三条非平凡逻辑：
1. 每题保留逐条指标，概览聚合可由 per_query 明细逐条核对（防孤岛回归）。
2. 真实检索→重排→引用的组装正确（retrieved/citations 结构）。
3. 弃答题：LLM 拒绝（<no-answer>）→ 空答案 + 无引用 → 才得分。
"""
from __future__ import annotations

from collections import deque

import numpy as np
import pytest

from app.evaluation import eval_metrics, public_real
from app.evaluation.public_real import NO_ANSWER_TOKEN

CORPUS = [
    {"chunk_index": 0, "document_id": "docA", "physical_page": 1,
     "text": "Risk is the composite measure of the probability and magnitude of consequences."},
    {"chunk_index": 1, "document_id": "docA", "physical_page": 2,
     "text": "NIST lists three bias categories: systemic, computational, human-cognitive."},
    {"chunk_index": 2, "document_id": "docB", "physical_page": 1,
     "text": "Insurance premium pricing rules are not discussed in this document."},
]

GOLD = {"document_id": "docA", "physical_page": 1, "printed_page": 1,
        "evidence": "composite measure"}


class FakeEmb:
    """固定向量：语料=单位阵；任意查询都近似 chunk 0（保证检索确定性）。"""

    def __init__(self):
        self._mock = False
        self._n = len(CORPUS)

    def embed(self, texts):
        eye = np.eye(self._n, dtype=np.float32)
        return ([eye[i] for i in range(len(texts))], [{} for _ in texts])

    def embed_one(self, text):
        eye = np.eye(self._n, dtype=np.float32)
        return eye[0], {}


class FakeRerank:
    def __init__(self):
        self._mock = False

    def score(self, query, passages):
        return [1.0] * len(passages)


class FakeLLM:
    """按调用顺序返回 canned 回答；status 非 mock。"""

    def __init__(self, answers: list[str]):
        self._answers = deque(answers)

    def status(self):
        return ("ollama", True)

    async def stream(self, system_prompt, user_prompt):
        text = self._answers.popleft()
        for i in range(0, len(text), 4):
            yield text[i:i + 4]


def _run():
    questions = [
        {"id": "a1", "query": "how is risk defined?", "answer_type": "exact",
         "gold_answers": ["composite measure"], "gold_pages": [GOLD],
         "language": "en", "tags": ["t"], "split": "test", "unanswerable": False},
        {"id": "u1", "query": "how should insurers set premiums?",
         "answer_type": "unanswerable", "gold_answers": [], "gold_pages": [],
         "language": "en", "tags": ["out"], "split": "test", "unanswerable": True},
    ]
    llm = FakeLLM(["composite measure", NO_ANSWER_TOKEN])
    preds = public_real.predict(CORPUS, questions, emb=FakeEmb(),
                                reranker_svc=FakeRerank(), llm_client=llm)
    return questions, preds


def test_predictions_shape_and_unanswerable_handling():
    questions, preds = _run()
    assert len(preds) == len(questions)
    by_q = {p["query_id"]: p for p in preds}

    a = by_q["a1"]
    assert a["answer"] == "composite measure"
    assert a["no_answer"] is False
    assert a["citations"] == [{"document_id": "docA", "physical_page": 1}]
    assert a["retrieved"][0]["chunk_index"] == 0

    u = by_q["u1"]
    assert u["no_answer"] is True
    assert u["answer"] == ""
    assert u["citations"] == []


def test_no_answer_token_maps_to_empty_citations():
    questions, preds = _run()
    # 弃答卷应得分：no_answer + 空答案 + 无引用
    assert eval_metrics.score_answer(preds[1], questions[1])["correct"]


def test_aggregate_derivable_from_per_query():
    questions, preds = _run()
    result = eval_metrics.evaluate(preds, questions)
    metrics = result["metrics"]
    rows = result["per_query"]
    assert len(rows) == len(questions)
    assert {r["query_id"] for r in rows} == {"a1", "u1"}
    # 概览 recall@1（answerable 平均）可由明细逐条重算核对
    ans_rows = [r for r in rows if not r["unanswerable"]]
    assert metrics["recall@1"] == pytest.approx(
        sum(r["recall@1"] for r in ans_rows) / len(ans_rows))