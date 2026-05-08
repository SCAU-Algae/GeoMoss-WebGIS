import math
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import Request

from api.auth import get_auth_db_connection

from .geometry import bbox_of_geometry, center_of_bbox


AMAP_REST_ROOT = "https://restapi.amap.com"
AMAP_TIMEOUT_SECONDS = float(os.getenv("FENGSHUI_AMAP_CONTEXT_TIMEOUT_SECONDS", "10"))
AMAP_SUCCESS_STATUS = "1"
AMAP_SUCCESS_INFOCODE = "10000"

PI = math.pi
GCJ_A = 6378245.0
GCJ_EE = 0.00669342162296594323


def _get_api_key_from_db_sync(key_name: str) -> str:
    try:
        with get_auth_db_connection() as conn:
            row = conn.execute(
                "SELECT key_value FROM api_keys WHERE key_name = ?",
                (key_name,),
            ).fetchone()
            if row:
                return str(dict(row).get("key_value") or "").strip()
    except Exception:
        pass
    return ""


def _resolve_amap_key() -> str:
    db_key = _get_api_key_from_db_sync("amap_key")
    if db_key:
        return db_key
    for env_name in ("AMAP_WEB_SERVICE_KEY", "AMAP_KEY", "GAODE_KEY", "VITE_AMAP_WEB_SERVICE_KEY"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def get_location_context_status() -> Dict[str, Any]:
    key = _resolve_amap_key()
    return {
        "available": bool(key),
        "api_key_source": "configured" if key else "missing",
        "message": "高德地理语义已配置。" if key else "高德 Web 服务 Key 未配置，地理语义将跳过。",
    }


def _out_of_china(lon: float, lat: float) -> bool:
    return lon < 72.004 or lon > 137.8347 or lat < 0.8293 or lat > 55.8271


def _transform_lat(lon: float, lat: float) -> float:
    ret = -100.0 + 2.0 * lon + 3.0 * lat + 0.2 * lat * lat + 0.1 * lon * lat + 0.2 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * PI) + 20.0 * math.sin(2.0 * lon * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * PI) + 40.0 * math.sin(lat / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * PI) + 320 * math.sin(lat * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(lon: float, lat: float) -> float:
    ret = 300.0 + lon + 2.0 * lat + 0.1 * lon * lon + 0.1 * lon * lat + 0.1 * math.sqrt(abs(lon))
    ret += (20.0 * math.sin(6.0 * lon * PI) + 20.0 * math.sin(2.0 * lon * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lon * PI) + 40.0 * math.sin(lon / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lon / 12.0 * PI) + 300.0 * math.sin(lon / 30.0 * PI)) * 2.0 / 3.0
    return ret


def wgs84_to_gcj02(lon: float, lat: float) -> Tuple[float, float]:
    lon = float(lon)
    lat = float(lat)
    if _out_of_china(lon, lat):
        return lon, lat
    d_lat = _transform_lat(lon - 105.0, lat - 35.0)
    d_lon = _transform_lon(lon - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * PI
    magic = math.sin(rad_lat)
    magic = 1 - GCJ_EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    d_lat = (d_lat * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrt_magic) * PI)
    d_lon = (d_lon * 180.0) / (GCJ_A / sqrt_magic * math.cos(rad_lat) * PI)
    return lon + d_lon, lat + d_lat


def _empty_context(status: str, message: str = "") -> Dict[str, Any]:
    return {
        "available": False,
        "status": status,
        "formatted_address": "",
        "admin": {},
        "pois": [],
        "poi_categories": [],
        "aois": [],
        "roads": [],
        "center_gcj02": None,
        "radius_m": None,
        "message": message,
    }


def _area_radius_m(geometry: Dict[str, Any]) -> int:
    min_lon, min_lat, max_lon, max_lat = bbox_of_geometry(geometry)
    center_lat = (min_lat + max_lat) / 2
    meters_per_lon = 111_320 * max(math.cos(math.radians(center_lat)), 0.01)
    width_m = abs(max_lon - min_lon) * meters_per_lon
    height_m = abs(max_lat - min_lat) * 110_540
    return int(max(500, min(5000, max(width_m, height_m) * 0.75)))


def _amap_ok(payload: Dict[str, Any]) -> bool:
    return str(payload.get("status") or "") == AMAP_SUCCESS_STATUS and str(payload.get("infocode") or AMAP_SUCCESS_INFOCODE) == AMAP_SUCCESS_INFOCODE


async def _amap_get(client: httpx.AsyncClient, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    response = await client.get(f"{AMAP_REST_ROOT}{path}", params=params)
    if response.status_code != 200:
        return {"status": "0", "info": f"HTTP {response.status_code}", "infocode": ""}
    try:
        payload = response.json()
    except Exception:
        return {"status": "0", "info": "上游返回非 JSON", "infocode": ""}
    return payload if isinstance(payload, dict) else {"status": "0", "info": "上游结构异常", "infocode": ""}


def _normalize_regeocode(payload: Dict[str, Any]) -> Dict[str, Any]:
    regeocode = payload.get("regeocode") or {}
    address_component = regeocode.get("addressComponent") or {}
    township = address_component.get("township")
    if isinstance(township, list):
        township = township[0] if township else ""
    admin = {
        "province": address_component.get("province") or "",
        "city": address_component.get("city") or "",
        "district": address_component.get("district") or "",
        "township": township or "",
        "adcode": address_component.get("adcode") or "",
        "citycode": address_component.get("citycode") or "",
    }
    roads = []
    for road in regeocode.get("roads") or []:
        if isinstance(road, dict):
            name = str(road.get("name") or "").strip()
            if name:
                roads.append({"name": name, "distance_m": road.get("distance"), "direction": road.get("direction")})
    aois = []
    for aoi in regeocode.get("aois") or []:
        if isinstance(aoi, dict):
            name = str(aoi.get("name") or "").strip()
            if name:
                aois.append({"name": name, "type": aoi.get("type") or "", "distance_m": aoi.get("distance"), "area": aoi.get("area")})
    return {
        "formatted_address": regeocode.get("formatted_address") or "",
        "admin": admin,
        "roads": roads[:6],
        "aois": aois[:6],
    }


def _normalize_pois(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    pois: List[Dict[str, Any]] = []
    for poi in payload.get("pois") or []:
        if not isinstance(poi, dict):
            continue
        name = str(poi.get("name") or "").strip()
        if not name:
            continue
        pois.append({
            "name": name[:80],
            "type": str(poi.get("type") or "")[:80],
            "typecode": str(poi.get("typecode") or ""),
            "distance_m": poi.get("distance"),
            "address": str(poi.get("address") or "")[:120],
        })
        if len(pois) >= 16:
            break
    return pois


def _summarize_categories(pois: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    for poi in pois:
        category = str(poi.get("type") or "").split(";")[0].strip() or "未分类"
        counter[category] += 1
    return [{"name": name, "count": count} for name, count in counter.most_common(8)]


async def collect_location_context(
    request: Request,
    geometry: Dict[str, Any],
    *,
    area_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    amap_key = _resolve_amap_key()
    if not amap_key:
        return _empty_context("unconfigured", "高德 Web 服务 Key 未配置，已跳过位置语义。")

    bbox = bbox_of_geometry(geometry)
    center_lon, center_lat = center_of_bbox(bbox)
    gcj_lon, gcj_lat = wgs84_to_gcj02(center_lon, center_lat)
    radius_m = _area_radius_m(geometry)
    common_headers = {
        "User-Agent": "WebGIS-FengshuiContext/1.0",
        "Accept": "application/json,text/plain,*/*",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(AMAP_TIMEOUT_SECONDS, connect=4.0),
            follow_redirects=True,
            headers=common_headers,
        ) as client:
            regeo_payload = await _amap_get(
                client,
                "/v3/geocode/regeo",
                {
                    "key": amap_key,
                    "location": f"{gcj_lon:.7f},{gcj_lat:.7f}",
                    "extensions": "all",
                    "radius": min(3000, radius_m),
                    "batch": "false",
                },
            )
            poi_payload = await _amap_get(
                client,
                "/v5/place/around",
                {
                    "key": amap_key,
                    "location": f"{gcj_lon:.7f},{gcj_lat:.7f}",
                    "radius": radius_m,
                    "sortrule": "distance",
                    "offset": 20,
                    "page": 1,
                    "show_fields": "business,indoor,navi,photos",
                },
            )
            if not _amap_ok(poi_payload):
                poi_payload = await _amap_get(
                    client,
                    "/v3/place/around",
                    {
                        "key": amap_key,
                        "location": f"{gcj_lon:.7f},{gcj_lat:.7f}",
                        "radius": radius_m,
                        "sortrule": "distance",
                        "offset": 20,
                        "page": 1,
                        "extensions": "base",
                    },
                )
    except Exception as exc:
        return _empty_context("error", f"高德位置语义调用失败：{str(exc)[:140]}")

    regeo_ok = _amap_ok(regeo_payload)
    poi_ok = _amap_ok(poi_payload)
    if not regeo_ok and not poi_ok:
        info = str(regeo_payload.get("info") or poi_payload.get("info") or "高德接口返回失败")
        return _empty_context("error", f"高德位置语义不可用：{info[:120]}")

    regeo = _normalize_regeocode(regeo_payload) if regeo_ok else {"formatted_address": "", "admin": {}, "roads": [], "aois": []}
    pois = _normalize_pois(poi_payload) if poi_ok else []
    admin = regeo.get("admin") or {}
    address = str(regeo.get("formatted_address") or "").strip()
    admin_line = "".join(str(admin.get(key) or "") for key in ("province", "city", "district", "township"))
    if not address:
        address = admin_line

    return {
        "available": True,
        "status": "ready",
        "formatted_address": address,
        "admin": admin,
        "pois": pois,
        "poi_categories": _summarize_categories(pois),
        "aois": regeo.get("aois") or [],
        "roads": regeo.get("roads") or [],
        "center_wgs84": {"lon": round(center_lon, 7), "lat": round(center_lat, 7)},
        "center_gcj02": {"lon": round(gcj_lon, 7), "lat": round(gcj_lat, 7)},
        "radius_m": radius_m,
        "message": "已接入高德逆地理编码和周边 POI 语义。",
    }
