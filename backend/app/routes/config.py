"""运行时配置路由（设置页）：GET/PUT /config/settings。

- GET：返回当前生效的 LLM 配置（api_key 只回传是否已设置，绝不回传明文）。
- PUT：写入运行时覆盖（持久化到 runtime_config 表并即时生效，无需重启）。
  覆盖优先级：运行时配置 > 环境变量（RAG_*）默认值。
- 注意：本接口为自托管单机部署设计；多租户产品化时应收敛到管理员角色
  （见 docs/MATURITY_MATRIX.md「需要产品决策」）。
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import runtime_config, accelerator
from app.core.llm import effective_llm_config
from app.core.embeddings import effective_embed_config
from app.core.reranker import effective_rerank_config
from app.core.parser import effective_parse_backend
from app.services import index_service, rerank_service

router = APIRouter(prefix="/api/v1", tags=["config"])


class LlmSettingsIn(BaseModel):
    # 空字符串 = 清除该键的运行时覆盖，回落环境变量默认值
    backend: Optional[Literal["mock", "ollama", "openai", ""]] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    # 计算加速档位（嵌入/重排 GPU 开关）；空串 = 回落 env 默认
    accelerator: Optional[Literal["auto", "cuda", "cpu", ""]] = None


class EmbedSettingsIn(BaseModel):
    backend: Optional[Literal["bge-m3", "mock", ""]] = None
    model: Optional[str] = None


class RerankSettingsIn(BaseModel):
    backend: Optional[Literal["bge-reranker-v2-m3", "mock", ""]] = None
    model: Optional[str] = None


class ParseSettingsIn(BaseModel):
    backend: Optional[Literal["docling", "mock", ""]] = None


class SettingsIn(BaseModel):
    llm: LlmSettingsIn = Field(default_factory=LlmSettingsIn)
    embed: EmbedSettingsIn = Field(default_factory=EmbedSettingsIn)
    rerank: RerankSettingsIn = Field(default_factory=RerankSettingsIn)
    parse: ParseSettingsIn = Field(default_factory=ParseSettingsIn)


@router.get("/config/settings")
async def get_settings():
    return {
        "llm": effective_llm_config(),
        "embed": effective_embed_config(),
        "rerank": effective_rerank_config(),
        "parse": {"backend": effective_parse_backend()},
        "apply_mode": "runtime_override",
        "accelerator": accelerator.requested(),
        "device": accelerator.device(),
        "cuda_available": accelerator.cuda_available(),
    }


@router.put("/config/settings")
async def put_settings(req: SettingsIn):
    llm = req.llm
    pairs: dict[str, str] = {}
    if llm.backend is not None:
        pairs["llm_backend"] = llm.backend
    if llm.base_url is not None:
        pairs["llm_base_url"] = llm.base_url.strip()
    if llm.api_key is not None:
        pairs["llm_api_key"] = llm.api_key.strip()
    if llm.model is not None:
        pairs["llm_model"] = llm.model.strip()
    if llm.accelerator is not None:
        pairs["accelerator"] = llm.accelerator
    if req.embed.backend is not None:
        pairs["embed_backend"] = req.embed.backend
    if req.embed.model is not None:
        pairs["embed_model"] = req.embed.model.strip()
    if req.rerank.backend is not None:
        pairs["rerank_backend"] = req.rerank.backend
    if req.rerank.model is not None:
        pairs["rerank_model"] = req.rerank.model.strip()
    if req.parse.backend is not None:
        pairs["parse_backend"] = req.parse.backend
    if not pairs:
        raise HTTPException(status_code=400, detail="没有可更新的配置项")

    try:
        await runtime_config.set_overrides(pairs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"配置持久化失败：{exc}")

    # 计算加速或模型名变更：丢弃已加载的嵌入/重排模型，下次调用按新配置重建
    if any(k in pairs for k in ("accelerator", "embed_backend", "embed_model")):
        index_service.get_embedder().reload()
    if any(k in pairs for k in ("accelerator", "rerank_backend", "rerank_model")):
        rerank_service.get_reranker().reload()

    if "embed_backend" in pairs or "embed_model" in pairs:
        # 嵌入模型/后端变更后，已持久化的向量仍停留在旧模型空间。
        # 只重建内存 FAISS（与 DB 向量自洽），既有文档需重索引才能正确检索。
        await index_service.rebuild_faiss()

    return {"ok": True, **await get_settings()}
