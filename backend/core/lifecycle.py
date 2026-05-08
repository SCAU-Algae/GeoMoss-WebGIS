"""Application startup and shutdown resource management."""

import logging

from fastapi import FastAPI

from api.auth import init_auth_storage
from api.proxy import build_http_client

logger = logging.getLogger(__name__)


async def startup_backend(app: FastAPI) -> None:
    """Initialize storage and shared clients."""
    logger.info("WebGIS Backend 启动...")
    await init_auth_storage()
    app.state.http_client = build_http_client()
    logger.info("HTTP 客户端初始化完成")


async def shutdown_backend(app: FastAPI) -> None:
    """Close shared clients."""
    logger.info("WebGIS Backend 关闭...")
    client = getattr(app.state, "http_client", None)
    if client is not None:
        await client.aclose()
        logger.info("HTTP 客户端已关闭")
