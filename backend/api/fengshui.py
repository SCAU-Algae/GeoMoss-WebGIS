import asyncio
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.fengshui.ai_insights import generate_ai_insights, get_ai_insights_status
from services.fengshui.geometry import build_area_info, geometry_from_feature, make_circle_feature
from services.fengshui.imagery_capture import capture_remote_sensing_evidence
from services.fengshui.location_context import collect_location_context, get_location_context_status
from services.fengshui.report import DISCLAIMER, build_metric_explanations, build_report, build_spatial_pattern, build_recommendations
from services.fengshui.scoring import calculate_scores, score_level
from services.fengshui.terrain import analyze_dem, resolve_dem_path
from services.fengshui.visual_water import analyze_visual_water, get_visual_water_status
from services.fengshui.water import analyze_water, resolve_water_paths


router = APIRouter(prefix="/api/fengshui", tags=["fengshui"])


class FengshuiAnalyzeRequest(BaseModel):
    mode: Literal["circle", "geojson"] = "circle"
    center: Optional[Dict[str, float]] = None
    radius_m: float = Field(default=1500.0, ge=20.0, le=200000.0)
    geojson: Optional[Dict[str, Any]] = None
    use_mock: bool = False
    include_ai: bool = True
    include_visual: bool = True
    include_location_context: bool = True


def _build_geometry(payload: FengshuiAnalyzeRequest) -> Dict[str, Any]:
    if payload.mode == "geojson":
        if not payload.geojson:
            raise ValueError("请提供 GeoJSON 研究范围")
        feature = payload.geojson
    else:
        center = payload.center or {}
        lon = float(center.get("lon", center.get("lng", 113.351948)))
        lat = float(center.get("lat", 23.160345))
        feature = make_circle_feature(lon, lat, payload.radius_m)

    return geometry_from_feature(feature)


