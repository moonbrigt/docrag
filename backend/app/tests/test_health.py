"""健康检查与双后端状态冒烟测试。"""
from __future__ import annotations


def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert "embed" in body["models"]
    assert "rerank" in body["models"]
    assert "llm" in body["models"]


def test_config_backends(client):
    r = client.get("/api/v1/config/backends")
    assert r.status_code == 200
    body = r.json()
    # mock 模式下后端名应为 mock 且 ready=true
    assert body["embedding"]["backend"] == "mock"
    assert body["embedding"]["ready"] is True
    assert body["rerank"]["backend"] == "mock"
    assert body["llm"]["backend"] == "mock"
