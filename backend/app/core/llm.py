"""LLM 客户端：基于 openai SDK 的双后端抽象（Ollama / OpenAI 兼容）+ mock 流式。

- ollama：base_url 默认 RAG_OLLAMA_BASE_URL，api_key 任意非空（Ollama 不校验）。
- openai：base_url 默认 RAG_OPENAI_BASE_URL + RAG_OPENAI_API_KEY，需联网。
- mock：本地确定性流式输出，引用传入的上下文编号，供离线 / CI。
- 通过 base_url 切换，零分支逻辑（同一 AsyncOpenAI 接口）。
- 生效配置 = 环境变量（RAG_*）默认值，可被运行时配置（设置页）覆盖，
  每次调用实时读取，切换无需重启（见 app.core.runtime_config）。
- 未就绪且非 mock 时 status().ready=False，调用方应返回 503。
"""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.core import runtime_config

_settings = get_settings()


def _effective(key: str, default: str) -> str:
    """运行时覆盖优先，其次 env 默认。"""
    return runtime_config.get(key) or default


def effective_llm_config() -> dict:
    """当前生效的 LLM 配置（设置页展示用；api_key 只回传是否已设置）。"""
    backend = _effective("llm_backend", _settings.LLM_BACKEND)
    if _settings.LLM_MOCK and runtime_config.get("llm_backend") is None:
        backend = "mock"  # env 显式 RAG_LLM_MOCK=true 时默认 mock
    base_url = _effective("llm_base_url", "")
    model = _effective("llm_model", _settings.LLM_MODEL)
    if backend == "ollama":
        base_url = base_url or _settings.OLLAMA_BASE_URL
    elif backend == "openai":
        base_url = base_url or _settings.OPENAI_BASE_URL
    api_key = _effective("llm_api_key", _settings.OPENAI_API_KEY)
    return {
        "backend": backend,
        "base_url": base_url,
        "model": model,
        "api_key_set": bool(api_key),
    }


class LLMClient:
    def __init__(self) -> None:
        self._client = None
        self._client_sig = None

    def status(self) -> tuple[str, bool]:
        cfg = effective_llm_config()
        if cfg["backend"] == "mock":
            return ("mock", True)
        # 真实后端在调用时才能发现连通性；此处报告配置意图可用。
        return (cfg["backend"], bool(cfg["model"]))

    def is_ready(self) -> bool:
        return self.status()[1]

    def _get_client(self, cfg: dict):
        # 配置变化时重建客户端（base_url/backend/api_key 任一变化）
        sig = (cfg["backend"], cfg["base_url"], cfg["api_key_set"])
        if self._client is not None and self._client_sig == sig:
            return self._client
        from openai import AsyncOpenAI

        if cfg["backend"] == "ollama":
            self._client = AsyncOpenAI(
                base_url=cfg["base_url"] or _settings.OLLAMA_BASE_URL,
                api_key="ollama",
            )
        else:  # openai
            api_key = _effective("llm_api_key", _settings.OPENAI_API_KEY)
            self._client = AsyncOpenAI(
                base_url=cfg["base_url"] or None,
                api_key=api_key or "EMPTY",
            )
        self._client_sig = sig
        return self._client

    async def stream(
        self,
        system_prompt: str,
        user_prompt: str,
        mock_context: list[dict] | None = None,
    ):
        """异步生成器，逐块产出文本增量（delta）。

        mock_context：仅 mock 模式使用，元素形如 {index, page, snippet}。
        """
        cfg = effective_llm_config()
        if cfg["backend"] == "mock":
            async for piece in self._mock_stream(user_prompt, mock_context):
                yield piece
            return

        client = self._get_client(cfg)
        try:
            stream = await client.chat.completions.create(
                model=cfg["model"] or _settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                temperature=0.0,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:  # 连通性 / 鉴权失败，向上抛出由路由转 503
            raise RuntimeError(f"LLM 调用失败：{exc}") from exc

    async def _mock_stream(self, user_prompt: str, mock_context) -> None:
        if not mock_context:
            text = (
                "（离线 Mock 模式）未接入真实模型，无法生成基于知识的回答。"
                "请到设置页配置模型 API（Ollama 或 OpenAI 兼容端点）。\n"
            )
        else:
            lines = ["根据提供的文档片段，回答如下：\n"]
            for c in mock_context:
                idx = c.get("index")
                page = c.get("page")
                snippet = (c.get("snippet") or "")[:80]
                lines.append(f"[{idx}] 文档第 {page} 页提到：{snippet}…\n")
            text = "".join(lines)
        # 逐字流式，模拟 token 增量
        for i in range(0, len(text), 4):
            await asyncio.sleep(0)
            yield text[i : i + 4]