def _analyze_sync(payload: FengshuiAnalyzeRequest, geometry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    geometry = geometry or _build_geometry(payload)
    area_info = build_area_info(geometry)

    if payload.use_mock:
        from services.fengshui.terrain import _mock_metrics
        terrain_metrics, terrain_status = _mock_metrics(geometry, "已按请求使用模拟指标。")
    else:
        terrain_metrics, terrain_status = analyze_dem(geometry)

    water_status = analyze_water(geometry)
    scores = calculate_scores(terrain_metrics, water_status)
    pattern = build_spatial_pattern(terrain_metrics, water_status)
    recommendations = build_recommendations(terrain_metrics, scores, water_status)
    report = build_report(area_info, terrain_metrics, pattern, scores, water_status)

    return {
        "area_info": area_info,
        "terrain_metrics": terrain_metrics,
        "spatial_pattern": pattern,
        "scores": scores,
        "score_level": score_level(scores["overall_score"]),
        "data_status": {
            "dem": terrain_status,
            "water": water_status,
        },
        "evidence_priority": {
            "water": "visual_water_when_ready",
            "rule": "千问视觉识别成功时，以北向遥感图像识别结果作为水体方位、类型和可见范围的优先证据；矢量水系保留为复核背景。",
        },
        "recommendations": recommendations,
        "metric_explanations": build_metric_explanations(),
        "report": report,
        "disclaimer": DISCLAIMER,
    }


@router.get("/status")
async def get_fengshui_status() -> Dict[str, Any]:
    dem_path = resolve_dem_path()
    water_paths = resolve_water_paths()
    water_path = water_paths.get("polygon") or water_paths.get("line")
    return {
        "status": "success",
        "data": {
            "dem": {
                "configured_path": str(dem_path),
                "available": dem_path.exists(),
            },
            "water": {
                "configured_path": str(water_path or ""),
                "available": bool(water_path and water_path.exists()),
                "polygon_path": str(water_paths.get("polygon") or ""),
                "line_path": str(water_paths.get("line") or ""),
            },
            "ai": get_ai_insights_status(),
            "visual_water": get_visual_water_status(),
            "location_context": get_location_context_status(),
            "supported_modes": ["circle", "geojson"],
        },
    }


@router.post("/analyze")
async def analyze_fengshui(payload: FengshuiAnalyzeRequest, request: Request) -> Dict[str, Any]:
    geometry = await asyncio.to_thread(_build_geometry, payload)
    data = await asyncio.to_thread(_analyze_sync, payload, geometry)
    area_info = data.get("area_info") or build_area_info(geometry)
    water_status = (data.get("data_status") or {}).get("water") or {}

    if payload.include_visual:
        capture = await capture_remote_sensing_evidence(request, geometry)
        capture_public = {key: value for key, value in capture.items() if key != "image_bytes"}
        visual_water = await analyze_visual_water(
            request,
            capture,
            area_info=area_info,
            water_status=water_status,
        )
        data["remote_sensing_evidence"] = capture_public
        data["visual_water"] = visual_water
        data.setdefault("data_status", {})["remote_sensing"] = capture_public
        data.setdefault("data_status", {})["visual_water"] = visual_water

    if payload.include_location_context:
        location_context = await collect_location_context(request, geometry, area_info=area_info)
        data["location_context"] = location_context
        data.setdefault("data_status", {})["location_context"] = {
            "available": bool(location_context.get("available")),
            "status": location_context.get("status"),
            "message": location_context.get("message"),
        }

    data["evidence_conflicts"] = _detect_evidence_conflicts(data)

    if payload.include_ai:
        session = await _resolve_optional_session(request)
        data["ai_insights"] = await generate_ai_insights(request, data, session=session)
    return {"status": "success", "data": data}


def _detect_evidence_conflicts(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    water = (data.get("data_status") or {}).get("water") or {}
    visual = data.get("visual_water") or (data.get("data_status") or {}).get("visual_water") or {}
    if not visual.get("available"):
        return []

    conflicts: List[Dict[str, Any]] = []
    vector_has_water = bool(water.get("available")) and (
        bool(water.get("intersects")) or float(water.get("nearest_distance_m") or 999999) <= 1500
    )
    visual_presence = str(visual.get("water_presence") or "").lower()
    visual_has_water = visual_presence in {"possible", "clear"}

    if vector_has_water and visual_presence == "none":
        conflicts.append({
            "type": "water_presence",
            "priority": "visual_water",
            "message": "矢量水系提示附近有水体，但视觉模型未识别到明显水体；报告将以视觉结果为准，并建议复核底图时相和水系数据。",
        })
    elif not vector_has_water and visual_has_water:
        conflicts.append({
            "type": "water_presence",
            "priority": "visual_water",
            "message": "矢量水系未检出近邻水体，但视觉模型识别到可见水体；报告将以视觉结果为准。",
        })

    vector_direction = str(water.get("direction") or "").strip()
    visual_direction = str(visual.get("dominant_direction") or "").strip().lower()
    if visual_has_water and vector_direction and vector_direction not in {"未识别", "内部"} and visual_direction not in {"", "unknown", "multiple", "center"}:
        direction_map = {
            "北": "north",
            "东北": "northeast",
            "东": "east",
            "东南": "southeast",
            "南": "south",
            "西南": "southwest",
            "西": "west",
            "西北": "northwest",
        }
        if direction_map.get(vector_direction) and direction_map.get(vector_direction) != visual_direction:
            conflicts.append({
                "type": "water_direction",
                "priority": "visual_water",
                "message": f"矢量水系方位为{vector_direction}，视觉模型判断为{visual_direction}；水体方位解释以视觉结果为准。",
            })

    return conflicts


async def _resolve_optional_session(request: Request) -> Optional[Dict[str, Any]]:
    try:
        from api.auth import _extract_token, _get_session_sync, init_auth_storage

        token = _extract_token(request)
        if not token:
            return None
        await init_auth_storage()
        return await asyncio.to_thread(_get_session_sync, token)
    except Exception:
        return None
