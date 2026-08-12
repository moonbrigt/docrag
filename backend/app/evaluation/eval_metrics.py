"""评测指标：检索质量、引用准确性、答案正确性、置信区间与切片。

- 引用以 (document_id, physical_page) 元组判对错：跨文档同页号不算命中，杜绝混淆。
- 弃答（unanswerable）：仅当 no_answer 声明 + 空答案 + 无引用才得分。
- CI：固定 seed 的 bootstrap 95% CI（均值类）与 Wilson CI（比例类），保证可复现。
- 本模块只负责打分，gold 仅作为评估输入，不进入任何检索/生成管线。
"""
from __future__ import annotations

import math
import re
from statistics import mean

import numpy as np

from app.evaluation.baselines import tokenize
from app.evaluation.public_dataset import normalize_text

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_K_DEFAULT = (1, 3, 5)


def _tokens(text: str) -> set[str]:
    return set(tokenize(text))


def _numbers(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUMBER_RE.finditer(text):
        raw = m.group(0).replace(",", "")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


# ---------------- 置信区间 ----------------

def bootstrap_ci(values: list[float], n_boot: int = 1000, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    """对 per-query 分数做 bootstrap 95% CI（固定 seed，确定性）。"""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = np.array([
        arr[rng.integers(0, len(arr), size=len(arr))].mean() for _ in range(n_boot)
    ])
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963985  # alpha=0.05
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


# ---------------- 答案打分 ----------------

def score_answer(pred: dict, q: dict) -> dict:
    """返回 {correct, score, eligible, detail}。"""
    atype = q["answer_type"]
    answer = (pred.get("answer") or "").strip()
    citations = pred.get("citations") or []
    if atype == "unanswerable":
        correct = bool(pred.get("no_answer")) and not answer and not citations
        return {"correct": correct, "score": 1.0 if correct else 0.0,
                "eligible": True, "detail": {"no_answer": bool(pred.get("no_answer"))}}
    if not answer:
        return {"correct": False, "score": 0.0, "eligible": False, "detail": {}}
    norm_ans = normalize_text(answer)
    if atype == "exact":
        hits = [normalize_text(a) for a in q.get("gold_answers", [])]
        correct = norm_ans in hits
        return {"correct": correct, "score": 1.0 if correct else 0.0,
                "eligible": True, "detail": {"matched": norm_ans}}
    if atype == "set":
        gold = {normalize_text(a) for a in q.get("gold_answers", [])}
        toks = {t for t in _tokens(answer) if t}  # 预测集合：答案中的词/字
        hit = gold & toks
        prec = len(hit) / len(toks) if toks else 0.0
        rec = len(hit) / len(gold) if gold else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        correct = f1 >= 1.0  # 集合完全命中才算对（gold 全集覆盖）
        return {"correct": correct, "score": f1, "eligible": True,
                "detail": {"precision": prec, "recall": rec, "f1": f1}}
    if atype == "rubric":
        points = [normalize_text(p) for p in q.get("rubric", {}).get("points", [])]
        min_points = q.get("rubric", {}).get("min_points", 1)
        hits = sum(1 for p in points if p in norm_ans)
        ratio = hits / len(points) if points else 0.0
        correct = hits >= min_points
        evidence = " ".join(normalize_text(g["evidence"]) for g in q.get("gold_pages", []))
        ev_toks = _tokens(evidence)
        ans_toks = _tokens(answer)
        inter = len(ev_toks & ans_toks)
        f1 = 2 * inter / (len(ev_toks) + len(ans_toks)) if (ev_toks and ans_toks) else 0.0
        return {"correct": correct, "score": ratio, "eligible": True,
                "detail": {"points_hit": hits, "points_total": len(points), "f1": f1}}
    if atype == "numeric":
        num = q.get("numeric", {})
        gold_value = num.get("value")
        tol = num.get("tolerance", {})
        pred_nums = _numbers(answer)
        matched = False
        if gold_value is not None:
            for v in pred_nums:
                if tol.get("type") == "absolute":
                    matched |= abs(v - gold_value) <= tol.get("value", 0)
                else:
                    rel = tol.get("value", 0)
                    matched |= abs(v - gold_value) <= rel * abs(gold_value)
        return {"correct": matched, "score": 1.0 if matched else 0.0,
                "eligible": True, "detail": {"numbers": pred_nums, "gold": gold_value}}
    return {"correct": False, "score": 0.0, "eligible": False, "detail": {}}


# ---------------- 检索 / 引用指标（单条） ----------------

def _gold_pages(q: dict) -> set[tuple[str, int]]:
    return {(g["document_id"], g["physical_page"]) for g in q.get("gold_pages", [])}


def _hard_negatives(q: dict, questions: list[dict]) -> set[tuple[str, int]]:
    """hard negatives：其他查询的 gold 页中，与本题同文档错页或跨文档同页号的页。"""
    gold = _gold_pages(q)
    mine = {(g["document_id"]) for g in q.get("gold_pages", [])}
    hn: set[tuple[str, int]] = set()
    for other in questions:
        if other["id"] == q["id"]:
            continue
        for g in other.get("gold_pages", []):
            if g["document_id"] in mine and (g["document_id"], g["physical_page"]) not in gold:
                hn.add((g["document_id"], g["physical_page"]))  # 同文档错页
            elif g["document_id"] not in mine:
                hn.add((g["document_id"], g["physical_page"]))  # 跨文档
    return hn


def per_query_metrics(pred: dict, q: dict, questions: list[dict], ks=_K_DEFAULT) -> dict:
    gold = _gold_pages(q)
    retrieved = pred.get("retrieved", [])[: max(ks)]
    ranked = [(r["document_id"], r["physical_page"]) for r in retrieved]
    out: dict = {"query_id": q["id"], "answer_type": q["answer_type"],
                 "unanswerable": bool(q["unanswerable"])}
    for k in ks:
        top = ranked[:k]
        top_set = set(top)
        inter = len(gold & top_set)
        out[f"recall@{k}"] = inter / len(gold) if gold else 0.0
        out[f"precision@{k}"] = inter / k if k else 0.0
        out[f"hit@{k}"] = 1.0 if inter > 0 else 0.0
        hn = _hard_negatives(q, questions)
        hn_top = hn & top_set
        out[f"hard_negative_recall@{k}"] = len(hn_top) / len(hn) if hn else 0.0
    # MRR / nDCG@max(k)
    kmax = max(ks)
    rank = next((i + 1 for i, item in enumerate(ranked) if item in gold), None)
    out["mrr"] = 1.0 / rank if rank else 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, item in enumerate(ranked[:kmax]) if item in gold)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), kmax)))
    out[f"ndcg@{kmax}"] = dcg / idcg if idcg else 0.0
    # 引用准确性（(doc, page) 元组级）
    citations = pred.get("citations") or []
    cit_set = set()
    cit_hit = 0
    for c in citations:
        key = (c["document_id"], c["physical_page"])
        if key in cit_set:
            continue
        cit_set.add(key)
        if key in gold:
            cit_hit += 1
    out["citation_page_precision"] = cit_hit / len(cit_set) if cit_set else 0.0
    out["citation_recall"] = len(cit_set & gold) / len(gold) if gold else 0.0
    out["citation_count"] = len(cit_set)
    out["hard_negative_citations"] = len(cit_set & _hard_negatives(q, questions))
    # 答案
    ans = score_answer(pred, q)
    out["answer_correct"] = 1.0 if ans["correct"] else 0.0
    out["answer_score"] = ans["score"]
    out["answer_eligible"] = ans["eligible"]
    out["answer_detail"] = ans["detail"]
    return out


