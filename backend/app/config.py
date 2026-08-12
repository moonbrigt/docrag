"""全局配置（pydantic-settings）。

所有可调项通过 RAG_ 前缀的环境变量注入；未设置时使用下方默认值。
重模型（bge-m3 / reranker / docling）默认走真实后端，但提供 *_MOCK 开关，
以便离线 / CI 下用确定性 mock 跑通全链路（不下载大模型权重）。
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 存储
    DATA_DIR: str = "./data"
    DB_PATH: str = "./app.db"
    MODEL_DIR: str = "./models"

    # 嵌入
    EMBED_BACKEND: str = "bge-m3"  # bge-m3 | mock
    EMBED_MOCK: bool = False
    EMBED_DIM: int = 1024

    # 重排
    RERANK_BACKEND: str = "bge-reranker-v2-m3"  # bge-reranker-v2-m3 | mock
    RERANK_MOCK: bool = False

    # 解析
    PARSE_BACKEND: str = "docling"  # docling | mock
    PARSE_MOCK: bool = False

    # LLM 双后端
    LLM_BACKEND: str = "ollama"  # ollama | openai | mock
    LLM_MOCK: bool = False
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OPENAI_BASE_URL: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "llama3.1:8b"

    # 检索参数
    RRF_K: int = 60
    RETRIEVE_TOP_K: int = 20  # RRF 融合前的每路候选数
    RERANK_TOP_K: int = 5  # 重排后保留数
    FAISS_TOP_K: int = 20
    FTS_TOP_K: int = 20

    # 身份与访问控制（ACL）
    # 仅当 RAG_TRUSTED_PROXY=true 时，才从反向代理注入的 X-Rag-Tenant /
    # X-Rag-User / X-Rag-Group 请求头解析身份；否则一律使用本地默认
    # principal（"default" 租户）。CORS allow_headers 不包含 X-Rag-*，
    # 保证浏览器端无法伪造这些头（只有可信反向代理能设置）。
    TRUSTED_PROXY: bool = False

    # 服务
    PORT: int = 8000


@lru_cache
def get_settings() -> Settings:
    """进程内单例配置。"""
    return Settings()
