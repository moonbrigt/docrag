"""运行时配置（设置页）测试：GET/PUT /config/settings、覆盖优先级、api_key 掩码、持久化。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset_runtime_config():
    """每个用例清空运行时覆盖，避免用例间污染。"""
    from app.core import runtime_config

    runtime_config._overrides.clear()
    yield
    runtime_config._overrides.clear()


def _put(client: TestClient, payload: dict):
    return client.put("/api/v1/config/settings", json=payload)


def test_get_settings_defaults(client):
    r = client.get("/api/v1/config/settings")
    assert r.status_code == 200
    body = r.json()
    llm = body["llm"]
    assert llm["backend"] == "mock"  # 测试 env RAG_LLM_MOCK=true
    assert "api_key_set" in llm and llm["api_key_set"] is False
    assert "model" in llm and llm["model"]
    assert body["apply_mode"] == "runtime_override"


def test_put_switches_backend_live(client):
    r = _put(client, {"llm": {"backend": "openai", "base_url": "https://api.test.local/v1", "model": "gpt-x"}})
    assert r.status_code == 200
    llm = r.json()["llm"]
    assert llm["backend"] == "openai"
    assert llm["base_url"] == "https://api.test.local/v1"
    assert llm["model"] == "gpt-x"

    # /config/backends 与 /health 立即反映新后端（无需重启）
    b = client.get("/api/v1/config/backends").json()
    assert b["llm"]["backend"] == "openai"
    h = client.get("/api/v1/health").json()
    assert h["models"]["llm"]["backend"] == "openai"


def test_api_key_masked_and_cleared(client):
    r = _put(client, {"llm": {"api_key": "sk-secret-123"}})
    body = r.json()["llm"]
    assert body["api_key_set"] is True
    assert "sk-secret-123" not in r.text  # 响应中绝不出现明文
    g = client.get("/api/v1/config/settings").json()["llm"]
    assert g["api_key_set"] is True
    assert "sk-secret-123" not in str(g)

    # 传空串清除
    r2 = _put(client, {"llm": {"api_key": ""}})
    assert r2.json()["llm"]["api_key_set"] is False


def test_override_persists_across_restart(client):
    _put(client, {"llm": {"backend": "ollama", "base_url": "http://ollama.local:11434/v1"}})

    # 模拟重启：重新加载内存覆盖（持久化在 SQLite，load 后应恢复）
    from app.core import runtime_config

    runtime_config._overrides.clear()
    runtime_config.load_runtime_config()
    cfg = client.get("/api/v1/config/settings").json()["llm"]
    assert cfg["backend"] == "ollama"
    assert cfg["base_url"] == "http://ollama.local:11434/v1"


def test_put_validation(client):
    r = _put(client, {"llm": {"backend": "not-a-backend"}})
    assert r.status_code == 422
    r2 = _put(client, {"llm": {}})
    assert r2.status_code == 400
    r3 = _put(client, {})
    assert r3.status_code in (400, 422)


def test_env_default_restored_after_clear(client):
    _put(client, {"llm": {"backend": "openai"}})
    r = _put(client, {"llm": {"backend": ""}})
    assert r.status_code == 200
    # 清除后回落 env 默认（测试环境 RAG_LLM_MOCK=true -> mock）
    assert r.json()["llm"]["backend"] == "mock"
