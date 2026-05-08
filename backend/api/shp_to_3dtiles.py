"""
SHP -> 3D Tiles conversion.

The converter intentionally keeps the first implementation conservative:
each polygon feature is represented as an extruded rectangular massing model.
It produces a standards-compliant b3dm tile whose payload is a GLB, so Cesium
can load the result without relying on non-standard b3dm instancing fields.
"""

import json
import logging
import math
import shutil
import struct
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import shapefile

try:
    from pyproj import CRS, Transformer
except Exception:  # pragma: no cover - pyproj is declared in dependencies.
    CRS = None
    Transformer = None

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "data" / "3dtiles"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

HEIGHT_FIELD_CANDIDATES = [
    "height", "Height", "HEIGHT", "楼层", "层数", "floor", "FLOOR",
    "building_h", "BUILDING_H", "elevation", "h", "H", "高度", "hgt",
    "storeys", "stories", "levels", "floors", "标高",
]
DEFAULT_FLOOR_HEIGHT = 3.0
DEFAULT_MIN_HEIGHT = 5.0
GRID_LOD_PARENT_FACTOR = 8
MAX_OPEN_BUCKET_HANDLES = 128

COLOR_RAMPS = {
    "greens": ["#edf8e9", "#bae4b3", "#74c476", "#31a354", "#006d2c"],
    "blues": ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
    "reds": ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
    "warm": ["#ffffcc", "#ffeda0", "#fed976", "#feb24c", "#f03b20"],
    "cool": ["#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c"],
}

ProgressCallback = Optional[Callable[[float, str], None]]


def _find_height_field(fields: list[str]) -> Optional[str]:
    """Find a likely building-height field in a Shapefile schema."""
    for candidate in HEIGHT_FIELD_CANDIDATES:
        for field in fields:
            if field.lower() == candidate.lower():
                return field
    return None


def _get_property(properties: dict[str, Any], field_name: str) -> Any:
    if not field_name:
        return None
    if field_name in properties:
        return properties[field_name]

    target = field_name.lower()
    for key, value in properties.items():
        if str(key).lower() == target:
            return value
    return None


def _resolve_height(properties: dict[str, Any], height_field: Optional[str]) -> float:
    """Extract building height in meters. Floor-count fields are converted to meters."""
    raw = _get_property(properties, height_field or "")
    if raw is None:
        return DEFAULT_MIN_HEIGHT

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_MIN_HEIGHT

    if value <= 0:
        return DEFAULT_MIN_HEIGHT

    field_lower = str(height_field or "").lower()
    is_floor_count = any(
        keyword in field_lower
        for keyword in ("层", "floor", "storey", "story", "stories", "level")
    )
    if is_floor_count and value <= 200:
        return value * DEFAULT_FLOOR_HEIGHT
    if value > 500:
        return DEFAULT_MIN_HEIGHT
    return value


def _hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[float, float, float, float]:
    raw = str(hex_color or "#68c282").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        raw = "68c282"
    try:
        rgb = tuple(int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        rgb = (0x68 / 255.0, 0xC2 / 255.0, 0x82 / 255.0)
    return (*rgb, min(max(float(opacity or 1.0), 0.1), 1.0))


def _record_to_dict(record: Any) -> dict[str, Any]:
    try:
        return dict(record.as_dict())
    except Exception:
        return {}


def _safe_extract_zip(zip_path: str, extract_dir: Path) -> None:
    root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = (extract_dir / member.filename).resolve()
            if not str(target).startswith(str(root)):
                raise ValueError("压缩包包含不安全的路径")
        archive.extractall(extract_dir)


def _build_transformer(shp_path: Path):
    if CRS is None or Transformer is None:
        return None

    prj_path = shp_path.with_suffix(".prj")
    if not prj_path.exists():
        return None

    try:
        crs = CRS.from_wkt(prj_path.read_text(encoding="utf-8", errors="ignore"))
        target = CRS.from_epsg(4326)
        if crs == target:
            return None
        return Transformer.from_crs(crs, target, always_xy=True)
    except Exception as exc:
        logger.warning("无法解析 Shapefile PRJ，按经纬度读取: %s", exc)
        return None


def _looks_like_lonlat(points: list[tuple[float, float]]) -> bool:
    if not points:
        return False
    sample = points[: min(len(points), 64)]
    return all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in sample)


def _transform_points(points: list[tuple[float, float]], transformer) -> list[tuple[float, float]]:
    if transformer is None:
        if not _looks_like_lonlat(points):
            raise ValueError("SHP 坐标看起来不是经纬度，请在压缩包中包含可解析的 .prj 文件")
        return points

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    lons, lats = transformer.transform(xs, ys)
    return list(zip(lons, lats))


def _latlon_to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    lat_m = (lat - ref_lat) * 111320.0
    lon_m = (lon - ref_lon) * 111320.0 * math.cos(math.radians(ref_lat))
    return lon_m, lat_m


