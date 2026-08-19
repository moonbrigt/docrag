"""嵌入服务：bge-m3（dense 1024 + sparse）与确定性 mock 降级。

- 真实后端：FlagEmbedding 的 BGEM3FlagModel，懒加载，权重首次使用时拉取。
- Mock 后端：基于词元哈希的确定性向量（L2 归一化），供离线 / CI 跑通检索与评测，
  不下载 2.2GB 权重。
- 模型未就绪且非 mock 模式时，status().ready=False，调用方应返回 503。
"""
from __future__ import annotations

import hashlib
import re
import threading

import numpy as np

from app.config import get_settings

_settings = get_settings()
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class EmbeddingService:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._mock = _settings.EMBED_MOCK
        self._backend_name = "mock" if self._mock else _settings.EMBED_BACKEND
        self._load_error: str | None = None

    # ---- 就绪状态 ----
    def status(self) -> tuple[str, bool]:
        """返回 (后端名, 是否可用)。"""
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

    # ---- 懒加载真实模型 ----
    def _ensure(self):
        if self._model is not None:
            return self._model
        if self._mock:
            return None
        with self._lock:
            if self._model is None:
                try:
                    from FlagEmbedding import BGEM3FlagModel

                    from app.core import accelerator

                    model_id = "BAAI/bge-m3"
                    local = f"{_settings.MODEL_DIR.rstrip('/')}/bge-m3"
                    device = accelerator.device()
                    fp16 = accelerator.use_fp16()
                    try:
                        self._model = BGEM3FlagModel(
                            local, use_fp16=fp16, devices=device
                        )
                    except Exception:
                        # 本地不存在则回退到 HF 自动拉取
                        self._model = BGEM3FlagModel(
                            model_id, use_fp16=fp16, devices=device
                        )
                except Exception as exc:
                    # 真实后端加载失败（权重缺失/未安装）：仅当显式开启 mock 才降级；
                    # 否则保持未就绪，由调用方返回 503（不静默替换模型）。
                    self._load_error = str(exc)
                    self._model = None
        return self._model

    # ---- 编码 ----
    def embed(self, texts: list[str]) -> tuple[list[np.ndarray], list[dict]]:
        """返回 (dense 列表[np.float32], sparse 列表[dict])。"""
        if self._mock or self._ensure() is None:
            dense = [self._mock_embed(t) for t in texts]
            sparse: list[dict] = [{} for _ in texts]
            return dense, sparse

        out = self._model.encode(
            texts,
            # HybridChunker 已限制 chunk ≤512 token，1024 即可覆盖且不拖慢弱卡
            max_length=1024,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
            # 4GB 卡：batch=4 比 8 更快（规避显存抖动）且留足余量，避免 OOM
            batch_size=4,
        )
        # BGEM3FlagModel 输出键为 dense_vecs / lexical_weights / colbert_vecs
        dense = [np.asarray(v, dtype=np.float32) for v in out["dense_vecs"]]
        sparse = out["lexical_weights"]
        return dense, sparse

    def embed_one(self, text: str) -> tuple[np.ndarray, dict]:
        dense, sparse = self.embed([text])
        return dense[0], sparse[0]

    # ---- mock 实现 ----
    def _mock_embed(self, text: str) -> np.ndarray:
        dim = _settings.EMBED_DIM
        vec = np.zeros(dim, dtype=np.float32)
        for tok in _tokenize(text):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % dim] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec
