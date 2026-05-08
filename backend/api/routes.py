"""
Central API router registry.

Keep route ownership in each api/*.py module, while app.py stays responsible
only for application assembly.
"""

from dataclasses import dataclass
import logging
from typing import Optional

from fastapi import APIRouter, FastAPI

from api.admin import router as admin_router
from api.admin_geodata import router as admin_geodata_router
from api.agent_chat import router as agent_chat_router
from api.api_keys_management import router as api_keys_router
from api.api_management import router as api_management_router
from api.auth import router as auth_router
from api.email_auth import router as email_auth_router
from api.external_proxy import router as external_proxy_router
from api.fengshui import router as fengshui_router
from api.location import router as location_router
from api.proxy import router as proxy_router
from api.statistics import router as statistics_router
from api.system import router as system_router
from api.terrain import router as terrain_router
from api.threed import router as threed_router


@dataclass(frozen=True)
class RouterRegistration:
    label: str
    router: APIRouter


API_ROUTERS = (
    RouterRegistration("瓦片代理", proxy_router),
    RouterRegistration("外部服务代理", external_proxy_router),
    RouterRegistration("认证", auth_router),
    RouterRegistration("访客统计", statistics_router),
    RouterRegistration("位置服务", location_router),
    RouterRegistration("管理员", admin_router),
    RouterRegistration("管理员地理数据", admin_geodata_router),
    RouterRegistration("API 管理", api_management_router),
    RouterRegistration("API 密钥管理", api_keys_router),
    RouterRegistration("Agent 对话", agent_chat_router),
    RouterRegistration("3D 处理", threed_router),
    RouterRegistration("地形图层", terrain_router),
    RouterRegistration("风水分析", fengshui_router),
    RouterRegistration("邮箱验证", email_auth_router),
    RouterRegistration("系统端点", system_router),
)


def register_api_routes(app: FastAPI, logger: Optional[logging.Logger] = None) -> None:
    """Register all API routers in the documented order."""
    for item in API_ROUTERS:
        app.include_router(item.router)
        logger and logger.info("已注册%s路由", item.label)