def _ecef_from_lonlat_height(lon: float, lat: float, height: float = 0.0) -> tuple[float, float, float]:
    semi_major = 6378137.0
    eccentricity_sq = 6.69437999014e-3
    lon_rad = math.radians(lon)
    lat_rad = math.radians(lat)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    radius = semi_major / math.sqrt(1.0 - eccentricity_sq * sin_lat * sin_lat)

    x = (radius + height) * cos_lat * math.cos(lon_rad)
    y = (radius + height) * cos_lat * math.sin(lon_rad)
    z = (radius * (1.0 - eccentricity_sq) + height) * sin_lat
    return x, y, z


def _east_north_up_transform(ref_lon: float, ref_lat: float) -> list[float]:
    lon = math.radians(ref_lon)
    lat = math.radians(ref_lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    center = _ecef_from_lonlat_height(ref_lon, ref_lat, 0.0)

    east = (-sin_lon, cos_lon, 0.0)
    north = (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat)
    up = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)

    return [
        east[0], east[1], east[2], 0.0,
        north[0], north[1], north[2], 0.0,
        up[0], up[1], up[2], 0.0,
        center[0], center[1], center[2], 1.0,
    ]


def _matrix_from_tiles_transform(transform: list[float]) -> np.ndarray:
    return np.asarray(transform, dtype=np.float64).reshape((4, 4), order="F")


def _matrix_to_tiles_transform(matrix: np.ndarray) -> list[float]:
    return np.asarray(matrix, dtype=np.float64).reshape(16, order="F").tolist()


def _relative_tiles_transform(parent_transform: list[float], child_transform: list[float]) -> list[float]:
    parent = _matrix_from_tiles_transform(parent_transform)
    child = _matrix_from_tiles_transform(child_transform)
    return _matrix_to_tiles_transform(np.linalg.inv(parent) @ child)


def _feature_name(fields: list[str], properties: dict[str, Any], fallback: int) -> str:
    for field in fields:
        if str(field).lower() in ("name", "名称", "building_n", "id"):
            value = _get_property(properties, field)
            if value not in (None, ""):
                return str(value)
    return f"building-{fallback + 1}"


def _assign_colors(
    features: list[dict[str, Any]],
    base_color: str,
    opacity: float,
    classification_field: str = "",
    color_ramp: str = "greens",
) -> None:
    base = _hex_to_rgba(base_color, opacity)
    for feature in features:
        feature["rgba"] = base

    if not classification_field:
        return

    values: list[float] = []
    for feature in features:
        try:
            values.append(float(_get_property(feature["properties"], classification_field) or 0))
        except (TypeError, ValueError):
            values.append(0.0)

    if not values or max(values) <= min(values):
        return

    ramp = COLOR_RAMPS.get(color_ramp, COLOR_RAMPS["greens"])
    vmin = min(values)
    vmax = max(values)
    for feature, value in zip(features, values):
        ratio = (value - vmin) / (vmax - vmin)
        idx = min(int(ratio * (len(ramp) - 1)), len(ramp) - 1)
        feature["rgba"] = _hex_to_rgba(ramp[idx], opacity)


def _box_geometry(feature: dict[str, Any]) -> tuple[list[float], list[float]]:
    x = feature["x_offset"]
    y = feature["y_offset"]
    width = max(float(feature["width_m"]), 0.5)
    depth = max(float(feature["depth_m"]), 0.5)
    height = max(float(feature["height_m"]), 0.5)

    x0 = x - width / 2.0
    x1 = x + width / 2.0
    y0 = y - depth / 2.0
    y1 = y + depth / 2.0
    z0 = 0.0
    z1 = height

    faces = [
        ((0.0, 0.0, -1.0), [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]),
        ((0.0, 0.0, 1.0), [(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)]),
        ((0.0, -1.0, 0.0), [(x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)]),
        ((1.0, 0.0, 0.0), [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)]),
        ((0.0, 1.0, 0.0), [(x1, y1, z0), (x1, y1, z1), (x0, y1, z1), (x0, y1, z0)]),
        ((-1.0, 0.0, 0.0), [(x0, y1, z0), (x0, y1, z1), (x0, y0, z1), (x0, y0, z0)]),
    ]

    positions: list[float] = []
    normals: list[float] = []
    for normal, vertices in faces:
        for vertex in vertices:
            positions.extend(vertex)
            normals.extend(normal)
    return positions, normals


def _pad_bytes(data: bytes, multiple: int, fill: bytes = b" ") -> bytes:
    remainder = len(data) % multiple
    if remainder == 0:
        return data
    return data + fill * (multiple - remainder)


def _append_buffer(buffer: bytearray, data: bytes, alignment: int = 4) -> tuple[int, int]:
    while len(buffer) % alignment:
        buffer.append(0)
    offset = len(buffer)
    buffer.extend(data)
    return offset, len(data)


