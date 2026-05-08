"""
Terrain layer API.

The first terrain implementation is deliberately lightweight for a 4C/8G
server: GDAL crops the source DEM once, then Cesium requests small heightmap
tiles on demand. The frontend can later swap this provider for quantized-mesh
without changing the public terrain layer contract.
"""

import asyncio
import json
import logging
import math
import os
import subprocess
import struct
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_auth_db_connection, require_admin

try:
    from osgeo import gdal
except Exception:  # pragma: no cover - server dependency is verified at runtime.
    gdal = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terrain", tags=["terrain"])

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
TERRAIN_ROOT = DATA_ROOT / "terrain"
TERRAIN_ROOT.mkdir(parents=True, exist_ok=True)

DEFAULT_DEM_PATH = os.getenv("WEBGIS_DEM_SOURCE_PATH", "/root/project_test/全国DEM/GEBCO-DEM.tif")
GUANGDONG_BBOX = [109.6, 20.0, 117.4, 25.6]
HEIGHTMAP_SIZE = int(os.getenv("WEBGIS_TERRAIN_HEIGHTMAP_SIZE", "32"))
MAX_TERRAIN_TILE_LEVEL = int(os.getenv("WEBGIS_TERRAIN_MAX_LEVEL", "11"))


def _db_connection():
    return get_auth_db_connection()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(text: Any, fallback: Any) -> Any:
    try:
        return json.loads(text) if text else fallback
    except Exception:
        return fallback


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return dict(row) if row else {}


def _ensure_terrain_table_sync() -> None:
    with _db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS terrain_layers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                source_path TEXT NOT NULL DEFAULT '',
                cropped_path TEXT NOT NULL DEFAULT '',
                tile_url_template TEXT NOT NULL DEFAULT '',
                bounds_json TEXT NOT NULL DEFAULT '[]',
                min_height DOUBLE PRECISION NOT NULL DEFAULT 0,
                max_height DOUBLE PRECISION NOT NULL DEFAULT 0,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_terrain_layers_status ON terrain_layers(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_terrain_layers_sort ON terrain_layers(sort_order, updated_at)")
        conn.commit()


def _table_exists_sync(table_name: str) -> bool:
    with _db_connection() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = ? AND table_name = ?
            ) AS table_exists
            """,
            ("public", table_name),
        ).fetchone()
    return bool(_row_to_dict(row).get("table_exists"))


def _column_exists_sync(table_name: str, column_name: str) -> bool:
    with _db_connection() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = ? AND table_name = ? AND column_name = ?
            ) AS column_exists
            """,
            ("public", table_name, column_name),
        ).fetchone()
    return bool(_row_to_dict(row).get("column_exists"))


def _ensure_boundary_geometry_column_sync() -> bool:
    if not _table_exists_sync("admin_boundary_features"):
        return False
    if _column_exists_sync("admin_boundary_features", "geometry_json"):
        return True
    with _db_connection() as conn:
        conn.execute("ALTER TABLE admin_boundary_features ADD COLUMN geometry_json TEXT NOT NULL DEFAULT '{}'")
        conn.commit()
    return True


def _terrain_from_row(row: Any) -> Dict[str, Any]:
    item = _row_to_dict(row)
    item["bounds"] = _json_loads(item.pop("bounds_json", "[]"), [])
    item["metadata"] = _json_loads(item.pop("metadata_json", "{}"), {})
    return item


