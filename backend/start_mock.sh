#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

export RAG_EMBED_MOCK=true
export RAG_RERANK_MOCK=true
export RAG_PARSE_MOCK=true
export RAG_LLM_MOCK=true

exec ./.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000