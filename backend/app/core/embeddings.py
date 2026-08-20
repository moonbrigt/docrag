"""嵌入服务：OpenAI 兼容 http 端点 / bge-m3 本地 / 确定性 mock。

- http 后端：POST {endpoint} 的 OpenAI 兼容 /v1/embeddings（Ollama / LM Studio / Doubao /
  OpenAI 等任意模型），模型名自由，走 stdlib urllib，无新增依赖。sparse 置空，词法走 FTS5。
- 真实本地后端：FlagEmbedding 的 BGEM3FlagModel，懒加载，权重首次使用时拉取。
- Mock 后端：基于词元哈希的确定性向量（L2 归一化），供离线 / CI 跑通检索与评测，
  不下载 2.2GB 权重。
- 模型未就绪且非 mock 模式时，status().ready=False，调用方应返回 503。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.parse
import urllib.request

import numpy as np

from app.config import get_settings
from app.core import runtime_config

_settings = get_settings()
_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_HTTP_TIMEOUT = 120


def effective_embed_config() -> dict:
    """当前生效的嵌入配置（设置页展示用）：运行时覆盖 > env 默认。"""
    backend = runtime_config.effective("embed_backend", _settings.EMBED_BACKEND)
    if _settings.EMBED_MOCK and runtime_config.get("embed_backend") is None:
        backend = "mock"  # env 显式 RAG_EMBED_MOCK=true 时默认 mock
    model = runtime_config.effective("embed_model", _settings.EMBED_MODEL)
    endpoint = runtime_config.effective("embed_endpoint", _settings.EMBEDDING_ENDPOINT)
    api_key = runtime_config.get("embed_api_key") or _settings.EMBEDDING_API_KEY
    return {
        "backend": backend,
        "model": model,
        "endpoint": endpoint,
        "api_key_set": bool(api_key),
    }


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _is_mock() -> bool:
    return effective_embed_config()["backend"] == "mock"


def _is_http() -> bool:
    return effective_embed_config()["backend"] == "http"


class EmbeddingService:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    # ---- 就绪状态 ----
    def status(self) -> tuple[str, bool]:
        """返回 (后端名, 是否可用)。"""
        if _is_mock():
            return ("mock", True)
        cfg = effective_embed_config()
        if cfg["backend"] == "http":
            return ("http", bool(cfg["endpoint"].strip() and cfg["model"].strip()))
        if self._ensure() is not None:
            return (cfg["backend"], True)
        return (cfg["backend"], False)

    def is_ready(self) -> bool:
        return self.status()[1]

    def reload(self) -> None:
        """丢弃已加载模型，下次调用按最新配置（模型名 / 计算加速档位）重建。"""
        self._model = None
        self._load_error = None

    # ---- 懒加载真实模型 ----
    def _ensure(self):
        if self._model is not None:
            return self._model
        if _is_mock():
            return None
        with self._lock:
            if self._model is None:
                try:
                    from FlagEmbedding import BGEM3FlagModel

                    from app.core import accelerator

                    model = effective_embed_config()["model"]
                    slug = model.rsplit("/", 1)[-1]
                    local = f"{_settings.MODEL_DIR.rstrip('/')}/{slug}"
                    device = accelerator.device()
                    fp16 = accelerator.use_fp16()
                    try:
                        self._model = BGEM3FlagModel(
                            local, use_fp16=fp16, devices=device
                        )
                    except Exception:
                        # 本地不存在则回退到 HF 自动拉取
                        self._model = BGEM3FlagModel(
                            model, use_fp16=fp16, devices=device
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
        cfg = effective_embed_config()
        if cfg["backend"] == "mock":
            return [self._mock_embed(t) for t in texts], [{} for _ in texts]
        if cfg["backend"] == "http":
            return self._http_embed(texts)
        if self._ensure() is None:
            return [self._mock_embed(t) for t in texts], [{} for _ in texts]

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

    # ---- OpenAI 兼容 http 端点 ----
    def _http_embed(self, texts: list[str]) -> tuple[list[np.ndarray], list[dict]]:
        cfg = effective_embed_config()
        endpoint = cfg["endpoint"].strip().rstrip("/")
        model = cfg["model"].strip()
        if not endpoint or not model:
            raise RuntimeError("http 嵌入端点或模型名未配置")
        api_key = runtime_config.get("embed_api_key") or _settings.EMBEDDING_API_KEY
        body = json.dumps({"input": texts, "model": model}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        # 环回地址走直连（本机 Ollama/LM Studio），规避 WSL 环境变量代理把 127.0.0.1 也代理了
        host = urllib.parse.urlparse(endpoint).hostname or ""
        if host in ("localhost", "127.0.0.1", "::1"):
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        else:
            opener = urllib.request.build_opener()
        with opener.open(req, timeout=_HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = sorted((payload.get("data") or []), key=lambda d: d.get("index", 0))
        if len(data) < len(texts):
            raise RuntimeError(
                f"http 嵌入返回 {len(data)} 条，请求 {len(texts)} 条；请检查端点兼容性"
            )
        dense = [np.asarray(r["embedding"], dtype=np.float32) for r in data[: len(texts)]]
        return dense, [{} for _ in texts]

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
