"""OpenAI 兼容 http 嵌入后端的自检：本地假 /v1/embeddings 服务端 → 走通 _http_embed。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.core import runtime_config
from app.core.embeddings import EmbeddingService, effective_embed_config

DIM = 7


class _FakeEmbed(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - HTTP method 名按接口要求
        n = len(json.loads(self.rfile.read(int(self.headers["Content-Length"])))["input"])
        body = json.dumps(
            {
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        "embedding": [float(i + 1) / n] * DIM,
                    }
                    for i in range(n)
                ]
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默，避免测试刷屏
        pass


@pytest.fixture
def http_embed_endpoint():
    srv = HTTPServer(("127.0.0.1", 0), _FakeEmbed)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}/v1/embeddings"
    yield url
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def http_overrides(http_embed_endpoint):
    runtime_config._overrides.clear()
    runtime_config._overrides.update(
        {
            "embed_backend": "http",
            "embed_endpoint": http_embed_endpoint,
            "embed_model": "fake-embed",
        }
    )
    yield
    runtime_config._overrides.clear()


def test_http_embedding_backend(http_overrides):
    cfg = effective_embed_config()
    assert cfg["backend"] == "http"
    assert cfg["api_key_set"] is False

    svc = EmbeddingService()
    dense, sparse = svc.embed(["alpha", "beta"])
    assert len(dense) == 2
    assert dense[0].shape == (DIM,)
    assert sparse == [{}, {}]
    assert svc.status() == ("http", True)


def test_http_embedding_not_ready_without_endpoint():
    runtime_config._overrides.clear()
    runtime_config._overrides.update(
        {"embed_backend": "http", "embed_model": "fake-embed"}  # 缺 endpoint
    )
    try:
        svc = EmbeddingService()
        assert svc.status() == ("http", False)
    finally:
        runtime_config._overrides.clear()