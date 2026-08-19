"""重排服务：bge-reranker-v2-m3（CrossEncoder）与 mock 降级。

- 真实后端：sentence-transformers 的 CrossEncoder，对 (query, passage) 打相关分。
- Mock 后端：以词元重叠度作为相关分，供离线 / CI 验证重排链路。
- 未就绪且非 mock 时 status().ready=False，调用方应返回 503。
"""
from __future__ import annotations

import threading

import numpy as np

from app.config import get_settings
from app.core.embeddings import _tokenize

_settings = get_settings()


class RerankService:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._mock = _settings.RERANK_MOCK
        self._backend_name = "mock" if self._mock else _settings.RERANK_BACKEND
        self._load_error: str | None = None

    def status(self) -> tuple[str, bool]:
        if self._mock:
            return ("mock", True)
        if self._ensure() is not None:
            return (self._backend_name, True)
        return (self._backend_name, False)

    def is_ready(self) -> bool:
        return self.status()[1]

    def reload(self) -> None:
        """丢弃已加载模型，下次调用按最新计算加速档位重建（GPU 开关热生效）。"""
        self._model = None
        self._load_error = None

    def _ensure(self):
        if self._model is not None:
            return self._model
        if self._mock:
            return None
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import CrossEncoder

                    from app.core import accelerator

                    model_id = "BAAI/bge-reranker-v2-m3"
                    local = f"{_settings.MODEL_DIR.rstrip('/')}/bge-reranker-v2-m3"
                    device = accelerator.device()
                    try:
                        self._model = CrossEncoder(local, device=device)
                    except Exception:
                        self._model = CrossEncoder(model_id, device=device)
                except Exception as exc:
                    # 真实后端加载失败：仅显式 mock 才降级；否则保持未就绪 -> 503
                    self._load_error = str(exc)
                    self._model = None
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        """返回与 passages 等长的相关分（升序无要求，数值越大越相关）。"""
        if self._mock or self._ensure() is None:
            q_tokens = set(_tokenize(query))
            scores: list[float] = []
            for p in passages:
                p_tokens = set(_tokenize(p))
                if not q_tokens or not p_tokens:
                    scores.append(0.0)
                    continue
                inter = len(q_tokens & p_tokens)
                union = len(q_tokens | p_tokens)
                scores.append(inter / union if union else 0.0)
            return scores

        pairs = [(query, p) for p in passages]
        raw = self._model.predict(pairs, show_progress_bar=False)
        return [float(np.asarray(x).reshape(-1)[0]) for x in raw]
