"""pytest 公共夹具：离线 mock 模式 + 临时 SQLite，确保全链路可在无大模型环境验证。

注意：环境变量必须在 import app 之前设置，否则会被 lru_cache 的 get_settings 固化。
"""
import asyncio
import atexit
import os
import tempfile

# 在导入 app 之前强制离线 mock，避免下载 bge-m3 / reranker / docling 权重
os.environ.update(
    {
        "RAG_EMBED_MOCK": "true",
        "RAG_RERANK_MOCK": "true",
        "RAG_PARSE_MOCK": "true",
        "RAG_LLM_MOCK": "true",
    }
)
_TMP_DIR = tempfile.TemporaryDirectory(prefix="docrag_test_")
_TMP = _TMP_DIR.name
os.environ["RAG_DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["RAG_DATA_DIR"] = _TMP


def _cleanup_test_resources():
    """先关闭 SQLite，再删除临时目录，避免 Windows 锁住 test.db。"""
    try:
        from app import db

        if db._conn is not None:
            db._conn.close()
            db._conn = None
    except Exception:
        pass
    _TMP_DIR.cleanup()


atexit.register(_cleanup_test_resources)

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import db
    from app.main import app
    from app.services import index_service

    db.init_db()

    # 测试隔离：清空知识库并重建空内存索引，保证每个用例从干净的 KB 开始。
    # get_settings 被 lru_cache 固化，所有用例共用同一临时 SQLite，必须主动清理，
    # 否则前一个用例上传并索引的文档会残留在库里，污染 test_search_empty_kb 等用例。
    async def _reset_kb():
        await db.write(lambda c: c.execute("DELETE FROM feedback"))
        await db.write(lambda c: c.execute("DELETE FROM trace"))
        await db.write(lambda c: c.execute("DELETE FROM document_events"))
        await db.write(lambda c: c.execute("DELETE FROM chunk_fts"))
        await db.write(lambda c: c.execute("DELETE FROM chunks"))
        await db.write(lambda c: c.execute("DELETE FROM documents"))
        await index_service.rebuild_faiss()

    asyncio.run(_reset_kb())

    with TestClient(app) as c:
        yield c


def wait_indexed(client, doc_id, timeout=5.0, headers=None):
    """轮询文档状态直到 indexed / failed。headers 供 trusted-proxy 测试传身份。"""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        if resp.status_code == 200:
            last = resp.json()["document"]
            if last["status"] in ("indexed", "failed"):
                break
        time.sleep(0.05)
    return last
