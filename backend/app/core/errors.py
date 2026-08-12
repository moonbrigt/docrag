"""服务层领域异常。

与框架解耦：服务层只抛领域异常，由 routes 层映射为对应 HTTP 状态码
（503 模型未就绪 / 422 解析失败 / 400 参数错误等）。
"""
from __future__ import annotations


class ModelNotReadyError(Exception):
    """重模型（嵌入/重排/LLM）未就绪，无法执行该操作。映射为 503。"""


class PipelineError(Exception):
    """文档解析 / 索引流水线失败。映射为 422（解析）或 500。"""
