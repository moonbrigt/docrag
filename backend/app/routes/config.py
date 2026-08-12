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

from app.core import runtime_config
from app.core.llm import effective_llm_config

router = APIRouter(prefix="/api/v1", tags=["config"])

_LLM_BACKENDS = Literal["mock", "ollama", "openai"]


class LlmSettingsIn(BaseModel):
    # 空字符串 = 清除该键的运行时覆盖，回落环境变量默认值
    backend: Optional[Literal["mock", "ollama", "openai", ""]] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class SettingsIn(BaseModel):
    llm: LlmSettingsIn = Field(default_factory=LlmSettingsIn)


@router.get("/config/settings")
async def get_settings():
    cfg = effective_llm_config()
    return {"llm": cfg, "apply_mode": "runtime_override"}


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
    if not pairs:
        raise HTTPException(status_code=400, detail="没有可更新的配置项")

    try:
        await runtime_config.set_overrides(pairs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"配置持久化失败：{exc}")

    return {"ok": True, "llm": effective_llm_config()}
