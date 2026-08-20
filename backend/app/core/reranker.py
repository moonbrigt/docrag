"""重排服务：bge-reranker-v2-m3（CrossEncoder）与 mock 降级。

- 真实后端：sentence-transformers 的 CrossEncoder，对 (query, passage) 打相关分。
- Mock 后端：以词元重叠度作为相关分，供离线 / CI 验证重排链路。
- 未就绪且非 mock 时 status().ready=False，调用方应返回 503。
"""
from __future__ import annotations

import threading

import numpy as np

from app.config import get_settings
from app.core import runtime_config
from app.core.embeddings import _tokenize

_settings = get_settings()


def effective_rerank_config() -> dict:
    """当前生效的重排配置：运行时覆盖 > env 默认。"""
    backend = runtime_config.effective("rerank_backend", _settings.RERANK_BACKEND)
    if _settings.RERANK_MOCK and runtime_config.get("rerank_backend") is None:
        backend = "mock"
    return {"backend": backend, "model": runtime_config.effective("rerank_model", _settings.RERANK_MODEL)}


def _is_mock() -> bool:
    return effective_rerank_config()["backend"] == "mock"


class RerankService:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    def status(self) -> tuple[str, bool]:
        if _is_mock():
            return ("mock", True)
        if self._ensure() is not None:
            return (effective_rerank_config()["backend"], True)
        return (effective_rerank_config()["backend"], False)

    def is_ready(self) -> bool:
        return self.status()[1]

    def reload(self) -> None:
        """丢弃已加载模型，下次调用按最新配置（模型名 / 计算加速档位）重建。"""
        self._model = None
        self._load_error = None

    def _ensure(self):
        if self._model is not None:
            return self._model
        if _is_mock():
            return None
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import CrossEncoder

                    from app.core import accelerator

                    model = effective_rerank_config()["model"]
                    slug = model.rsplit("/", 1)[-1]
                    local = f"{_settings.MODEL_DIR.rstrip('/')}/{slug}"
                    device = accelerator.device()
                    try:
                        self._model = CrossEncoder(local, device=device)
                    except Exception:
                        self._model = CrossEncoder(model, device=device)
                except Exception as exc:
                    # 真实后端加载失败：仅显式 mock 才降级；否则保持未就绪 -> 503
                    self._load_error = str(exc)
                    self._model = None
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        """返回与 passages 等长的相关分（升序无要求，数值越大越相关）。"""
        if _is_mock() or self._ensure() is None:
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
