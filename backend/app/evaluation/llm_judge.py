"""LLM-as-Judge 质量评分：faithfulness / relevance / completeness。

用 LLM 对每条生成式答案进行多维度打分（1-5 分），输出结构化报告。
评分 prompt 参考 RAGAS / TruLens 框架，适配中文场景。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.core import llm as llm_mod
from app.core import runtime_config
from app.evaluation.real_llm_runner import CTX_CHUNKS
from app.evaluation.public_runner import load_corpus

_JUDGE_SYSTEM = """你是一个严格的事实性问答评估专家。你需要根据给定的「文档片段」和「问题」，评估「回答」的质量。

评分维度（每项 1-5 分）：
1. Faithfulness（忠实度）：回答是否完全基于文档片段，没有编造信息
   - 5: 100% 基于文档，无任何编造
   - 4: 大部分基于文档，有极少量推断
   - 3: 有一定编造，但核心信息来自文档
   - 2: 大量编造或歪曲
   - 1: 完全编造或与文档无关

2. Relevance（相关性）：回答是否直接回答了问题
   - 5: 精准回答问题，信息完整
   - 4: 回答了问题，有少量冗余
   - 3: 部分回答了问题
   - 2: 答非所问或信息不足
   - 1: 完全不相关

3. Completeness（完整性）：回答是否覆盖了问题的所有方面
   - 5: 完整覆盖所有方面
   - 4: 覆盖了大部分方面
   - 3: 覆盖了关键方面
   - 2: 有明显遗漏
   - 1: 严重不完整

严格按以下 JSON 格式输出，不要输出其他内容：
{"faithfulness": N, "relevance": N, "completeness": N, "reason": "简要说明"}"""

_JUDGE_USER = """文档片段：
{context}

问题：{question}

回答：{answer}

请评估该回答质量（输出 JSON）："""


def _parse_judge_response(text: str) -> dict:
    """从 LLM 输出中提取 JSON 评分。"""
    text = (text or "").strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown code block 中提取
    if "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start) if "```" in text[start:] else len(text)
        try:
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass
    # 尝试找 { ... } 块
    if "{" in text and "}" in text:
        start = text.index("{")
        end = text.rindex("}") + 1
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return {"faithfulness": 0, "relevance": 0, "completeness": 0, "reason": f"parse_error: {text[:200]}"}


async def _judge_one(
    llm_client: llm_mod.LLMClient,
    question: str,
    context: str,
    answer: str,
) -> dict:
    """对单条答案进行 LLM-as-judge 评分。"""
    if not answer or answer.strip() == "":
        return {"faithfulness": 0, "relevance": 0, "completeness": 0,
                "reason": "empty_answer"}

    user_msg = _JUDGE_USER.format(
        context=context[:4000], question=question, answer=answer[:2000]
    )
    try:
        raw = await asyncio.wait_for(
            asyncio.ensure_future(
                _consume_stream(llm_client.stream(_JUDGE_SYSTEM, user_msg))
            ),
            timeout=30,
        )
        scores = _parse_judge_response(raw)
        # 校验分数范围
        for key in ("faithfulness", "relevance", "completeness"):
            v = scores.get(key, 0)
            if not isinstance(v, (int, float)) or v < 0 or v > 5:
                scores[key] = 0
        return scores
    except asyncio.TimeoutError:
        return {"faithfulness": 0, "relevance": 0, "completeness": 0,
                "reason": "judge_timeout"}
    except (RuntimeError, OSError, ValueError) as exc:
        return {"faithfulness": 0, "relevance": 0, "completeness": 0,
                "reason": f"judge_error: {exc}"}


async def _consume_stream(stream) -> str:
    parts = []
    async for piece in stream:
        parts.append(piece)
    return "".join(parts)


def judge_answers(
    report_path: str | Path,
    corpus: list[dict],
    llm_client: llm_mod.LLMClient | None = None,
) -> dict:
    """对 real_llm_runner 报告中的每条答案进行质量评分。

    返回 {per_query: [...], summary: {avg_faithfulness, avg_relevance, avg_completeness}}
    """
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    # 优先从 predictions 字段读取（含 answer），fallback 到 per_query
    predictions = report.get("predictions", [])
    if predictions:
        questions_map = {p["query_id"]: p for p in predictions}
    else:
        per_query = report.get("per_query", [])
        questions_map = {q["query_id"]: q for q in per_query}

    # 加载问题集
    from app.evaluation import public_dataset
    questions = public_dataset.load_questions()

    if llm_client is None:
        runtime_config.load_runtime_config()
        llm_client = llm_mod.LLMClient()
        backend, ready = llm_client.status()
        if not ready:
            raise RuntimeError(f"LLM 未就绪（{backend}），无法运行 judge")

    results = []

    async def _run():
        for q in questions:
            pq = questions_map.get(q["id"], {})
            answer = pq.get("answer", "")
            retrieved = pq.get("retrieved", [])

            # 拼接上下文（与生成时一致）
            context_parts = []
            for r in retrieved[:CTX_CHUNKS]:
                idx = r.get("chunk_index", 0)
                if 0 <= idx < len(corpus):
                    context_parts.append(f"[{idx+1}] {corpus[idx]['text'][:4000]}")
            context = "\n".join(context_parts) if context_parts else "(无检索结果)"

            # 使用 raw_answer（含推理过程）作为 judge 输入，但提取最终答案作为 preview
            from app.evaluation.real_llm_runner import _extract_final_answer
            final_answer = _extract_final_answer(answer)
            scores = await _judge_one(llm_client, q["query"], context, final_answer)
            scores["query_id"] = q["id"]
            scores["answer_type"] = q.get("answer_type", "")
            scores["unanswerable"] = q.get("unanswerable", False)
            scores["answer_preview"] = final_answer[:200] if final_answer else ""
            results.append(scores)

    asyncio.run(_run())

    # 聚合
    faithful = [r["faithfulness"] for r in results if r["faithfulness"] > 0]
    relevant = [r["relevance"] for r in results if r["relevance"] > 0]
    complete = [r["completeness"] for r in results if r["completeness"] > 0]

    summary = {
        "n_scored": len(results),
        "avg_faithfulness": round(sum(faithful) / len(faithful), 2) if faithful else 0,
        "avg_relevance": round(sum(relevant) / len(relevant), 2) if relevant else 0,
        "avg_completeness": round(sum(complete) / len(complete), 2) if complete else 0,
        "n_empty": sum(1 for r in results if not r.get("answer_preview")),
        "n_judge_errors": sum(1 for r in results if "error" in r.get("reason", "") or "timeout" in r.get("reason", "")),
    }

    return {"per_query": results, "summary": summary}


def main():
    import argparse

    runtime_config.load_runtime_config()
    parser = argparse.ArgumentParser(description="LLM-as-Judge 质量评分")
    parser.add_argument("report", help="real_llm_runner 生成的报告路径")
    parser.add_argument("--work-dir", default="work")
    parser.add_argument("--out", default="judge_report.json")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    data = load_corpus(work_dir)
    result = judge_answers(args.report, data["corpus"])

    out = work_dir / args.out
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    import os
    os.replace(tmp, out)

    s = result["summary"]
    print(
        f"judge OK: faithfulness={s['avg_faithfulness']:.2f} "
        f"relevance={s['avg_relevance']:.2f} completeness={s['avg_completeness']:.2f} "
        f"scored={s['n_scored']} errors={s['n_judge_errors']} | report -> {out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
