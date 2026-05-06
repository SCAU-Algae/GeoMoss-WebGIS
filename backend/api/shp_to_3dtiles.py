"""
SHP → 3D Tiles 转换模块。
将含建筑高度的 Shapefile 转换为 Cesium 3D Tiles (b3dm + tileset.json)。
"""

import io
import json
import logging
import math
import os
import struct
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
import shapefile

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "data" / "3dtiles"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

HEIGHT_FIELD_CANDIDATES = [
    "height", "Height", "HEIGHT", "楼层", "层数", "floor", "FLOOR",
    "building_h", "BUILDING_H", "elevation", "h", "H", "高度", "hgt",
    "storeys", "stories", "levels", "floors", "标高",
]
DEFAULT_FLOOR_HEIGHT = 3.0  # 默认每层 3 米，用于"楼层/层数"字段
DEFAULT_MIN_HEIGHT = 5.0     # 默认最低高度（无有效高度时的回退值）


def _find_height_field(fields: list[str]) -> Optional[str]:
    """在 Shapefile 字段中查找建筑高度相关字段。"""
    for name in HEIGHT_FIELD_CANDIDATES:
        for field in fields:
            if field.lower() == name.lower():
                return field
    return None


def _resolve_height(record, height_field: Optional[str]) -> float:
    """从记录中提取建筑高度（米）。楼层数会自动 ×3。"""
    if not height_field:
        return DEFAULT_MIN_HEIGHT

    try:
        raw = getattr(record, height_field, None)
        if raw is None:
            return DEFAULT_MIN_HEIGHT
        val = float(raw)
        if val <= 0:
            return DEFAULT_MIN_HEIGHT

        # 检测是否为楼层数（通常 ≤200，且字段名含"层/floors"）
        field_lower = height_field.lower()
        is_floor_count = any(
            kw in field_lower for kw in ("层", "floor", "storey", "story", "stories", "level")
        )
        if is_floor_count and val <= 200:
            return val * DEFAULT_FLOOR_HEIGHT
        # 高度值极大（>500 米）视为异常
        if val > 500:
            return DEFAULT_MIN_HEIGHT
        return val
    except (ValueError, TypeError):
        return DEFAULT_MIN_HEIGHT


