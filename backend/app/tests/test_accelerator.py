"""计算加速档位判定自检（无需 GPU / torch：以打桩方式验证设备映射逻辑）。"""
from app.core import accelerator


def _stub(monkeypatch, override, cuda_avail):
    monkeypatch.setattr(accelerator.runtime_config, "get", lambda k: override)
    monkeypatch.setattr(accelerator, "cuda_available", lambda: cuda_avail)


def test_invalid_runtime_value_falls_back_to_auto(monkeypatch):
    _stub(monkeypatch, "gpu", True)
    assert accelerator.requested() == "auto"


def test_auto_prefers_cuda_when_available(monkeypatch):
    _stub(monkeypatch, None, True)
    assert accelerator.device() == "cuda"
    assert accelerator.use_fp16() is True


def test_auto_falls_back_to_cpu_without_cuda(monkeypatch):
    _stub(monkeypatch, None, False)
    assert accelerator.device() == "cpu"
    assert accelerator.use_fp16() is False


def test_cpu_forced_ignores_cuda(monkeypatch):
    _stub(monkeypatch, "cpu", True)
    assert accelerator.device() == "cpu"
    assert accelerator.use_fp16() is False


def test_cuda_preferred_falls_back_to_cpu_when_unavailable(monkeypatch):
    _stub(monkeypatch, "cuda", False)
    assert accelerator.device() == "cpu"
    assert accelerator.use_fp16() is False