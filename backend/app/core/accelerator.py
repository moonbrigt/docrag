"""计算加速（GPU）选择：供嵌入 / 重排模型决定设备与精度。

优先级：runtime_config['accelerator'] > env RAG_ACCELERATOR > "auto"。
- auto：有 GPU 用 cuda + fp16，否则 cpu + fp32。
- cuda：偏好 GPU；环境无 CUDA 时回落 cpu（fp32）。
- cpu：强制 CPU（fp32）。

FP16 仅在 CUDA 上启用（CPU 的 fp16 数值不稳定且多数算子不支持）。
LLM（Ollama / OpenAI 兼容）运行在独立进程中，GPU 由它自身管理，不归本模块。
"""
from __future__ import annotations

from app.config import get_settings
from app.core import runtime_config

_settings = get_settings()
_VALID = frozenset({"auto", "cuda", "cpu"})


def requested() -> str:
    """用户/环境选定的加速档位（auto/cuda/cpu），非法值归一为 auto。"""
    value = runtime_config.get("accelerator") or _settings.ACCELERATOR or "auto"
    return value if value in _VALID else "auto"


def cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def device() -> str:
    """生效设备名（'cuda' 或 'cpu'）。"""
    if requested() == "cpu":
        return "cpu"
    return "cuda" if cuda_available() else "cpu"


def use_fp16() -> bool:
    return device() == "cuda"