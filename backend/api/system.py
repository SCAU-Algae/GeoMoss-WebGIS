"""System and diagnostics endpoints."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/")
@router.get("/health")
async def health_check():
    """功能：健康检查接口，用于探活与部署监控。"""
    return {"status": "healthy", "message": "GeoMoss Backend is running."}


@router.get("/api/client-ip")
async def client_ip(request: Request):
    """返回客户端公网 IP 地址（替代 ipify.org）。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"
    return {"ip": client_ip}


@router.get("/api/info")
async def get_api_info(request: Request):
    """功能：动态扫描全量接口并提取函数注释。"""
    api_list = []

    for route in request.app.routes:
        if not hasattr(route, "endpoint") or not hasattr(route, "path"):
            continue

        if route.path in ["/openapi.json", "/docs", "/redoc"]:
            continue

        methods = list(route.methods - {"HEAD", "OPTIONS"}) if route.methods else []
        description = (route.endpoint.__doc__ or "暂无说明").strip().split("\n")[0]
        api_list.append({
            "path": route.path,
            "methods": methods,
            "description": description
        })

    api_list.sort(key=lambda item: item["path"])

    return {
        "name": "GeoMoss Backend",
        "version": "3.1.0",
        "description": "GeoMoss WebGIS 后端 API 服务",
        "total_endpoints": len(api_list),
        "endpoints": api_list
    }
