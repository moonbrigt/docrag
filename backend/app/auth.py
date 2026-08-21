"""身份与访问控制（ACL）：Principal 抽象 + FastAPI 依赖。

设计约束（成熟度维度-权限/ACL）：
- 仅当 RAG_TRUSTED_PROXY=true 时才从反向代理头解析身份；否则一律使用本地
  默认 principal（"default" 租户 / "local" 用户 / 无组）。
- 浏览器无法伪造 X-Rag-* 头：CORS allow_headers 不包含它们（见 main.py）。
- 可见性规则（fail-closed，无权限 = 404 / 空结果，不泄露存在性）：
    tenant 必须匹配 +（属主 或 组成员重叠 或 管理员）。
- 管理规则（删除 / ACL 修改 / cancel / retry / 版本替换）：
    tenant 匹配 +（属主 或 管理员）。
- 管理员 = user_id 为 "admin"，或用户组包含 "admins"。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request

from app.config import get_settings


@dataclass(frozen=True)
class Principal:
    """请求身份：租户 + 用户 + 用户组。"""

    tenant_id: str
    user_id: str = "local"
    groups: tuple[str, ...] = field(default_factory=tuple)

    def is_admin(self) -> bool:
        return self.user_id == "admin" or "admins" in self.groups


def default_principal() -> Principal:
    """本地（非 trusted-proxy）模式下的默认身份。"""
    return Principal(tenant_id="default", user_id="local")


def get_principal(request: Request) -> Principal:
    """FastAPI 依赖：解析当前请求的身份。

    RAG_TRUSTED_PROXY=true 时信任反向代理注入的头（反向代理需配置
    proxy_set_header X-Rag-Tenant / X-Rag-User / X-Rag-Group，且禁止
    浏览器直连后端）；否则忽略一切身份头，返回本地默认身份。
    """
    settings = get_settings()
    if not settings.TRUSTED_PROXY:
        return default_principal()
    tenant = (request.headers.get("x-rag-tenant") or "").strip() or "default"
    user = (request.headers.get("x-rag-user") or "").strip() or "local"
    groups = tuple(
        g.strip()
        for g in (request.headers.get("x-rag-group") or "").split(",")
        if g.strip()
    )
    return Principal(tenant_id=tenant, user_id=user, groups=groups)


def doc_visible(principal: Principal, doc: dict) -> bool:
    """文档对当前身份是否可见（不检查 is_active，由调用方按场景决定）。"""
    if doc.get("tenant_id") != principal.tenant_id:
        return False
    if principal.is_admin():
        return True
    if doc.get("owner_user_id") == principal.user_id:
        return True
    groups = doc.get("group_ids") or []
    return any(g in principal.groups for g in groups)


def doc_manageable(principal: Principal, doc: dict) -> bool:
    """文档是否可被当前身份管理（删除 / ACL 修改 / cancel / retry / 版本）。"""
    if doc.get("tenant_id") != principal.tenant_id:
        return False
    return principal.is_admin() or doc.get("owner_user_id") == principal.user_id