def _hex_to_rgb(hex_color: str) -> tuple:
    """#rrggbb → (r, g, b) 0-1."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


COLOR_RAMPS = {
    "greens": ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
    "blues": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
    "reds": ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
    "warm": ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#f03b20"],
    "cool": ["#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c"],
}


def _build_gltf_cube(features: list[dict] = None, base_color: str = "#68c282",
                     classification_field: str = "", color_ramp: str = "greens"):
    """构建单位立方体 glTF，可选按分类字段着色。"""
    vertices = np.array([
        [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
        [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5],
    ], dtype=np.float32)

    indices = np.array([
        0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7,
        0, 4, 7, 0, 7, 3, 1, 5, 6, 1, 6, 2,
        0, 1, 5, 0, 5, 4, 3, 2, 6, 3, 6, 7,
    ], dtype=np.uint16)

    vert_bytes = vertices.tobytes()
    idx_bytes = indices.tobytes()
    while len(vert_bytes) % 4: vert_bytes += b'\x00'
    while len(idx_bytes) % 4: idx_bytes += b'\x00'

    buffer_data = vert_bytes + idx_bytes
    total_len = len(buffer_data)

    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": 0, "_FEATURE_ID_0": 2},
                "indices": 1,
                "mode": 4,
            }]
        }],
        "buffers": [{"byteLength": total_len}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(vert_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(vert_bytes), "byteLength": len(idx_bytes), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 8, "type": "VEC3", "max": [0.5, 0.5, 0.5], "min": [-0.5, -0.5, -0.5]},
            {"bufferView": 1, "componentType": 5123, "count": 36, "type": "SCALAR"},
        ],
    }

    gltf["buffers"][0]["uri"] = f"data:application/octet-stream;base64,{_b64(buffer_data)}"
    return gltf


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def _build_b3dm(features: list[dict], progress_cb=None, base_color: str = "#68c282",
                classification_field: str = "", color_ramp: str = "greens") -> bytes:
    """
    构建单个 b3dm 文件。
    每个 feature = { lon, lat, width_m, depth_m, height_m, name, ... }
    """
    gltf = _build_gltf_cube(features, base_color, classification_field, color_ramp)
    gltf_json = json.dumps(gltf, separators=(",", ":"))
    gltf_bytes = gltf_json.encode("utf-8")
    while len(gltf_bytes) % 8:
        gltf_bytes += b' '
    gltf_len = len(gltf_bytes)

    batch_table = {
        "name": [f.get("name", "") for f in features],
        "height": [f["height_m"] for f in features],
        "color": [f.get("_color", base_color) for f in features],
    }
    batch_json = json.dumps(batch_table, separators=(",", ":"))
    batch_bytes = batch_json.encode("utf-8")
    while len(batch_bytes) % 8:
        batch_bytes += b' '
    batch_len = len(batch_bytes)

    # Feature Table: RTC_CENTER + per-instance position + scale
    # Use the b3dm's RTC_CENTER to shift all positions
    ft = {"BATCH_LENGTH": len(features)}

    # Prepare binary feature table data
    positions = []
    scales = []
    for f in features:
        positions.extend([f["x_offset"], f["y_offset"], f["z_offset"]])
        scales.extend([f["width_m"], f["depth_m"], f["height_m"]])

    ft_binary = struct.pack(f"<{len(features)*3}f", *positions)
    ft_binary += struct.pack(f"<{len(features)*3}f", *scales)

    ft["POSITION"] = {"byteOffset": 0}
    ft["SCALE"] = {"byteOffset": len(features) * 3 * 4}  # 3 floats * 4 bytes

    ft_json = json.dumps(ft, separators=(",", ":"))
    ft_json_bytes = ft_json.encode("utf-8")
    while len(ft_json_bytes) % 8:
        ft_json_bytes += b' '
    ft_json_len = len(ft_json_bytes)

    # b3dm header
    magic = b'b3dm'
    version = 1
    byte_length = 28 + ft_json_len + len(ft_binary) + batch_len + gltf_len
    header = struct.pack("<4s6I", magic, version, byte_length,
                         ft_json_len, len(ft_binary), batch_len, 0)

    result = header + ft_json_bytes + ft_binary + batch_bytes + gltf_bytes
    if progress_cb:
        progress_cb(0.9, "正在序列化 3D 数据...")
    return result


def _latlon_to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple:
    """将经纬度转为以 ref 为原点的局部坐标（米）。"""
    lat_m = (lat - ref_lat) * 111320.0
    lon_m = (lon - ref_lon) * 111320.0 * math.cos(math.radians(ref_lat))
    return lon_m, lat_m


def process_shp_zip(
    zip_path: str,
    output_name: str,
    progress_cb=None,
    height_field: str = "",
    base_color: str = "#68c282",
    opacity: float = 1.0,
    classification_field: str = "",
    color_ramp: str = "greens",
) -> dict:
    """
    SHP zip → 3D Tiles。

    Args:
        height_field: 用户指定的高度字段（空则自动检测）
        base_color: 基础颜色 (#rrggbb)
        opacity: 透明度 0.1-1.0
        classification_field: 分级着色字段（空则纯色）
        color_ramp: 色带名称
    """
    if progress_cb:
        progress_cb(0.0, "正在解压压缩包...")
    logger.info("SHP→3D 开始: height_field=%s, color=%s, opacity=%.1f, classify=%s",
                height_field or 'auto', base_color, opacity, classification_field or 'none')

    output_dir = OUTPUT_ROOT / output_name
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # 1. 解压
    extract_dir = output_dir / "_extract"
    extract_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # 2. 找到 .shp 文件
    shp_files = list(extract_dir.glob("**/*.shp"))
    if not shp_files:
        raise ValueError("压缩包中未找到 .shp 文件")

    shp_path = str(shp_files[0])
    if progress_cb:
        progress_cb(0.1, f"正在解析 Shapefile ({len(shp_files)} 个)...")

    # 3. 读取 Shapefile
    sf = shapefile.Reader(shp_path)
    fields = [f[0] for f in sf.fields[1:]]  # skip deletion flag
    if not height_field:
        height_field = _find_height_field(fields)
    records = sf.records()
    shapes = sf.shapes()
    total = len(records)

    if progress_cb:
        progress_cb(0.15, f"解析完成：{total} 个要素，高度字段: {height_field or '默认'}")

    # 4. 提取建筑物特征
    all_lats, all_lons = [], []
    features = []
    for i, (record, shape) in enumerate(zip(records, shapes)):
        pts = shape.points
        if len(pts) < 3:
            continue

        # 计算多边形中心和边界
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        center_lon = (min(xs) + max(xs)) / 2.0
        center_lat = (min(ys) + max(ys)) / 2.0
        width_m = (max(xs) - min(xs)) * 111320.0 * math.cos(math.radians(center_lat))
        depth_m = (max(ys) - min(ys)) * 111320.0

        height_m = _resolve_height(record, height_field)

        name = ""
        for fname in fields:
            if fname.lower() in ("name", "名称", "building_n", "id"):
                try:
                    name = str(getattr(record, fname, ""))
                except Exception:
                    pass
                break

        features.append({
            "lon": center_lon,
            "lat": center_lat,
            "width_m": max(width_m, 0.5),
            "depth_m": max(depth_m, 0.5),
            "height_m": height_m,
            "name": name,
        })
        all_lats.append(center_lat)
        all_lons.append(center_lon)

        if progress_cb and i % 500 == 0:
            progress_cb(0.15 + 0.35 * (i / total), f"处理要素 {i}/{total}...")

    if not features:
        raise ValueError("未能从 Shapefile 中提取有效建筑物要素")

    # 5. 计算参考中心
    ref_lat = (min(all_lats) + max(all_lats)) / 2.0
    ref_lon = (min(all_lons) + max(all_lons)) / 2.0

    # RTC_CENTER（b3dm 全局偏移）
    rtc_center = [ref_lon, ref_lat, 0.0]

    # 计算局部偏移
    for f in features:
        x, y = _latlon_to_local(f["lat"], f["lon"], ref_lat, ref_lon)
        f["x_offset"] = x
        f["y_offset"] = y
        f["z_offset"] = f["height_m"] / 2.0  # 建筑中心高度

    if progress_cb:
        progress_cb(0.5, f"正在生成 3D 模型 ({len(features)} 栋建筑)...")

    # 6. 计算分类颜色
    if classification_field and features:
        field_vals = [f.get(classification_field, 0) for f in features]
        numeric_vals = []
        for v in field_vals:
            try: numeric_vals.append(float(v))
            except: numeric_vals.append(0)
        if numeric_vals and max(numeric_vals) > min(numeric_vals):
            ramp = COLOR_RAMPS.get(color_ramp, COLOR_RAMPS["greens"])
            vmin, vmax = min(numeric_vals), max(numeric_vals)
            for f, v in zip(features, numeric_vals):
                t = (v - vmin) / (vmax - vmin) if vmax > vmin else 0
                idx = min(int(t * (len(ramp) - 1)), len(ramp) - 1)
                f["_color"] = ramp[idx]

    # 7. 构建 b3dm
    b3dm_bytes = _build_b3dm(features, progress_cb, base_color, classification_field, color_ramp)
    logger.info("b3dm 生成完成: %d 栋建筑, 颜色=%s", len(features), base_color)

    # 7. 写入文件
    b3dm_path = output_dir / "buildings.b3dm"
    with open(b3dm_path, "wb") as f:
        f.write(b3dm_bytes)

    # 8. 创建 tileset.json
    bbox = [min(all_lons), min(all_lats), 0, max(all_lons), max(all_lats), 0]
    tileset = {
        "asset": {"version": "1.0"},
        "geometricError": 500.0,
        "root": {
            "boundingVolume": {
                "region": _compute_region(all_lons, all_lats, features),
            },
            "geometricError": 200.0,
            "refine": "ADD",
            "content": {"uri": "buildings.b3dm"},
        },
    }
    tileset_path = output_dir / "tileset.json"
    with open(tileset_path, "w") as f:
        json.dump(tileset, f, indent=2, ensure_ascii=False)

    # 清理解压目录
    import shutil
    shutil.rmtree(extract_dir, ignore_errors=True)

    if progress_cb:
        progress_cb(1.0, f"完成！共 {len(features)} 栋建筑")

    logger.info("3D Tiles 生成完成: %s (%d 栋建筑)", output_dir, len(features))

    return {
        "feature_count": len(features),
        "output_dir": str(output_dir),
        "tileset_url": f"/api/3d/tiles/{output_name}/tileset.json",
    }


def _compute_region(lons, lats, features):
    """计算 WGS84 region 包围盒 [west, south, east, north, minH, maxH]"""
    max_h = max((f["height_m"] for f in features), default=50)
    return [
        math.radians(min(lons)),
        math.radians(min(lats)),
        math.radians(max(lons)),
        math.radians(max(lats)),
        0,
        max_h,
    ]
