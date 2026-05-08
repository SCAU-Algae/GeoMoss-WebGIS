import asyncio
import io
import math
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx
from fastapi import Request

from api.auth import get_auth_db_connection

from .geometry import bbox_of_geometry


TILE_SIZE = 256
MAX_TILE_COUNT = int(os.getenv("FENGSHUI_CAPTURE_MAX_TILE_COUNT", "36"))
OUTPUT_LONG_SIDE = int(os.getenv("FENGSHUI_CAPTURE_OUTPUT_LONG_SIDE", "1024"))
MIN_OUTPUT_LONG_SIDE = int(os.getenv("FENGSHUI_CAPTURE_MIN_OUTPUT_LONG_SIDE", "768"))
CAPTURE_TIMEOUT_SECONDS = float(os.getenv("FENGSHUI_CAPTURE_TIMEOUT_SECONDS", "18"))


@dataclass(frozen=True)
class TileSource:
    key: str
    label: str
    requires_key: bool


TILE_SOURCE_ORDER = (
    TileSource("tianditu", "天地图影像", True),
)


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


def _resolve_tianditu_key() -> str:
    db_key = _get_api_key_from_db_sync("tianditu_tk")
    if db_key:
        return db_key
    for env_name in ("TIANDITU_TK", "TIANDITU_TOKEN", "VITE_TIANDITU_TK"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return value
    return ""


def _lonlat_to_tile_float(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    lon = max(-180.0, min(180.0, float(lon)))
    n = 2 ** int(zoom)
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return x, y


def _tile_float_to_pixel(tile_xy: Tuple[float, float]) -> Tuple[float, float]:
    return tile_xy[0] * TILE_SIZE, tile_xy[1] * TILE_SIZE


def _expand_bbox(bbox: List[float], ratio: float = 0.16) -> List[float]:
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox[:4]]
    width = max(max_lon - min_lon, 0.0008)
    height = max(max_lat - min_lat, 0.0008)
    return [
        max(-180.0, min_lon - width * ratio),
        max(-85.0, min_lat - height * ratio),
        min(180.0, max_lon + width * ratio),
        min(85.0, max_lat + height * ratio),
    ]


def _tile_bounds_for_bbox(bbox: List[float], zoom: int) -> Tuple[int, int, int, int, Tuple[float, float], Tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox[:4]]
    top_left = _lonlat_to_tile_float(min_lon, max_lat, zoom)
    bottom_right = _lonlat_to_tile_float(max_lon, min_lat, zoom)
    x0 = max(0, int(math.floor(min(top_left[0], bottom_right[0]))))
    x1 = max(0, int(math.floor(max(top_left[0], bottom_right[0]))))
    y0 = max(0, int(math.floor(min(top_left[1], bottom_right[1]))))
    y1 = max(0, int(math.floor(max(top_left[1], bottom_right[1]))))
    max_index = (2 ** zoom) - 1
    return (
        min(x0, max_index),
        min(y0, max_index),
        min(x1, max_index),
        min(y1, max_index),
        top_left,
        bottom_right,
    )


def _choose_zoom(expanded_bbox: List[float]) -> int:
    best = 6
    for zoom in range(18, 5, -1):
        x0, y0, x1, y1, top_left, bottom_right = _tile_bounds_for_bbox(expanded_bbox, zoom)
        tile_count = (x1 - x0 + 1) * (y1 - y0 + 1)
        pixel_width = abs(bottom_right[0] - top_left[0]) * TILE_SIZE
        pixel_height = abs(bottom_right[1] - top_left[1]) * TILE_SIZE
        pixel_extent = max(pixel_width, pixel_height)
        if tile_count <= MAX_TILE_COUNT and pixel_extent >= 480:
            return zoom
        if tile_count <= MAX_TILE_COUNT:
            best = zoom
    return best


def _tile_url(source_key: str, x: int, y: int, z: int, tianditu_key: str) -> str:
    if source_key == "tianditu":
        subdomain = (x + y + z) % 8
        return (
            f"https://t{subdomain}.tianditu.gov.cn/img_w/wmts"
            f"?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default"
            f"&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk={tianditu_key}"
        )
    raise ValueError(f"Unsupported fengshui imagery source: {source_key}")


async def _fetch_tile(client: httpx.AsyncClient, source_key: str, x: int, y: int, z: int, tianditu_key: str) -> Optional[bytes]:
    url = _tile_url(source_key, x, y, z, tianditu_key)
    try:
        response = await client.get(
            url,
            headers={
                "User-Agent": "WebGIS-FengshuiCapture/1.0",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        if response.status_code == 200 and response.content:
            return bytes(response.content)
    except Exception:
        return None
    return None


def _iter_geometry_rings(geometry: Dict[str, Any]) -> Iterable[List[Any]]:
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geom_type == "Polygon":
        for ring in coordinates:
            yield ring
    elif geom_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                yield ring


def _draw_overlay(image: Any, geometry: Dict[str, Any], zoom: int, crop_left: int, crop_top: int) -> None:
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(image, "RGBA")
    width, height = image.size

    for ring in _iter_geometry_rings(geometry):
        points: List[Tuple[float, float]] = []
        for point in ring:
            if len(point) < 2:
                continue
            tile_xy = _lonlat_to_tile_float(float(point[0]), float(point[1]), zoom)
            px, py = _tile_float_to_pixel(tile_xy)
            points.append((px - crop_left, py - crop_top))
        if len(points) >= 2:
            draw.line(points, fill=(0, 245, 255, 235), width=4, joint="curve")
            draw.line(points, fill=(4, 12, 18, 210), width=1)

    cross_x, cross_y = width / 2, height / 2
    draw.line([(cross_x - 12, cross_y), (cross_x + 12, cross_y)], fill=(255, 255, 255, 215), width=2)
    draw.line([(cross_x, cross_y - 12), (cross_x, cross_y + 12)], fill=(255, 255, 255, 215), width=2)
    draw.ellipse((cross_x - 4, cross_y - 4, cross_x + 4, cross_y + 4), fill=(0, 245, 255, 235))

    arrow_x = width - 42
    arrow_top = 22
    draw.polygon(
        [(arrow_x, arrow_top), (arrow_x - 10, arrow_top + 30), (arrow_x, arrow_top + 23), (arrow_x + 10, arrow_top + 30)],
        fill=(255, 255, 255, 230),
        outline=(0, 0, 0, 120),
    )
    try:
        font = ImageFont.load_default()
        draw.text((arrow_x - 4, arrow_top + 34), "N", fill=(255, 255, 255, 240), font=font)
    except Exception:
        pass

    draw.rectangle((0, 0, width - 1, height - 1), outline=(0, 245, 255, 170), width=2)


def _decode_tile(tile_bytes: bytes) -> Optional[Any]:
    try:
        from PIL import Image

        return Image.open(io.BytesIO(tile_bytes)).convert("RGB")
    except Exception:
        return None


async def _capture_with_source(
    request: Request,
    geometry: Dict[str, Any],
    source: TileSource,
    *,
    tianditu_key: str,
) -> Dict[str, Any]:
    from PIL import Image

    bbox = bbox_of_geometry(geometry)
    expanded_bbox = _expand_bbox(bbox)
    zoom = _choose_zoom(expanded_bbox)
    x0, y0, x1, y1, top_left, bottom_right = _tile_bounds_for_bbox(expanded_bbox, zoom)
    tile_count = (x1 - x0 + 1) * (y1 - y0 + 1)
    if tile_count > MAX_TILE_COUNT:
        return {
            "available": False,
            "status": "too_large",
            "message": f"遥感截图瓦片数过大（{tile_count}），已跳过视觉识别。",
        }

    timeout = httpx.Timeout(CAPTURE_TIMEOUT_SECONDS, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
        tasks = [
            _fetch_tile(client, source.key, x, y, zoom, tianditu_key)
            for y in range(y0, y1 + 1)
            for x in range(x0, x1 + 1)
        ]
        raw_tiles = await asyncio.gather(*tasks)

    decoded_tiles = [_decode_tile(tile) if tile else None for tile in raw_tiles]
    success_count = sum(1 for tile in decoded_tiles if tile is not None)
    if success_count == 0:
        return {
            "available": False,
            "status": "tile_error",
            "message": f"{source.label}瓦片无法加载，已跳过该截图源。",
            "imagery_source": source.key,
        }

    canvas = Image.new("RGB", ((x1 - x0 + 1) * TILE_SIZE, (y1 - y0 + 1) * TILE_SIZE), (28, 32, 36))
    tile_index = 0
    for tile_y in range(y0, y1 + 1):
        for tile_x in range(x0, x1 + 1):
            tile = decoded_tiles[tile_index]
            tile_index += 1
            if tile is not None:
                canvas.paste(tile.resize((TILE_SIZE, TILE_SIZE)), ((tile_x - x0) * TILE_SIZE, (tile_y - y0) * TILE_SIZE))

    crop_left = max(0, int(math.floor(min(top_left[0], bottom_right[0]) * TILE_SIZE)) - x0 * TILE_SIZE)
    crop_top = max(0, int(math.floor(min(top_left[1], bottom_right[1]) * TILE_SIZE)) - y0 * TILE_SIZE)
    crop_right = min(canvas.size[0], int(math.ceil(max(top_left[0], bottom_right[0]) * TILE_SIZE)) - x0 * TILE_SIZE)
    crop_bottom = min(canvas.size[1], int(math.ceil(max(top_left[1], bottom_right[1]) * TILE_SIZE)) - y0 * TILE_SIZE)
    if crop_right - crop_left < 64 or crop_bottom - crop_top < 64:
        crop_left, crop_top, crop_right, crop_bottom = 0, 0, canvas.size[0], canvas.size[1]

    captured = canvas.crop((crop_left, crop_top, crop_right, crop_bottom))
    _draw_overlay(captured, geometry, zoom, crop_left + x0 * TILE_SIZE, crop_top + y0 * TILE_SIZE)

    long_side = max(captured.size)
    target_long_side = OUTPUT_LONG_SIDE if long_side >= MIN_OUTPUT_LONG_SIDE else MIN_OUTPUT_LONG_SIDE
    if long_side != target_long_side:
        scale = target_long_side / max(long_side, 1)
        next_size = (max(1, int(round(captured.size[0] * scale))), max(1, int(round(captured.size[1] * scale))))
        captured = captured.resize(next_size, Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    captured.save(buffer, format="JPEG", quality=90, optimize=True)
    image_bytes = buffer.getvalue()
    return {
        "available": True,
        "status": "ready",
        "image_bytes": image_bytes,
        "mime_type": "image/jpeg",
        "imagery_source": source.key,
        "imagery_label": source.label,
        "zoom": zoom,
        "bbox": [round(float(v), 7) for v in bbox],
        "expanded_bbox": [round(float(v), 7) for v in expanded_bbox],
        "image_size": {"width": captured.size[0], "height": captured.size[1]},
        "tile_count": tile_count,
        "tile_success_count": success_count,
        "message": f"已生成北向遥感证据图（{source.label}，z{zoom}）。",
    }


async def capture_remote_sensing_evidence(request: Request, geometry: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import PIL  # noqa: F401
    except Exception:
        return {
            "available": False,
            "status": "dependency_missing",
            "message": "后端缺少 Pillow，无法生成遥感截图。",
        }

    tianditu_key = _resolve_tianditu_key()
    errors: List[str] = []
    for source in TILE_SOURCE_ORDER:
        if source.requires_key and not tianditu_key:
            errors.append(f"{source.label}未配置密钥")
            continue
        result = await _capture_with_source(request, geometry, source, tianditu_key=tianditu_key)
        if result.get("available"):
            return result
        message = str(result.get("message") or "").strip()
        if message:
            errors.append(message)

    return {
        "available": False,
        "status": "error",
        "imagery_source": "tianditu",
        "imagery_label": "天地图影像",
        "message": "天地图遥感截图生成失败：" + "；".join(errors[:3]),
    }