def _build_glb(features: list[dict[str, Any]]) -> bytes:
    positions: list[float] = []
    normals: list[float] = []
    colors: list[float] = []
    batch_ids: list[int] = []
    indices: list[int] = []

    for batch_id, feature in enumerate(features):
        feature_positions, feature_normals = _box_geometry(feature)
        vertex_start = len(positions) // 3
        vertex_count = len(feature_positions) // 3
        positions.extend(feature_positions)
        normals.extend(feature_normals)
        for _ in range(vertex_count):
            colors.extend(feature["rgba"])
            batch_ids.append(batch_id)
        for face_start in range(0, vertex_count, 4):
            base = vertex_start + face_start
            indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])

    position_array = np.asarray(positions, dtype=np.float32)
    normal_array = np.asarray(normals, dtype=np.float32)
    color_array = np.asarray(colors, dtype=np.float32)
    batch_id_dtype = np.uint32 if len(features) > 65535 else np.uint16
    batch_id_array = np.asarray(batch_ids, dtype=batch_id_dtype)
    index_dtype = np.uint32 if (len(positions) // 3) > 65535 else np.uint16
    index_array = np.asarray(indices, dtype=index_dtype)

    binary = bytearray()
    pos_offset, pos_length = _append_buffer(binary, position_array.tobytes())
    normal_offset, normal_length = _append_buffer(binary, normal_array.tobytes())
    color_offset, color_length = _append_buffer(binary, color_array.tobytes())
    batch_id_offset, batch_id_length = _append_buffer(binary, batch_id_array.tobytes())
    index_offset, index_length = _append_buffer(binary, index_array.tobytes())
    while len(binary) % 4:
        binary.append(0)

    position_values = position_array.reshape((-1, 3))
    position_min = position_values.min(axis=0).tolist()
    position_max = position_values.max(axis=0).tolist()
    index_component_type = 5125 if index_dtype == np.uint32 else 5123
    batch_id_component_type = 5125 if batch_id_dtype == np.uint32 else 5123

    gltf = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "materials": [{
            "pbrMetallicRoughness": {
                "baseColorFactor": [1.0, 1.0, 1.0, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.85,
            },
            "doubleSided": True,
            "alphaMode": "BLEND",
        }],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2, "_BATCHID": 3},
                "indices": 4,
                "material": 0,
                "mode": 4,
            }]
        }],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": pos_offset, "byteLength": pos_length, "target": 34962},
            {"buffer": 0, "byteOffset": normal_offset, "byteLength": normal_length, "target": 34962},
            {"buffer": 0, "byteOffset": color_offset, "byteLength": color_length, "target": 34962},
            {"buffer": 0, "byteOffset": batch_id_offset, "byteLength": batch_id_length, "target": 34962},
            {"buffer": 0, "byteOffset": index_offset, "byteLength": index_length, "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(position_array) // 3,
                "type": "VEC3",
                "min": position_min,
                "max": position_max,
            },
            {"bufferView": 1, "componentType": 5126, "count": len(normal_array) // 3, "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(color_array) // 4, "type": "VEC4"},
            {
                "bufferView": 3,
                "componentType": batch_id_component_type,
                "count": len(batch_id_array),
                "type": "SCALAR",
                "min": [0],
                "max": [max(len(features) - 1, 0)],
            },
            {
                "bufferView": 4,
                "componentType": index_component_type,
                "count": len(index_array),
                "type": "SCALAR",
                "min": [int(index_array.min())],
                "max": [int(index_array.max())],
            },
        ],
    }

    json_chunk = _pad_bytes(json.dumps(gltf, separators=(",", ":")).encode("utf-8"), 4, b" ")
    bin_chunk = _pad_bytes(bytes(binary), 4, b"\x00")
    total_length = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)

    return b"".join([
        struct.pack("<4sII", b"glTF", 2, total_length),
        struct.pack("<II", len(json_chunk), 0x4E4F534A),
        json_chunk,
        struct.pack("<II", len(bin_chunk), 0x004E4942),
        bin_chunk,
    ])


