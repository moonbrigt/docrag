"""公开评测运行器：prepare | run | verify 三子命令。

- prepare：DOI 下载 + SHA-256 fail-closed 校验 + pypdf 提取语料（每页一个 chunk）+
  程序化验证全部 gold evidence 与 unanswerable 关键词，输出 work/eval_corpus.json。
- run：加载语料 → 确定性 BM25 + 词法重排 + 抽取式答案基线 → 指标 + CI + 切片 →
  报告 JSON 原子写入；同一输入重复运行产生字节一致的报告（确定性自检）。
- verify：复验语料、gold 与报告完整性。

报告含 manifest 信息、corpus 统计、per-query 明细、指标+CI、适配器 provenance
（Docling/BGE/reranker/LLM 均 NOT_RUN——本评测只跑无密钥工程基线，不使用任何
真实模型或付费 API）。
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

from app.evaluation import ablation, baselines, eval_metrics, public_dataset

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORK_DIR = REPO_ROOT / "work"
DEFAULT_REPORT = Path("eval_reports") / "public_nist_report.json"
CORPUS_FILE = "eval_corpus.json"
KS = (1, 3, 5)
RERANK_TOP_K = 5
PROVENANCE = {
    "docling": "NOT_RUN",
    "embedding_bge_m3": "NOT_RUN",
    "reranker_bge": "NOT_RUN",
    "llm": "NOT_RUN",
}


# ---------------- 语料 ----------------

def build_and_verify_corpus(work_dir: Path) -> dict:
    """下载/校验 PDF → 提取语料 → 验证 gold → 原子写 eval_corpus.json。"""
    manifest = public_dataset.load_manifest()
    cache_dir = work_dir / "source_cache"
    paths = public_dataset.ensure_sources(cache_dir, manifest)
    pages_by_doc = {doc_id: public_dataset.extract_pages(p) for doc_id, p in paths.items()}
    start_pages = {s["document_id"]: s.get("content_start_page", 1)
                   for s in manifest["sources"]}
    corpus = [
        chunk
        for doc_id, pages in pages_by_doc.items()
        for chunk in public_dataset.build_corpus(paths[doc_id], doc_id,
                                                 start_pages.get(doc_id, 1))
    ]
    questions = public_dataset.load_questions()
    public_dataset.validate_questions(questions, pages_by_doc)
    data = {
        "manifest_id": manifest["id"],
        "version": manifest["version"],
        "documents": list(paths.keys()),
        "corpus": corpus,
        "n_chunks": len(corpus),
        "pages_excluded": sum(max(0, start_pages.get(d, 1) - 1) for d in paths),
    }
    public_dataset.atomic_write_jsonl(work_dir / CORPUS_FILE, [data])
    return data


def load_corpus(work_dir: Path) -> dict:
    path = work_dir / CORPUS_FILE
    if not path.exists():
        return build_and_verify_corpus(work_dir)
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    data = rows[0]
    manifest = public_dataset.load_manifest()
    if data.get("manifest_id") != manifest["id"] or data.get("version") != manifest["version"]:
        raise ValueError("缓存语料与当前 manifest 版本不符，请重新 prepare")
    return data


# ---------------- 基线预测 ----------------

def _predict(corpus: list[dict], questions: list[dict], retriever, reranker) -> list[dict]:
    """统一预测循环：检索 → 重排 → 抽取式答案。只接收 corpus 与 query。"""
    answerer = baselines.ExtractiveAnswerer()
    predictions: list[dict] = []
    for q in questions:
        candidates = retriever.search(q["query"], RERANK_TOP_K * 3)
        top = reranker.rerank(q["query"], candidates, RERANK_TOP_K)
        chunk = corpus[top[0]["chunk_index"]] if top else None
        no_answer = bool(not chunk)
        if chunk is not None:
            q_terms = set(baselines.tokenize(q["query"]))
            text_terms = set(baselines.tokenize(chunk["text"]))
            no_answer = no_answer or not (q_terms & text_terms)
        answer = "" if no_answer else answerer.answer(q["query"], chunk)
        predictions.append({
            "query_id": q["id"],
            "retrieved": [
                {"document_id": c["document_id"], "physical_page": c["physical_page"],
                 "chunk_index": c["chunk_index"], "score": c["score"]}
                for c in top
            ],
            "citations": [
                {"document_id": c["document_id"], "physical_page": c["physical_page"]}
                for c in top[:RERANK_TOP_K]
            ],
            "answer": answer,
            "no_answer": no_answer,
        })
    return predictions


def run_baseline(corpus: list[dict], questions: list[dict]) -> list[dict]:
    """主基线：BM25 检索 + 词法重排 + 抽取式答案。"""
    retriever, reranker, _ = ablation.VARIANT_SPECS["bm25"](corpus)
    return _predict(corpus, questions, retriever, reranker)


def run_ablation(corpus: list[dict], questions: list[dict]) -> dict:
    """四个检索变体的预测集合：bm25 / dense_mock / hybrid / hybrid_rerank。"""
    return {
        name: _predict(corpus, questions, *(spec(corpus)[:2]))
        for name, spec in ablation.VARIANT_SPECS.items()
    }


# ---------------- 报告 ----------------

def build_report(work_dir: Path, ks=KS) -> dict:
    data = load_corpus(work_dir)
    manifest = public_dataset.load_manifest()
    questions = public_dataset.load_questions()
    predictions = run_baseline(data["corpus"], questions)
    result = eval_metrics.evaluate(predictions, questions, ks)
    # 消融对比：BM25 / mock 稠密 / 混合 / 混合+重排（同一指标口径）
    ablation_predictions = run_ablation(data["corpus"], questions)
    ablation_table = {}
    for variant, preds in ablation_predictions.items():
        res = eval_metrics.evaluate(preds, questions, ks)
        ablation_table[variant] = {
            "name": ablation.VARIANT_SPECS[variant](data["corpus"])[2],
            "metrics": {
                k: res["metrics"][k]
                for k in ("recall@1", "recall@3", "recall@5", "mrr", "ndcg@5",
                          "citation_recall", "citation_page_precision",
                          "answer_em", "answer_f1", "unanswerable_correct")
            },
        }
    report = {
        "profile": manifest["profile"],
        "manifest": {
            "id": manifest["id"], "name": manifest["name"],
            "version": manifest["version"], "created_by": manifest["created_by"],
            "n_questions": manifest["n_questions"],
            "answerable_count": manifest["answerable_count"],
            "unanswerable_count": manifest["unanswerable_count"],
            "sources": [
                {"document_id": s["document_id"], "filename": s["filename"],
                 "doi": s["doi"], "license": s["license"],
                 "license_url": s["license_url"], "sha256": s["sha256"],
                 "page_count": s["page_count"]}
                for s in manifest["sources"]
            ],
        },
        "corpus": {
            "documents": data["documents"], "n_chunks": data["n_chunks"],
            "n_chars": sum(len(c["text"]) for c in data["corpus"]),
            "pages_excluded": data.get("pages_excluded", 0),
            "source_cache": str(work_dir / "source_cache"),
        },
        "baseline": {
            "name": "bm25 + lexical-rerank + extractive-answer",
            "ks": list(ks), "rerank_top_k": RERANK_TOP_K,
            "deterministic": True, "keys": "none",
        },
        "metrics": result["metrics"],
        "ci": result["ci"],
        "slices": result["slices"],
        "ablation": ablation_table,
        "per_query": result["per_query"],
        "provenance": PROVENANCE,
    }
    return report


def _strip_ts(report: dict) -> str:
    clean = {k: v for k, v in report.items() if k not in ("created_at",)}
    return json.dumps(clean, sort_keys=True, ensure_ascii=False).encode("utf-8")


def cmd_prepare(args) -> int:
    work_dir = Path(args.work_dir)
    data = build_and_verify_corpus(work_dir)
    manifest = public_dataset.load_manifest()
    print(f"prepare OK: {data['n_chunks']} chunks, "
          f"docs={data['documents']}, manifest={manifest['id']}@{manifest['version']}")
    print(f"corpus -> {work_dir / CORPUS_FILE}")
    return 0


def cmd_run(args) -> int:
    work_dir = Path(args.work_dir)
    report = build_report(work_dir, ks=KS)
    report["created_at"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")
    # 确定性自检：同输入再跑一遍（不落盘），比较去除时间戳后的字节
    rerun = build_report(work_dir, ks=KS)
    report["determinism"] = {
        "verified": _strip_ts(rerun) == _strip_ts(report),
        "method": "同输入重复运行两次，报告（去除 created_at 后）字节一致",
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = work_dir / out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out)
    print(f"run OK: {report['metrics']['eligible']}/{report['metrics']['total']} "
          f"eligible, report -> {out}")
    return 0


def cmd_verify(args) -> int:
    work_dir = Path(args.work_dir)
    data = load_corpus(work_dir)
    pages_by_doc: dict[str, list[str]] = {}
    cache = work_dir / "source_cache"
    manifest = public_dataset.load_manifest()
    paths = public_dataset.ensure_sources(cache, manifest)
    pages_by_doc = {doc_id: public_dataset.extract_pages(p) for doc_id, p in paths.items()}
    public_dataset.validate_questions(public_dataset.load_questions(), pages_by_doc)
    print(f"verify OK: {data['n_chunks']} chunks, gold 全部通过（{manifest['n_questions']} 题）")
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = work_dir / report_path
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        det = report.get("determinism", {})
        print(f"report OK: determinism.verified={det.get('verified')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="public_runner",
                                     description="NIST 公开评测：prepare | run | verify")
    parser.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR),
                        help="工作目录（语料缓存与报告输出，默认 <repo>/work）")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare", help="下载+校验 PDF，提取语料，验证 gold")
    p_run = sub.add_parser("run", help="跑基线评测并输出报告 JSON")
    p_run.add_argument("--out", default=str(DEFAULT_REPORT),
                       help="报告输出路径（相对 work-dir 或绝对路径）")
    p_verify = sub.add_parser("verify", help="复验语料/gold/报告")
    p_verify.add_argument("--report", default=str(DEFAULT_REPORT), help="报告路径")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        return cmd_prepare(args)
    if args.command == "run":
        return cmd_run(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