# ---------------- 聚合 ----------------

def _aggregate(rows: list[dict], n: int) -> dict:
    """rows 为 per-query 指标 dict 列表；n 为参与该组指标平均的查询数。

    检索类指标只对 answerable 题平均（unanswerable 题无 gold 页，recall/mrr 恒 0，
    不应稀释检索质量）；答案类指标按 eligible 平均。
    """
    fields = [k for k in rows[0] if k.startswith(("recall@", "precision@", "hit@",
              "hard_negative_recall@", "ndcg@", "mrr"))] if rows else []
    agg: dict = {}
    for f in fields:
        vals = [r[f] for r in rows]
        agg[f] = sum(vals) / n if n else 0.0
    cit = [r["citation_page_precision"] for r in rows if r["citation_count"] > 0]
    agg["citation_page_precision"] = mean(cit) if cit else 0.0
    agg["citation_page_precision_eligible"] = len(cit)
    agg["citation_recall"] = (sum(r["citation_recall"] for r in rows) / n) if n else 0.0
    agg["hard_negative_citation_rate"] = (
        sum(r["hard_negative_citations"] for r in rows) /
        sum(r["citation_count"] for r in rows) if any(r["citation_count"] for r in rows) else 0.0
    )
    eligible = [r for r in rows if r["answer_eligible"]]
    agg["answer_em"] = sum(r["answer_correct"] for r in eligible) / len(eligible) if eligible else 0.0
    agg["answer_f1"] = mean(r["answer_score"] for r in eligible) if eligible else 0.0
    agg["eligible"] = len(eligible)
    agg["total"] = n
    return agg


