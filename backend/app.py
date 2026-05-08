"""
WebGIS Backend - FastAPI 主应用入口

功能模块：
- 瓦片代理：Google 卫星图瓦片代理 (api/proxy.py)
- 访客统计：地理位置统计功能 (api/statistics.py)
- 通用接口：新闻、数据处理、健康检查等
"""

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env")

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import register_api_routes
from core.cors import build_cors_options
from core.lifecycle import shutdown_backend, startup_backend

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ==================== FastAPI 应用初始化 ====================

app = FastAPI(
    title="GeoMoss Backend",
    description="GeoMoss WebGIS backend API service",
    version="3.1.0",
)

# ==================== CORS 中间件配置 ====================

app.add_middleware(CORSMiddleware, **build_cors_options())

# ==================== 生命周期事件 ====================


@app.on_event("startup")
async def startup_event():
    """
    应用启动事件：初始化全局 HTTP 客户端
    """
    await startup_backend(app)


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭事件：清理资源
    """
    await shutdown_backend(app)


# ==================== 路由挂载 ====================

register_api_routes(app, logger=logger)
