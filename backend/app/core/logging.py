"""结构化日志配置（可观测性基础）。

提供统一 JSON 行日志格式化器，便于在容器 / 编排平台采集（stdout -> 日志系统）。
用法：
    from app.core.logging import get_logger, configure_logging
    configure_logging()              # 应用启动时调用一次
    log = get_logger(__name__)
    log.info("pipeline.done", extra={"doc_id": doc_id, "chunks": 12})
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """把日志记录渲染为一行 JSON，字段固定便于采集与检索。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """配置根日志为 JSON 行输出，并将第三方库降噪。幂等。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level, logging.INFO))
    # 降低访问日志噪声，错误仍可见
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