def build_ci(rows: list[dict], n: int) -> dict:
    """对宏平均指标给出 bootstrap CI；对比例型指标另附 Wilson CI。"""
    fields = [k for k in rows[0] if k.startswith(("recall@", "precision@", "hit@",
              "hard_negative_recall@", "ndcg@", "mrr"))] if rows else []
    ci: dict = {}
    for f in fields:
        vals = [r[f] for r in rows]
        lo, hi = bootstrap_ci(vals)
        successes = round(sum(vals))
        wlo, whi = wilson_ci(successes, n)
        ci[f] = {"bootstrap": [round(lo, 4), round(hi, 4)], "wilson": [round(wlo, 4), round(whi, 4)]}
    return ci


def slice_metrics(rows: list[dict], questions: list[dict]) -> dict:
    by_q = {r["query_id"]: r for r in rows}
    out: dict = {}
    for dim in ("language", "answer_type", "tag", "document"):
        groups: dict[str, list[dict]] = {}
        for q in questions:
            key = q.get("language", "en") if dim == "language" else (
                q.get("answer_type") if dim == "answer_type" else (
                    (q.get("tags") or [])[0] if dim == "tag" else
                    q["gold_pages"][0]["document_id"] if q["gold_pages"] else "unanswerable"
                )
            )
            groups.setdefault(key, []).append(by_q[q["id"]])
        out[dim] = {
            key: _aggregate(group, len(group)) for key, group in sorted(groups.items())
        }
    return out


def evaluate(predictions: list[dict], questions: list[dict], ks=_K_DEFAULT) -> dict:
    """predictions: 与 questions 同序的预测（或按 query_id 对齐后重排）。"""
    by_q = {p["query_id"]: p for p in predictions}
    rows = [per_query_metrics(by_q[q["id"]], q, questions, ks) for q in questions]
    n = len(rows)
    # 检索类指标只对 answerable 题平均（unanswerable 无 gold 页，恒 0）
    retrieval_rows = [r for r in rows if not r["unanswerable"]]
    metrics = _aggregate(retrieval_rows, len(retrieval_rows))
    metrics["retrieval_eligible"] = len(retrieval_rows)
    metrics["retrieval_total"] = n
    metrics["total"] = n  # eligible/total：可评答案题数 / 全部题数（含 unanswerable）
    unans = [r for r in rows if r["unanswerable"]]
    metrics["unanswerable_correct"] = (
        sum(r["answer_correct"] for r in unans) / len(unans) if unans else None
    )
    return {
        "metrics": metrics,
        "ci": build_ci(retrieval_rows, len(retrieval_rows)),
        "slices": slice_metrics(rows, questions),
        "per_query": rows,
        "num_queries": n,
    }
