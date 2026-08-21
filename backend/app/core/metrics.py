"""进程内指标注册表（可观测性）。

提供线程安全的计数器与直方图内存实现，供 GET /api/v1/metrics 暴露。
MVP 阶段以 JSON 暴露即可；生产可将 snapshot() 接入 Prometheus
Pushgateway / Node Exporter textfile collector，无需改动埋点代码。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_MAX_OBSERVATIONS = 200  # 每个直方图保留最近 N 个样本，控制内存


class _Histogram:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: deque[float] = deque(maxlen=_MAX_OBSERVATIONS)

    def observe(self, value: float) -> None:
        with self._lock:
            self._samples.append(value)

    def snapshot(self) -> dict:
        with self._lock:
            if not self._samples:
                return {"count": 0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
            s = sorted(self._samples)
            n = len(s)
            return {
                "count": n,
                "avg_ms": round(sum(s) / n, 2),
                "p50_ms": round(s[n // 2], 2),
                "p95_ms": round(s[min(n - 1, int(n * 0.95))], 2),
                "min_ms": round(s[0], 2),
                "max_ms": round(s[-1], 2),
            }


class Metrics:
    """集中式指标注册表。单例使用 get_metrics()。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, _Histogram] = defaultdict(_Histogram)

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] += by

    def observe(self, name: str, value: float) -> None:
        self._histograms[name].observe(value)

    def snapshot(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
        histograms = {k: v.snapshot() for k, v in self._histograms.items()}
        return {
            "counters": counters,
            "histograms": histograms,
            "generated_at": int(time.time()),
        }


_metrics = Metrics()


def get_metrics() -> Metrics:
    """返回进程内指标单例。"""
    return _metrics
