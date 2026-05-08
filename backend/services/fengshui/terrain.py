import math
import os
import struct
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from .geometry import bbox_of_geometry, build_area_info

try:
    from osgeo import gdal
except Exception:  # pragma: no cover - runtime dependency.
    gdal = None


DEFAULT_DEM_PATH = os.getenv(
    "WEBGIS_FENGSHUI_DEM_PATH",
    os.getenv("WEBGIS_DEM_SOURCE_PATH", "/root/project_test/全国DEM/GEBCO-DEM.tif"),
)


def resolve_dem_path() -> Path:
    return Path(DEFAULT_DEM_PATH)


def _aspect_name(degree: float) -> str:
    names = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return names[int(((float(degree) + 22.5) % 360) / 45)]


def _mock_metrics(geometry: Dict[str, Any], reason: str = "") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    area_info = build_area_info(geometry)
    bbox = area_info["bbox"]
    span = max(abs(float(bbox[2]) - float(bbox[0])), abs(float(bbox[3]) - float(bbox[1])))
    scale = max(0.45, min(span * 60, 3.2))
    mean_elevation = 130 + scale * 22
    relief = 72 + scale * 18
    mean_slope = 5.8 + scale * 1.45
    metrics = {
        "mean_elevation": round(mean_elevation, 1),
        "max_elevation": round(mean_elevation + relief * 0.56, 1),
        "min_elevation": round(mean_elevation - relief * 0.44, 1),
        "relief": round(relief, 1),
        "mean_slope": round(mean_slope, 1),
        "max_slope": round(mean_slope * 2.45, 1),
        "dominant_aspect": "东南",
        "terrain_position": "缓坡台地",
        "terrain_roughness": round(0.3 + scale * 0.055, 2),
    }
    status = {
        "available": False,
        "source": "fallback_mock",
        "message": reason or "未检测到可用 DEM，已使用稳定模拟指标保持流程可用。",
    }
    return metrics, status


def analyze_dem(geometry: Dict[str, Any], dem_path: Path | None = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    dem_path = dem_path or resolve_dem_path()
    if gdal is None:
        return _mock_metrics(geometry, "服务器 Python 缺少 GDAL，暂使用模拟地形指标。")
    if not dem_path.exists():
        return _mock_metrics(geometry, f"未找到 DEM 源文件：{dem_path}，暂使用模拟地形指标。")

    bbox = bbox_of_geometry(geometry)
    dataset = gdal.Open(str(dem_path))
    if dataset is None:
        return _mock_metrics(geometry, f"DEM 无法打开：{dem_path}，暂使用模拟地形指标。")

    west, south, east, north = [float(value) for value in bbox]
    if east <= west or north <= south:
        return _mock_metrics(geometry, "研究范围坐标异常，暂使用模拟地形指标。")

    sample_size = int(os.getenv("WEBGIS_FENGSHUI_SAMPLE_SIZE", "160"))
    sample_size = max(48, min(sample_size, 256))
    try:
        clipped = gdal.Translate(
            "",
            dataset,
            format="VRT",
            projWin=[west, north, east, south],
            width=sample_size,
            height=sample_size,
            resampleAlg="bilinear",
        )
        if clipped is None:
            return _mock_metrics(geometry, "DEM 裁剪范围无有效数据，暂使用模拟地形指标。")
        band = clipped.GetRasterBand(1)
        raw = band.ReadRaster(
            0,
            0,
            sample_size,
            sample_size,
            buf_xsize=sample_size,
            buf_ysize=sample_size,
            buf_type=gdal.GDT_Float32,
        )
        expected_count = sample_size * sample_size
        if raw is None or len(raw) < expected_count * 4:
            return _mock_metrics(geometry, "DEM 采样结果为空，暂使用模拟地形指标。")
        array = np.array(struct.unpack(f"={expected_count}f", raw[:expected_count * 4]), dtype="float64").reshape((sample_size, sample_size))
        nodata = band.GetNoDataValue()
        if nodata is not None:
            array[array == float(nodata)] = np.nan
        array[~np.isfinite(array)] = np.nan
        valid = array[np.isfinite(array)]
        if valid.size <= 0:
            return _mock_metrics(geometry, "研究范围内 DEM 没有有效像元，暂使用模拟地形指标。")

        center_lat = (south + north) / 2
        width_m = max((east - west) * 111_320 * max(math.cos(math.radians(center_lat)), 0.01), 1.0)
        height_m = max((north - south) * 110_540, 1.0)
        xres = width_m / max(sample_size - 1, 1)
        yres = height_m / max(sample_size - 1, 1)
        gy, gx = np.gradient(array, yres, xres)
        slope = np.degrees(np.arctan(np.sqrt(gx * gx + gy * gy)))
        aspect_degree = (np.degrees(np.arctan2(-gx, gy)) + 360) % 360
        mean_slope = float(np.nanmean(slope)) if np.isfinite(np.nanmean(slope)) else 0.0
        max_slope = float(np.nanmax(slope)) if np.isfinite(np.nanmax(slope)) else 0.0
        relief = float(np.nanmax(valid) - np.nanmin(valid))
        mean_elevation = float(np.nanmean(valid))
        roughness = float(np.nanstd(valid) / max(abs(mean_elevation), 1.0))
        terrain_position = "缓坡台地" if mean_slope < 8 else "坡地区域" if mean_slope < 18 else "陡坡山地"

        metrics = {
            "mean_elevation": round(mean_elevation, 1),
            "max_elevation": round(float(np.nanmax(valid)), 1),
            "min_elevation": round(float(np.nanmin(valid)), 1),
            "relief": round(relief, 1),
            "mean_slope": round(mean_slope, 1),
            "max_slope": round(max_slope, 1),
            "dominant_aspect": _aspect_name(float(np.nanmedian(aspect_degree))),
            "terrain_position": terrain_position,
            "terrain_roughness": round(roughness, 2),
        }
        status = {
            "available": True,
            "source": str(dem_path),
            "sample_size": sample_size,
            "message": "已基于服务器 DEM 计算地形指标。",
        }
        return metrics, status
    except Exception as exc:
        return _mock_metrics(geometry, f"DEM 分析失败：{str(exc)[:160]}，暂使用模拟地形指标。")