def _batch_table_json(features: list[dict[str, Any]]) -> bytes:
    rows = []
    source_fields: list[str] = []
    for index, feature in enumerate(features):
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        for key in props.keys():
            if key not in source_fields:
                source_fields.append(str(key))
        rows.append({
            "batch_id": index,
            "name": str(feature.get("name") or props.get("name") or props.get("名称") or f"building-{index + 1}"),
            "height_m": round(float(feature.get("height_m") or 0.0), 3),
            "width_m": round(float(feature.get("width_m") or 0.0), 3),
            "depth_m": round(float(feature.get("depth_m") or 0.0), 3),
            "lon": round(float(feature.get("lon") or 0.0), 8),
            "lat": round(float(feature.get("lat") or 0.0), 8),
            "source": props,
        })

    batch_table = {
        "batch_id": [row["batch_id"] for row in rows],
        "name": [row["name"] for row in rows],
        "height_m": [row["height_m"] for row in rows],
        "width_m": [row["width_m"] for row in rows],
        "depth_m": [row["depth_m"] for row in rows],
        "lon": [row["lon"] for row in rows],
        "lat": [row["lat"] for row in rows],
        "source": [row["source"] for row in rows],
    }
    for field in source_fields:
        values = [row["source"].get(field) if isinstance(row["source"], dict) else None for row in rows]
        if any(value is not None for value in values):
            batch_table[field] = values
    return json.dumps(batch_table, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")


def _build_b3dm(features: list[dict[str, Any]]) -> bytes:
    glb = _build_glb(features)
    feature_table_json = _pad_bytes(json.dumps({"BATCH_LENGTH": len(features)}, separators=(",", ":")).encode("utf-8"), 8, b" ")
    batch_table_json = _pad_bytes(_batch_table_json(features), 8, b" ")
    byte_length = 28 + len(feature_table_json) + len(batch_table_json) + len(glb)
    header = struct.pack(
        "<4s6I",
        b"b3dm",
        1,
        byte_length,
        len(feature_table_json),
        0,
        len(batch_table_json),
        0,
    )

    return header + feature_table_json + batch_table_json + glb


def _compute_local_box(features: list[dict[str, Any]]) -> list[float]:
    min_x = min(feature["x_offset"] - feature["width_m"] / 2.0 for feature in features)
    max_x = max(feature["x_offset"] + feature["width_m"] / 2.0 for feature in features)
    min_y = min(feature["y_offset"] - feature["depth_m"] / 2.0 for feature in features)
    max_y = max(feature["y_offset"] + feature["depth_m"] / 2.0 for feature in features)
    min_z = 0.0
    max_z = max(feature["height_m"] for feature in features)

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = (min_z + max_z) / 2.0
    half_x = max((max_x - min_x) / 2.0, 1.0)
    half_y = max((max_y - min_y) / 2.0, 1.0)
    half_z = max((max_z - min_z) / 2.0, 1.0)

    return [
        center_x, center_y, center_z,
        half_x, 0.0, 0.0,
        0.0, half_y, 0.0,
        0.0, 0.0, half_z,
    ]


def _compute_region(features: list[dict[str, Any]]) -> list[float]:
    min_lon = min(feature["lon"] for feature in features)
    max_lon = max(feature["lon"] for feature in features)
    min_lat = min(feature["lat"] for feature in features)
    max_lat = max(feature["lat"] for feature in features)
    max_height = max(float(feature.get("height_m") or 0.0) for feature in features)
    return [
        math.radians(min_lon),
        math.radians(min_lat),
        math.radians(max_lon),
        math.radians(max_lat),
        0.0,
        max(max_height, 1.0),
    ]


def _compute_region_from_bounds(bounds: dict[str, float]) -> list[float]:
    return [
        math.radians(bounds["min_lon"]),
        math.radians(bounds["min_lat"]),
        math.radians(bounds["max_lon"]),
        math.radians(bounds["max_lat"]),
        0.0,
        max(float(bounds.get("max_height") or 1.0), 1.0),
    ]


def _update_bounds(bounds: Optional[dict[str, float]], feature: dict[str, Any]) -> dict[str, float]:
    lon = float(feature["lon"])
    lat = float(feature["lat"])
    height = float(feature.get("height_m") or 0.0)
    if bounds is None:
        return {
            "min_lon": lon,
            "min_lat": lat,
            "max_lon": lon,
            "max_lat": lat,
            "max_height": max(height, 1.0),
        }
    bounds["min_lon"] = min(bounds["min_lon"], lon)
    bounds["min_lat"] = min(bounds["min_lat"], lat)
    bounds["max_lon"] = max(bounds["max_lon"], lon)
    bounds["max_lat"] = max(bounds["max_lat"], lat)
    bounds["max_height"] = max(bounds["max_height"], height)
    return bounds


def _lonlat_bbox_from_reader(reader: Any, transformer: Any) -> tuple[float, float, float, float]:
    raw_bbox = [float(v) for v in getattr(reader, "bbox", [])[:4]]
    if len(raw_bbox) < 4:
        return (-180.0, -90.0, 180.0, 90.0)
    min_x, min_y, max_x, max_y = raw_bbox
    points = [(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)]
    transformed = _transform_points(points, transformer)
    lons = [point[0] for point in transformed]
    lats = [point[1] for point in transformed]
    return min(lons), min(lats), max(lons), max(lats)


def _write_feature_line(handle: Any, feature: dict[str, Any]) -> None:
    handle.write(json.dumps(feature, ensure_ascii=False, default=str, separators=(",", ":")) + "\n")


def _close_bucket_handle(handles: OrderedDict[str, Any], safe_key: str) -> None:
    handle = handles.pop(safe_key, None)
    if handle is None:
        return
    try:
        handle.close()
    except Exception:
        pass


def _close_bucket_handles(handles: OrderedDict[str, Any]) -> None:
    for safe_key in list(handles.keys()):
        _close_bucket_handle(handles, safe_key)


def _get_bucket_handle(handles: OrderedDict[str, Any], bucket_paths: dict[str, Path], safe_key: str) -> Any:
    handle = handles.get(safe_key)
    if handle is not None:
        handles.move_to_end(safe_key)
        return handle

    while len(handles) >= MAX_OPEN_BUCKET_HANDLES:
        oldest_key = next(iter(handles))
        _close_bucket_handle(handles, oldest_key)

    handle = open(bucket_paths[safe_key], "a", encoding="utf-8")
    handles[safe_key] = handle
    return handle


def _iter_feature_chunks(path: Path, chunk_size: int) -> Any:
    batch: list[dict[str, Any]] = []
    safe_chunk_size = max(int(chunk_size or 0), 1)
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            batch.append(json.loads(raw))
            if len(batch) >= safe_chunk_size:
                yield batch
                batch = []
    if batch:
        yield batch


def _shape_record_to_feature(
    shape_record: Any,
    fields: list[str],
    transformer: Any,
    height_field: str,
    index: int,
) -> Optional[dict[str, Any]]:
    record = shape_record.record
    shape = shape_record.shape
    raw_points = [(float(x), float(y)) for x, y in shape.points]
    if len(raw_points) < 3:
        return None

    points = _transform_points(raw_points, transformer)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    center_lon = (min(xs) + max(xs)) / 2.0
    center_lat = (min(ys) + max(ys)) / 2.0
    width_m = abs((max(xs) - min(xs)) * 111320.0 * math.cos(math.radians(center_lat)))
    depth_m = abs((max(ys) - min(ys)) * 111320.0)

    properties = _record_to_dict(record)
    return {
        "lon": center_lon,
        "lat": center_lat,
        "width_m": max(width_m, 0.5),
        "depth_m": max(depth_m, 0.5),
        "height_m": _resolve_height(properties, height_field),
        "name": _feature_name(fields, properties, index),
        "properties": properties,
    }


def _prepare_local_offsets(features: list[dict[str, Any]]) -> tuple[float, float]:
    ref_lon = (min(feature["lon"] for feature in features) + max(feature["lon"] for feature in features)) / 2.0
    ref_lat = (min(feature["lat"] for feature in features) + max(feature["lat"] for feature in features)) / 2.0

    for feature in features:
        x_offset, y_offset = _latlon_to_local(feature["lat"], feature["lon"], ref_lat, ref_lon)
        feature["x_offset"] = x_offset
        feature["y_offset"] = y_offset

    return ref_lon, ref_lat


def _build_tile_child(
    features: list[dict[str, Any]],
    output_dir: Path,
    tile_name: str,
    base_color: str,
    opacity: float,
    classification_field: str,
    color_ramp: str,
    progress_cb: ProgressCallback = None,
) -> dict[str, Any]:
    ref_lon, ref_lat = _prepare_local_offsets(features)
    _assign_colors(features, base_color, opacity, classification_field, color_ramp)
    (output_dir / tile_name).write_bytes(_build_b3dm(features))
    return {
        "transform": _east_north_up_transform(ref_lon, ref_lat),
        "boundingVolume": {"box": _compute_local_box(features)},
        "geometricError": 0.0,
        "refine": "ADD",
        "content": {"uri": tile_name},
    }


def _init_grid_bucket_stats(gx: int, gy: int) -> dict[str, Any]:
    return {
        "gx": int(gx),
        "gy": int(gy),
        "count": 0,
        "sum_height": 0.0,
        "max_height": 0.0,
        "min_lon": 180.0,
        "min_lat": 90.0,
        "max_lon": -180.0,
        "max_lat": -90.0,
    }


def _update_grid_bucket_stats(stats: dict[str, Any], feature: dict[str, Any]) -> None:
    lon = float(feature["lon"])
    lat = float(feature["lat"])
    height = max(float(feature.get("height_m") or 0.0), DEFAULT_MIN_HEIGHT)
    stats["count"] += 1
    stats["sum_height"] += height
    stats["max_height"] = max(float(stats.get("max_height") or 0.0), height)
    stats["min_lon"] = min(float(stats["min_lon"]), lon)
    stats["min_lat"] = min(float(stats["min_lat"]), lat)
    stats["max_lon"] = max(float(stats["max_lon"]), lon)
    stats["max_lat"] = max(float(stats["max_lat"]), lat)


def _grid_stats_to_coarse_feature(stats: dict[str, Any], grid_w: float, grid_h: float, name_prefix: str) -> dict[str, Any]:
    min_lon = float(stats["min_lon"])
    max_lon = float(stats["max_lon"])
    min_lat = float(stats["min_lat"])
    max_lat = float(stats["max_lat"])
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    width_m = abs((max_lon - min_lon) * 111320.0 * math.cos(math.radians(center_lat)))
    depth_m = abs((max_lat - min_lat) * 111320.0)
    count = max(int(stats.get("count") or 0), 1)
    avg_height = float(stats.get("sum_height") or 0.0) / count
    return {
        "lon": center_lon,
        "lat": center_lat,
        "width_m": max(width_m, grid_w * 0.72, 8.0),
        "depth_m": max(depth_m, grid_h * 0.72, 8.0),
        "height_m": max(avg_height, DEFAULT_MIN_HEIGHT),
        "name": f"{name_prefix}_{stats.get('gx')}_{stats.get('gy')}",
        "properties": {
            "count": count,
            "avg_height": avg_height,
            "max_height": float(stats.get("max_height") or 0.0),
        },
    }


def process_shp_zip(
    zip_path: str,
    output_name: str,
    progress_cb: ProgressCallback = None,
    height_field: str = "",
    base_color: str = "#68c282",
    opacity: float = 1.0,
    classification_field: str = "",
    color_ramp: str = "greens",
    max_features: int = 20000,
    tile_batch_size: int = 0,
    grid_width_m: float = 0.0,
    grid_height_m: float = 0.0,
    split_regions: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Convert a zipped polygon Shapefile to a simple b3dm 3D Tileset."""
    if progress_cb:
        progress_cb(0.0, "正在解压压缩包...")

    logger.info(
        "SHP -> 3D start: height_field=%s, color=%s, opacity=%.1f, classify=%s",
        height_field or "auto",
        base_color,
        opacity,
        classification_field or "none",
    )

    output_dir = OUTPUT_ROOT / output_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    extract_dir = output_dir / "_extract"
    extract_dir.mkdir(exist_ok=True)

    try:
        _safe_extract_zip(zip_path, extract_dir)

        shp_files = list(extract_dir.glob("**/*.shp"))
        if not shp_files:
            raise ValueError("压缩包中未找到 .shp 文件")

        shp_path = shp_files[0]
        if progress_cb:
            progress_cb(0.1, f"正在解析 Shapefile ({len(shp_files)} 个)...")

        reader = shapefile.Reader(str(shp_path))
        fields = [field[0] for field in reader.fields[1:]]
        if not height_field:
            height_field = _find_height_field(fields) or ""

        total = len(reader)
        if max_features > 0 and total > max_features:
            raise ValueError(
                f"当前 SHP 包含 {total} 个要素，超过服务器安全上限 {max_features}。"
                "请降低数据范围，或提高后台任务安全上限后再转换。"
            )
        transformer = _build_transformer(shp_path)

        if progress_cb:
            progress_cb(0.15, f"解析完成：{total} 个要素，高度字段: {height_field or '默认'}")

        safe_batch_size = int(tile_batch_size or 0)
        use_grid_split = float(grid_width_m or 0) > 0 and float(grid_height_m or 0) > 0

        safe_regions = [
            region
            for region in (split_regions or [])
            if isinstance(region, dict)
            and isinstance(region.get("bbox"), list)
            and len(region.get("bbox") or []) >= 4
        ]

        if safe_regions or use_grid_split:
            bucket_root = output_dir / "_buckets"
            bucket_root.mkdir(exist_ok=True)
            handles: OrderedDict[str, Any] = OrderedDict()
            bucket_paths: dict[str, Path] = {}
            bucket_sizes: dict[str, int] = {}
            grid_bucket_stats: dict[str, dict[str, Any]] = {}
            bucket_grid_indices: dict[str, tuple[int, int]] = {}
            bounds: Optional[dict[str, float]] = None
            valid_count = 0

            min_lon, min_lat, max_lon, max_lat = _lonlat_bbox_from_reader(reader, transformer)
            ref_lon = (min_lon + max_lon) / 2.0
            ref_lat = (min_lat + max_lat) / 2.0
            origin_x, origin_y = _latlon_to_local(min_lat, min_lon, ref_lat, ref_lon)
            grid_w = max(float(grid_width_m or 0), 1.0)
            grid_h = max(float(grid_height_m or 0), 1.0)

            def bucket_key_for_feature(feature: dict[str, Any]) -> tuple[str, Optional[tuple[int, int]]]:
                if safe_regions:
                    for region in safe_regions:
                        r_min_lon, r_min_lat, r_max_lon, r_max_lat = [float(v) for v in region["bbox"][:4]]
                        if r_min_lon <= feature["lon"] <= r_max_lon and r_min_lat <= feature["lat"] <= r_max_lat:
                            return f"admin_{str(region.get('code') or 'unknown')}", None
                    return "admin_unmatched", None

                x_offset, y_offset = _latlon_to_local(feature["lat"], feature["lon"], ref_lat, ref_lon)
                gx = math.floor((x_offset - origin_x) / grid_w)
                gy = math.floor((y_offset - origin_y) / grid_h)
                return f"grid_{gx}_{gy}", (int(gx), int(gy))

            try:
                for index, shape_record in enumerate(reader.iterShapeRecords()):
                    feature = _shape_record_to_feature(shape_record, fields, transformer, height_field, index)
                    if feature is None:
                        continue

                    key, grid_index = bucket_key_for_feature(feature)
                    safe_key = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in key)[:120]
                    if safe_key not in bucket_paths:
                        bucket_paths[safe_key] = bucket_root / f"{safe_key}.jsonl"
                        bucket_sizes[safe_key] = 0
                        if grid_index is not None:
                            bucket_grid_indices[safe_key] = grid_index
                            grid_bucket_stats[safe_key] = _init_grid_bucket_stats(grid_index[0], grid_index[1])
                    _write_feature_line(_get_bucket_handle(handles, bucket_paths, safe_key), feature)
                    bucket_sizes[safe_key] += 1
                    if safe_key in grid_bucket_stats:
                        _update_grid_bucket_stats(grid_bucket_stats[safe_key], feature)
                    bounds = _update_bounds(bounds, feature)
                    valid_count += 1

                    if progress_cb and index % 2000 == 0:
                        progress_cb(0.15 + 0.25 * (index / max(total, 1)), f"正在生成临时切分桶 {index}/{total}...")
            finally:
                _close_bucket_handles(handles)

            if not bucket_paths or bounds is None:
                raise ValueError("未能从 Shapefile 中提取有效建筑物要素")

            children: list[dict[str, Any]] = []
            bucket_items = sorted(bucket_paths.items())
            chunk_size = safe_batch_size if safe_batch_size > 0 else max(valid_count, 1)

            fine_children_by_parent: dict[tuple[int, int], list[dict[str, Any]]] = {}
            coarse_features_by_parent: dict[tuple[int, int], list[dict[str, Any]]] = {}
            generated_fine_tiles = 0

            for bucket_index, (safe_key, path) in enumerate(bucket_items, start=1):
                grid_index = bucket_grid_indices.get(safe_key)
                parent_key = None
                if grid_index is not None:
                    parent_key = (
                        math.floor(grid_index[0] / GRID_LOD_PARENT_FACTOR),
                        math.floor(grid_index[1] / GRID_LOD_PARENT_FACTOR),
                    )
                    coarse_features_by_parent.setdefault(parent_key, []).append(
                        _grid_stats_to_coarse_feature(grid_bucket_stats[safe_key], grid_w, grid_h, "grid_overview")
                    )

                for chunk in _iter_feature_chunks(path, chunk_size):
                    tile_name = f"{'admin' if safe_regions else 'grid'}_{generated_fine_tiles + 1:04d}.b3dm"
                    if progress_cb:
                        progress_cb(
                            0.45 + 0.45 * (bucket_index / max(len(bucket_items), 1)),
                            f"正在生成瓦片 {bucket_index}/{len(bucket_items)}...",
                        )
                    fine_child = _build_tile_child(
                        chunk,
                        output_dir,
                        tile_name,
                        base_color,
                        opacity,
                        classification_field,
                        color_ramp,
                        progress_cb,
                    )
                    generated_fine_tiles += 1
                    if parent_key is None:
                        children.append(fine_child)
                    else:
                        fine_children_by_parent.setdefault(parent_key, []).append(fine_child)

            lod_tile_count = 0
            if use_grid_split and fine_children_by_parent:
                parent_children: list[dict[str, Any]] = []
                overview_features: list[dict[str, Any]] = []
                for parent_index, parent_key in enumerate(sorted(fine_children_by_parent), start=1):
                    coarse_features = coarse_features_by_parent.get(parent_key) or []
                    if not coarse_features:
                        continue
                    parent_tile_name = f"grid_lod_parent_{parent_index:04d}.b3dm"
                    parent_child = _build_tile_child(
                        coarse_features,
                        output_dir,
                        parent_tile_name,
                        base_color,
                        min(float(opacity or 1.0), 0.62),
                        "",
                        color_ramp,
                        progress_cb,
                    )
                    parent_transform = parent_child.get("transform")
                    lod_tile_count += 1
                    nested_children = []
                    for fine_child in fine_children_by_parent[parent_key]:
                        fine_transform = fine_child.get("transform")
                        if parent_transform and fine_transform:
                            fine_child = {
                                **fine_child,
                                "transform": _relative_tiles_transform(parent_transform, fine_transform),
                            }
                        nested_children.append(fine_child)
                    parent_child["geometricError"] = max(grid_w, grid_h) * GRID_LOD_PARENT_FACTOR * 0.75
                    parent_child["refine"] = "REPLACE"
                    parent_child["children"] = nested_children
                    parent_children.append(parent_child)

                    parent_stats = _init_grid_bucket_stats(parent_key[0], parent_key[1])
                    for feature in coarse_features:
                        _update_grid_bucket_stats(parent_stats, feature)
                    overview_features.append(
                        _grid_stats_to_coarse_feature(
                            parent_stats,
                            grid_w * GRID_LOD_PARENT_FACTOR,
                            grid_h * GRID_LOD_PARENT_FACTOR,
                            "city_overview",
                        )
                    )

                if overview_features and parent_children:
                    overview_child = _build_tile_child(
                        overview_features,
                        output_dir,
                        "city_overview.b3dm",
                        base_color,
                        min(float(opacity or 1.0), 0.44),
                        "",
                        color_ramp,
                        progress_cb,
                    )
                    overview_transform = overview_child.get("transform")
                    lod_tile_count += 1
                    normalized_parent_children = []
                    for parent_child in parent_children:
                        parent_transform = parent_child.get("transform")
                        if overview_transform and parent_transform:
                            parent_child = {
                                **parent_child,
                                "transform": _relative_tiles_transform(overview_transform, parent_transform),
                            }
                        normalized_parent_children.append(parent_child)
                    overview_child["geometricError"] = max(grid_w, grid_h) * GRID_LOD_PARENT_FACTOR * 2.0
                    overview_child["refine"] = "REPLACE"
                    overview_child["children"] = normalized_parent_children
                    children = [overview_child]
                else:
                    children = parent_children

            total_tile_count = generated_fine_tiles + lod_tile_count
            if not total_tile_count:
                total_tile_count = len(children)
            root_geometric_error = max(1000.0, max(grid_w, grid_h) * GRID_LOD_PARENT_FACTOR * 4.0) if use_grid_split else 1000.0

            tileset = {
                "asset": {"version": "1.0", "gltfUpAxis": "Z"},
                "geometricError": root_geometric_error,
                "root": {
                    "boundingVolume": {"region": _compute_region_from_bounds(bounds)},
                    "geometricError": root_geometric_error,
                    "refine": "REPLACE" if use_grid_split else "ADD",
                    "children": children,
                },
            }
            (output_dir / "tileset.json").write_text(json.dumps(tileset, indent=2, ensure_ascii=False), encoding="utf-8")
            shutil.rmtree(bucket_root, ignore_errors=True)

            if progress_cb:
                label = "区划" if safe_regions else "网格"
                progress_cb(1.0, f"完成！共 {valid_count} 栋建筑，{total_tile_count} 个{label}瓦片")

            logger.info("Split 3D Tiles generated: %s (%d features, %d tiles)", output_dir, valid_count, total_tile_count)
            return {
                "feature_count": valid_count,
                "output_dir": str(output_dir),
                "tileset_url": f"/api/3d/tiles/{output_name}/tileset.json",
                "tile_count": total_tile_count,
                "lod_enabled": bool(use_grid_split and fine_children_by_parent),
            }

        if not use_grid_split and safe_batch_size > 0 and total > safe_batch_size:
            children: list[dict[str, Any]] = []
            batch: list[dict[str, Any]] = []
            all_features_for_region: list[dict[str, Any]] = []
            valid_count = 0

            for index, shape_record in enumerate(reader.iterShapeRecords()):
                feature = _shape_record_to_feature(shape_record, fields, transformer, height_field, index)
                if feature is None:
                    continue

                batch.append(feature)
                all_features_for_region.append({
                    "lon": feature["lon"],
                    "lat": feature["lat"],
                    "height_m": feature["height_m"],
                })
                valid_count += 1

                if len(batch) >= safe_batch_size:
                    tile_name = f"buildings_{len(children) + 1:04d}.b3dm"
                    if progress_cb:
                        progress_cb(0.15 + 0.75 * (index / max(total, 1)), f"生成分块 {len(children) + 1}...")
                    children.append(_build_tile_child(
                        batch,
                        output_dir,
                        tile_name,
                        base_color,
                        opacity,
                        classification_field,
                        color_ramp,
                        progress_cb,
                    ))
                    batch = []

            if batch:
                tile_name = f"buildings_{len(children) + 1:04d}.b3dm"
                children.append(_build_tile_child(
                    batch,
                    output_dir,
                    tile_name,
                    base_color,
                    opacity,
                    classification_field,
                    color_ramp,
                    progress_cb,
                ))

            if not children or not all_features_for_region:
                raise ValueError("未能从 Shapefile 中提取有效建筑物要素")

            tileset = {
                "asset": {"version": "1.0", "gltfUpAxis": "Z"},
                "geometricError": 1000.0,
                "root": {
                    "boundingVolume": {"region": _compute_region(all_features_for_region)},
                    "geometricError": 500.0,
                    "refine": "ADD",
                    "children": children,
                },
            }
            (output_dir / "tileset.json").write_text(json.dumps(tileset, indent=2, ensure_ascii=False), encoding="utf-8")

            if progress_cb:
                progress_cb(1.0, f"完成！共 {valid_count} 栋建筑，{len(children)} 个分块")

            logger.info("Chunked 3D Tiles generated: %s (%d features, %d tiles)", output_dir, valid_count, len(children))
            return {
                "feature_count": valid_count,
                "output_dir": str(output_dir),
                "tileset_url": f"/api/3d/tiles/{output_name}/tileset.json",
                "tile_count": len(children),
            }

        features: list[dict[str, Any]] = []
        all_lats: list[float] = []
        all_lons: list[float] = []

        for index, shape_record in enumerate(reader.iterShapeRecords()):
            feature = _shape_record_to_feature(shape_record, fields, transformer, height_field, index)
            if feature is None:
                continue
            features.append(feature)
            all_lons.append(feature["lon"])
            all_lats.append(feature["lat"])

            if progress_cb and index % 500 == 0:
                progress_cb(0.15 + 0.35 * (index / max(total, 1)), f"处理要素 {index}/{total}...")

        if not features:
            raise ValueError("未能从 Shapefile 中提取有效建筑物要素")

        ref_lon, ref_lat = _prepare_local_offsets(features)

        _assign_colors(features, base_color, opacity, classification_field, color_ramp)

        if progress_cb:
            progress_cb(0.5, f"正在生成 3D 模型 ({len(features)} 栋建筑)...")

        b3dm_path = output_dir / "buildings.b3dm"
        b3dm_path.write_bytes(_build_b3dm(features))

        tileset = {
            "asset": {"version": "1.0", "gltfUpAxis": "Z"},
            "geometricError": 500.0,
            "root": {
                "transform": _east_north_up_transform(ref_lon, ref_lat),
                "boundingVolume": {"box": _compute_local_box(features)},
                "geometricError": 0.0,
                "refine": "ADD",
                "content": {"uri": "buildings.b3dm"},
            },
        }
        (output_dir / "tileset.json").write_text(json.dumps(tileset, indent=2, ensure_ascii=False), encoding="utf-8")

        if progress_cb:
            progress_cb(1.0, f"完成！共 {len(features)} 栋建筑")

        logger.info("3D Tiles generated: %s (%d features)", output_dir, len(features))
        return {
            "feature_count": len(features),
            "output_dir": str(output_dir),
            "tileset_url": f"/api/3d/tiles/{output_name}/tileset.json",
            "tile_count": 1,
        }
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
