"""运行时配置覆盖（设置页写回）。

优先级：DB 中的 runtime_config 覆盖 > 环境变量（RAG_*）默认值。
- 启动时从 SQLite 加载到内存（load_runtime_config，见 main.py lifespan）。
- 设置页 PUT /config/settings 时通过 set_overrides 更新并持久化。
- 各核心服务（LLM/embedding/rerank/parser）读取时调用 get() 取生效值。
- 存储说明：api_key 等敏感值明文存于本地 SQLite（自托管单机部署），
  API 响应一律不回传明文，只返回 api_key_set 布尔。
"""
from __future__ import annotations

from app import db

# 内存态：键 -> 生效覆盖值；None 表示未覆盖（回落 env 默认）
_overrides: dict[str, str | None] = {}


def load_runtime_config() -> None:
    """从持久化存储加载覆盖（应用启动时调用一次）。"""
    _overrides.clear()
    try:
        rows = db.query("SELECT key, value FROM runtime_config")
    except Exception:
        return  # 表尚不存在（旧库迁移前）时静默跳过
    for r in rows:
        _overrides[r["key"]] = r["value"]


def get(key: str) -> str | None:
    """返回覆盖值；无覆盖返回 None（调用方回落 env 默认）。"""
    return _overrides.get(key)


def effective(key: str, default: str) -> str:
    """运行时覆盖优先，其次 env 默认（各核心服务读取生效值的统一入口）。"""
    return get(key) or default


async def set_overrides(pairs: dict[str, str]) -> None:
    """写入覆盖并持久化。值传空字符串表示清除该键的覆盖。"""

    def _persist(conn):
        # db.write 同步执行回调（conn 为 sqlite3.Connection）
        for key, value in pairs.items():
            if value == "":
                conn.execute("DELETE FROM runtime_config WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO runtime_config (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                    "updated_at = datetime('now')",
                    (key, value),
                )

    # 先落盘再更新内存；失败则内存不变，保持与持久态一致
    await db.write(_persist)
    for key, value in pairs.items():
        _overrides[key] = value if value != "" else None
