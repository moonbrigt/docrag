"""稠密向量索引：FAISS IndexFlatIP（L2 归一化后 IP=cosine）。

- 优先使用 faiss-cpu；不可用时回退到 numpy 精确内积（功能等价，仅性能差异）。
- 索引常驻内存，chunk_id 与矩阵行一一对应。
- 启动时从 SQLite 的 embedding BLOB 重建；新增分块时增量 add。
"""
from __future__ import annotations

import threading

import numpy as np

try:
    import faiss  # type: ignore

    _HAVE_FAISS = True
except Exception:  # pragma: no cover - 取决于环境是否安装 faiss
    faiss = None
    _HAVE_FAISS = False


class FaissStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ids: list[int] = []
        self.index = None  # faiss.IndexFlatIP | None
        self._matrix: np.ndarray | None = None  # numpy 兜底
        self.mode = "faiss" if _HAVE_FAISS else "numpy"
        self.dim: int = 0

    @property
    def size(self) -> int:
        return len(self.ids)

    def reset(self) -> None:
        with self._lock:
            self.ids = []
            self.index = None
            self._matrix = None
            self.dim = 0

    def build_from(self, rows: list[tuple[int, bytes]]) -> None:
        """rows: (chunk_id, embedding_blob)。从持久化 BLOB 重建索引。"""
        with self._lock:
            self.ids = []
            vecs: list[np.ndarray] = []
            for cid, blob in rows:
                if not blob:
                    continue
                v = np.frombuffer(blob, dtype=np.float32)
                if v.size == 0:
                    continue
                vecs.append(self._normalize(v))
                self.ids.append(cid)
            if not vecs:
                self.index = None
                self._matrix = None
                self.dim = 0
                return
            mat = np.stack(vecs).astype(np.float32)
            self.dim = mat.shape[1]
            if _HAVE_FAISS:
                idx = faiss.IndexFlatIP(self.dim)
                idx.add(mat)
                self.index = idx
                self._matrix = None
            else:
                self._matrix = mat
                self.index = None

    def add(self, chunk_id: int, vec: np.ndarray) -> None:
        v = self._normalize(vec.astype(np.float32))
        with self._lock:
            self.ids.append(chunk_id)
            if _HAVE_FAISS and self.index is not None:
                self.index.add(v.reshape(1, -1))
            elif _HAVE_FAISS and self.index is None:
                self.dim = v.shape[0]
                self.index = faiss.IndexFlatIP(self.dim)
                self.index.add(v.reshape(1, -1))
            else:
                if self._matrix is None:
                    self._matrix = v.reshape(1, -1)
                    self.dim = v.shape[0]
                else:
                    self._matrix = np.vstack([self._matrix, v.reshape(1, -1)])

    def search(self, vec: np.ndarray, k: int) -> list[tuple[int, float]]:
        """返回 [(chunk_id, score)]，按 score 降序。"""
        v = self._normalize(vec.astype(np.float32))
        with self._lock:
            if not self.ids:
                return []
            if _HAVE_FAISS and self.index is not None:
                kk = min(k, len(self.ids))
                scores, idxs = self.index.search(v.reshape(1, -1), kk)
                out = [
                    (self.ids[int(i)], float(s))
                    for s, i in zip(scores[0], idxs[0])
                    if i != -1
                ]
                return out
            mat = self._matrix
            sims = mat @ v
            order = np.argsort(-sims)
            kk = min(k, len(self.ids))
            return [(self.ids[int(j)], float(sims[j])) for j in order[:kk]]

    @staticmethod
    def _normalize(v: np.ndarray) -> np.ndarray:
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v