def _public_terrain_from_row(row: Any) -> Dict[str, Any]:
    item = _terrain_from_row(row)
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "地形图层"),
        "description": str(item.get("description") or ""),
        "status": str(item.get("status") or ""),
        "tile_url_template": str(item.get("tile_url_template") or ""),
        "bounds": item.get("bounds") or [],
        "min_height": float(item.get("min_height") or 0),
        "max_height": float(item.get("max_height") or 0),
        "width": int(item.get("width") or 0),
        "height": int(item.get("height") or 0),
        "metadata": item.get("metadata") or {},
        "published_at": str(item.get("published_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }


def _list_public_terrain_layers_sync() -> list[Dict[str, Any]]:
    _ensure_terrain_table_sync()
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, description, status, tile_url_template, bounds_json,
                   min_height, max_height, width, height, metadata_json, published_at, updated_at
            FROM terrain_layers
            WHERE status = 'published' AND cropped_path != ''
            ORDER BY sort_order ASC, updated_at DESC
            """
        ).fetchall()
    return [_public_terrain_from_row(row) for row in rows]


def _list_admin_terrain_layers_sync() -> list[Dict[str, Any]]:
    _ensure_terrain_table_sync()
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, description, status, source_path, cropped_path, tile_url_template,
                   bounds_json, min_height, max_height, width, height, metadata_json,
                   sort_order, published_at, created_by, created_at, updated_at
            FROM terrain_layers
            ORDER BY sort_order ASC, updated_at DESC
            """
        ).fetchall()
    return [_terrain_from_row(row) for row in rows]


def _get_boundary_geometry_sync() -> tuple[Optional[dict], Optional[list[float]], str]:
    _ensure_terrain_table_sync()
    if not _ensure_boundary_geometry_column_sync():
        return None, None, "fallback_bbox"
    with _db_connection() as conn:
        row = conn.execute(
            """
            SELECT geometry_json, bbox_json, dataset_id, code, name
            FROM admin_boundary_features
            WHERE name LIKE ? OR code LIKE ?
            ORDER BY
              CASE WHEN code = '440000' THEN 0 WHEN code LIKE ? THEN 1 ELSE 2 END,
              code ASC
            LIMIT 1
            """,
            ("%广东%", "44%", "44%"),
        ).fetchone()
    if not row:
        return None, None, "fallback_bbox"

    item = _row_to_dict(row)
    geometry = _json_loads(item.get("geometry_json"), {})
    bbox = _json_loads(item.get("bbox_json"), [])
    if geometry:
        return geometry, bbox, "admin_boundary"
    if isinstance(bbox, list) and len(bbox) >= 4:
        return None, [float(v) for v in bbox[:4]], "admin_boundary_bbox"
    return None, None, "fallback_bbox"


def _write_cutline_geojson(path: Path, geometry: dict) -> None:
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"name": "广东省"},
            "geometry": geometry,
        }],
    }
    path.write_text(_json_dumps(payload), encoding="utf-8")


def _run_command(args: list[str]) -> None:
    logger.info("Running command: %s", " ".join(args))
    proc = subprocess.run(args, check=False, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "GDAL command failed")[:1200])


def _read_raster_stats(path: Path) -> Dict[str, Any]:
    if gdal is None:
        raise RuntimeError("服务器 Python 缺少 osgeo.gdal，无法读取 DEM")
    dataset = gdal.Open(str(path))
    if dataset is None:
        raise RuntimeError(f"DEM 无法打开: {path}")
    band = dataset.GetRasterBand(1)
    stats = band.GetStatistics(True, True) or [0, 0, 0, 0]
    gt = dataset.GetGeoTransform()
    min_lon = float(gt[0])
    max_lat = float(gt[3])
    max_lon = min_lon + float(gt[1]) * int(dataset.RasterXSize)
    min_lat = max_lat + float(gt[5]) * int(dataset.RasterYSize)
    return {
        "bounds": [min(min_lon, max_lon), min(min_lat, max_lat), max(min_lon, max_lon), max(min_lat, max_lat)],
        "min_height": float(stats[0]),
        "max_height": float(stats[1]),
        "width": int(dataset.RasterXSize),
        "height": int(dataset.RasterYSize),
    }


