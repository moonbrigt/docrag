"""SQLite 连接与并发控制。

设计约束（Spec §6）：
- 单文件库 app.db，单连接 + 进程内 asyncio.Lock 防并发写入损坏。
- 写操作串行化；读操作并发安全（WAL 模式）。
- chunks.embedding 以 float32(1024) BLOB 存储；chunk_fts 为 FTS5 trigram 虚拟表。
"""
from __future__ import annotations

import asyncio
import pathlib
import sqlite3

from app.config import get_settings

_settings = get_settings()
_write_lock = asyncio.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    filename      TEXT NOT NULL,
    sha256        TEXT,
    page_count    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'queued',
    error         TEXT,
    file_path     TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    -- 成熟度：ACL 与生命周期（旧库由 _migrate 补列）
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    owner_user_id TEXT NOT NULL DEFAULT 'local',
    group_ids     TEXT NOT NULL DEFAULT '[]',
    source_id     TEXT,
    version       INTEGER NOT NULL DEFAULT 1,
    is_active     INTEGER NOT NULL DEFAULT 1,
    archived_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id);

-- 文档生命周期事件（状态流转审计）
CREATE TABLE IF NOT EXISTS document_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id  TEXT NOT NULL,
    source_id    TEXT,
    version      INTEGER,
    from_status  TEXT NOT NULL,
    to_status    TEXT NOT NULL,
    reason       TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    is_transient INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_doc ON document_events(document_id);

CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    content     TEXT NOT NULL,
    page_no     INTEGER NOT NULL,
    bbox        TEXT,
    section     TEXT,
    embedding   BLOB,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc  ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_page ON chunks(document_id, page_no);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    content,
    tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS evaluations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at       TEXT DEFAULT (datetime('now')),
    config_json  TEXT,
    metrics_json TEXT
);

-- 成熟度：问答管道追踪（query 原文一律不落库，query_hash 固定 'not_stored'）
CREATE TABLE IF NOT EXISTS trace (
    trace_id               TEXT PRIMARY KEY,
    created_at             TEXT DEFAULT (datetime('now')),
    tenant_id              TEXT NOT NULL,
    user_id                TEXT NOT NULL,
    query_hash             TEXT NOT NULL DEFAULT 'not_stored',
    status                 TEXT NOT NULL,
    rerank_used            INTEGER NOT NULL DEFAULT 0,
    selected_document_ids  TEXT,
    evidence               TEXT,
    citations              TEXT,
    stage_timings          TEXT,
    model_provenance       TEXT,
    error_message          TEXT
);
CREATE INDEX IF NOT EXISTS idx_trace_owner ON trace(tenant_id, user_id);

-- 成熟度：用户反馈（纠错与运营）
CREATE TABLE IF NOT EXISTS feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id      TEXT NOT NULL,
    rating        TEXT NOT NULL,
    issue_type    TEXT,
    selected_text TEXT,
    comment       TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (trace_id) REFERENCES trace(trace_id)
);

-- 运行时配置覆盖（设置页写回；覆盖 env 默认值，key 为 RAG_* 风格键名）
CREATE TABLE IF NOT EXISTS runtime_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""

# 旧库升级：为已存在的 documents 表补 ACL/生命周期列（幂等，重复列忽略）
_ALTER_DOCUMENTS = [
    ("tenant_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("owner_user_id", "TEXT NOT NULL DEFAULT 'local'"),
    ("group_ids", "TEXT NOT NULL DEFAULT '[]'"),
    ("source_id", "TEXT"),
    ("version", "INTEGER NOT NULL DEFAULT 1"),
    ("is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("archived_at", "TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    """为旧版数据库补列（CREATE TABLE IF NOT EXISTS 不会改已有表）。"""
    has_docs = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'"
    ).fetchone()
    if not has_docs:
        return  # 全新库：无 documents 表，SCHEMA 会创建全部表
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
    for column, ddl in _ALTER_DOCUMENTS:
        if column in existing:
            continue
        conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {ddl}")
    # 老数据回填：source_id 缺省 = 自身 id（首个版本即 source）
    conn.execute(
        "UPDATE documents SET source_id=id WHERE source_id IS NULL OR source_id=''"
    )


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        pathlib.Path(_settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(_settings.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        # 先迁移旧库补列，再执行全量 SCHEMA（否则引用新列的表/索引创建会失败）
        _migrate(_conn)
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def init_db() -> None:
    """应用启动时初始化连接与表结构。"""
    _connect()


def query(sql: str, params: tuple = ()) -> list[dict]:
    """并发安全的读操作。"""
    conn = _connect()
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


async def write(fn) -> object:
    """写操作串行化（防 SQLite 并发损坏）。fn(conn) 内自行 commit。"""
    async with _write_lock:
        conn = _connect()
        try:
            result = fn(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