def _create_or_update_guangdong_dem_sync(admin_username: str = "admin") -> Dict[str, Any]:
    _ensure_terrain_table_sync()
    source_path = Path(DEFAULT_DEM_PATH)
    if not source_path.exists():
        raise HTTPException(status_code=404, detail=f"未找到 DEM 源文件: {source_path}")

    layer_id = "guangdong-dem"
    layer_dir = TERRAIN_ROOT / layer_id
    layer_dir.mkdir(parents=True, exist_ok=True)
    cropped_path = layer_dir / "guangdong_dem.tif"
    cutline_path = layer_dir / "guangdong_boundary.geojson"

    geometry, bbox, boundary_mode = _get_boundary_geometry_sync()
    if geometry:
        _write_cutline_geojson(cutline_path, geometry)
        args = [
            "gdalwarp",
            "-overwrite",
            "-of", "GTiff",
            "-co", "TILED=YES",
            "-co", "COMPRESS=DEFLATE",
            "-dstnodata", "-32768",
            "-cutline", str(cutline_path),
            "-crop_to_cutline",
            str(source_path),
            str(cropped_path),
        ]
    else:
        min_lon, min_lat, max_lon, max_lat = [float(v) for v in (bbox or GUANGDONG_BBOX)[:4]]
        args = [
            "gdalwarp",
            "-overwrite",
            "-of", "GTiff",
            "-co", "TILED=YES",
            "-co", "COMPRESS=DEFLATE",
            "-dstnodata", "-32768",
            "-te", str(min_lon), str(min_lat), str(max_lon), str(max_lat),
            str(source_path),
            str(cropped_path),
        ]

    _run_command(args)
    _run_command(["gdaladdo", "-r", "average", str(cropped_path), "2", "4", "8", "16"])

    stats = _read_raster_stats(cropped_path)
    now_iso = _iso_now()
    metadata = {
        "source": "GEBCO-DEM",
        "source_path": str(source_path),
        "crop_mode": boundary_mode,
        "heightmap_size": HEIGHTMAP_SIZE,
        "max_tile_level": MAX_TERRAIN_TILE_LEVEL,
        "fallback_bbox": boundary_mode == "fallback_bbox",
    }

    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO terrain_layers (
                id, name, description, status, source_path, cropped_path, tile_url_template,
                bounds_json, min_height, max_height, width, height, metadata_json,
                published_at, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = excluded.status,
                source_path = excluded.source_path,
                cropped_path = excluded.cropped_path,
                tile_url_template = excluded.tile_url_template,
                bounds_json = excluded.bounds_json,
                min_height = excluded.min_height,
                max_height = excluded.max_height,
                width = excluded.width,
                height = excluded.height,
                metadata_json = excluded.metadata_json,
                published_at = excluded.published_at,
                updated_at = excluded.updated_at
            """,
            (
                layer_id,
                "广东省 DEM 地形",
                "由全国 DEM 裁剪生成的广东省三维地形，高度瓦片按需采样。",
                str(source_path),
                str(cropped_path),
                f"/api/terrain/{layer_id}/heightmap/{{z}}/{{x}}/{{y}}.json",
                _json_dumps(stats["bounds"]),
                stats["min_height"],
                stats["max_height"],
                stats["width"],
                stats["height"],
                _json_dumps(metadata),
                now_iso,
                admin_username,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()

    return {
        "id": layer_id,
        "name": "广东省 DEM 地形",
        **stats,
        "metadata": metadata,
        "tile_url_template": f"/api/terrain/{layer_id}/heightmap/{{z}}/{{x}}/{{y}}.json",
    }


def _get_terrain_layer_sync(layer_id: str) -> Dict[str, Any]:
    _ensure_terrain_table_sync()
    with _db_connection() as conn:
        row = conn.execute(
            """
            SELECT id, name, status, cropped_path, bounds_json, min_height, max_height, metadata_json
            FROM terrain_layers
            WHERE id = ?
            """,
            (layer_id,),
        ).fetchone()
    item = _terrain_from_row(row)
    if not item:
        raise HTTPException(status_code=404, detail="地形图层不存在")
    return item


def _geographic_tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    tiles_x = 2 ** (int(z) + 1)
    tiles_y = 2 ** int(z)
    lon_width = 360.0 / tiles_x
    lat_height = 180.0 / tiles_y
    west = -180.0 + int(x) * lon_width
    east = west + lon_width
    north = 90.0 - int(y) * lat_height
    south = north - lat_height
    return west, south, east, north


def _intersects(a: list[float], b: tuple[float, float, float, float]) -> bool:
    return not (b[2] < a[0] or b[0] > a[2] or b[3] < a[1] or b[1] > a[3])


@lru_cache(maxsize=512)
def _sample_heightmap(cropped_path: str, x: int, y: int, z: int, size: int) -> tuple[tuple[float, ...], bool]:
    if gdal is None:
        raise RuntimeError("服务器 Python 缺少 osgeo.gdal，无法采样 DEM")

    dataset = gdal.Open(cropped_path)
    if dataset is None:
        raise RuntimeError("DEM 图层文件无法打开")

    west, south, east, north = _geographic_tile_bounds(x, y, z)
    vrt = gdal.Translate(
        "",
        dataset,
        format="VRT",
        projWin=[west, north, east, south],
        width=size,
        height=size,
        resampleAlg="bilinear",
    )
    if vrt is None:
        return tuple([0.0] * (size * size)), False

    band = vrt.GetRasterBand(1)
    raw = band.ReadRaster(
        0,
        0,
        size,
        size,
        buf_xsize=size,
        buf_ysize=size,
        buf_type=gdal.GDT_Float32,
    )
    if raw is None:
        return tuple([0.0] * (size * size)), False

    nodata = band.GetNoDataValue()
    expected_count = size * size
    expected_bytes = expected_count * 4
    if len(raw) < expected_bytes:
        return tuple([0.0] * expected_count), False

    unpacked = struct.unpack(f"={expected_count}f", raw[:expected_bytes])
    cleaned: list[float] = []
    has_data = False
    nodata_value = float(nodata) if nodata is not None else None
    for value in unpacked:
        number = float(value)
        valid = math.isfinite(number)
        if nodata_value is not None and number == nodata_value:
            valid = False
        if valid:
            has_data = True
            cleaned.append(max(-500.0, min(9000.0, number)))
        else:
            cleaned.append(0.0)
    return tuple(cleaned), has_data


@router.get("/layers/published")
async def list_published_terrain_layers() -> Dict[str, Any]:
    layers = await asyncio.to_thread(_list_public_terrain_layers_sync)
    return {"status": "success", "data": layers, "available": bool(layers)}


@router.get("/{layer_id}/heightmap/{z}/{x}/{y}.json")
async def get_heightmap_tile(layer_id: str, z: int, x: int, y: int) -> Dict[str, Any]:
    if z < 0 or z > MAX_TERRAIN_TILE_LEVEL:
        return {"width": HEIGHTMAP_SIZE, "height": HEIGHTMAP_SIZE, "heights": [0.0] * (HEIGHTMAP_SIZE * HEIGHTMAP_SIZE), "available": False}

    layer = await asyncio.to_thread(_get_terrain_layer_sync, layer_id)
    bounds = layer.get("bounds") or []
    tile_bounds = _geographic_tile_bounds(x, y, z)
    if not (isinstance(bounds, list) and len(bounds) >= 4 and _intersects([float(v) for v in bounds[:4]], tile_bounds)):
        return {"width": HEIGHTMAP_SIZE, "height": HEIGHTMAP_SIZE, "heights": [0.0] * (HEIGHTMAP_SIZE * HEIGHTMAP_SIZE), "available": False}

    cropped_path = str(layer.get("cropped_path") or "")
    try:
        values, has_data = await asyncio.to_thread(_sample_heightmap, cropped_path, int(x), int(y), int(z), HEIGHTMAP_SIZE)
    except Exception as exc:
        logger.warning("Terrain tile sample failed: %s", exc)
        raise HTTPException(status_code=500, detail="地形瓦片采样失败")

    return {
        "width": HEIGHTMAP_SIZE,
        "height": HEIGHTMAP_SIZE,
        "bounds": tile_bounds,
        "available": has_data,
        "heights": list(values),
    }


@router.get("/admin/layers")
async def list_admin_terrain_layers(_session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return {"status": "success", "data": await asyncio.to_thread(_list_admin_terrain_layers_sync)}


@router.post("/admin/guangdong-dem")
async def publish_guangdong_dem(session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    admin_username = str(session.get("username") or "admin")
    data = await asyncio.to_thread(_create_or_update_guangdong_dem_sync, admin_username)
    return {"status": "success", "data": data}
