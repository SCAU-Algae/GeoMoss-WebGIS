import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .geometry import bbox_of_geometry, center_of_bbox
from .scoring import clamp_score


DEFAULT_WATER_DIR = Path(os.getenv("WEBGIS_WATER_VECTOR_DIR", "/root/project_test/全国范围的水系数据"))
DEFAULT_WATER_PATH = os.getenv("WEBGIS_WATER_VECTOR_PATH", "")
DEFAULT_WATER_LINE_PATH = os.getenv("WEBGIS_WATER_LINE_VECTOR_PATH", "")
SEARCH_MULTIPLIERS = (1.5, 4, 10, 24)
MAX_CANDIDATES = int(os.getenv("WEBGIS_WATER_MAX_CANDIDATES", "220"))
WATER_FIELD_CANDIDATES = ("name", "NAME", "名称", "fclass_cn", "fclass", "type", "width")


def _missing_status() -> Dict[str, Any]:
    return {
        "available": False,
        "is_placeholder": True,
        "status": "missing",
        "nearest_distance_m": None,
        "direction": "未识别",
        "intersects": False,
        "score": 60,
        "message": "未接入真实水系数据，得水分按中性占位展示，并从综合评分确定性权重中排除。",
        "source": "",
        "candidate_count": 0,
        "nearest_name": "",
        "nearest_type": "",
    }


def resolve_water_paths() -> Dict[str, Any]:
    polygon_path = Path(DEFAULT_WATER_PATH) if DEFAULT_WATER_PATH else None
    line_path = Path(DEFAULT_WATER_LINE_PATH) if DEFAULT_WATER_LINE_PATH else None

    if polygon_path and polygon_path.exists():
        pass
    elif DEFAULT_WATER_DIR.exists():
        polygon_path = _pick_shp(DEFAULT_WATER_DIR, ["面", "polygon", "area", "湖", "水系"])
    else:
        polygon_path = None

    if line_path and line_path.exists():
        pass
    elif DEFAULT_WATER_DIR.exists():
        line_path = _pick_shp(DEFAULT_WATER_DIR, ["线", "line", "river", "stream", "河"])
    else:
        line_path = None

    return {
        "polygon": polygon_path,
        "line": line_path,
        "directory": DEFAULT_WATER_DIR,
    }


def _pick_shp(directory: Path, keywords: List[str]) -> Optional[Path]:
    candidates = sorted(directory.glob("*.shp"))
    if not candidates:
        return None

    def rank(path: Path) -> Tuple[int, int, str]:
        name = path.name.lower()
        keyword_score = sum(1 for keyword in keywords if keyword.lower() in name)
        return (-keyword_score, len(name), name)

    return sorted(candidates, key=rank)[0]


def _direction_name(origin_lon: float, origin_lat: float, target_lon: float, target_lat: float) -> str:
    dx = target_lon - origin_lon
    dy = target_lat - origin_lat
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return "内部"
    degree = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    names = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return names[int(((degree + 22.5) % 360) / 45)]


def _intersects_bbox(a: Iterable[float], b: Iterable[float]) -> bool:
    a_values = list(a or [])[:4]
    b_values = list(b or [])[:4]
    if len(a_values) < 4 or len(b_values) < 4:
        return False
    a0, a1, a2, a3 = [float(v) for v in a_values]
    b0, b1, b2, b3 = [float(v) for v in b_values]
    return not (b2 < a0 or b0 > a2 or b3 < a1 or b1 > a3)


def _expand_bbox(bbox: List[float], multiplier: float) -> Tuple[float, float, float, float]:
    minx, miny, maxx, maxy = [float(v) for v in bbox[:4]]
    width = max(maxx - minx, 0.01)
    height = max(maxy - miny, 0.01)
    return (
        minx - width * multiplier,
        miny - height * multiplier,
        maxx + width * multiplier,
        maxy + height * multiplier,
    )


def _meters_per_degree(center_lat: float) -> Tuple[float, float]:
    return 111_320 * max(math.cos(math.radians(center_lat)), 0.01), 110_540


def _project(lon: float, lat: float, origin_lon: float, origin_lat: float, meters_per_lon: float, meters_per_lat: float) -> Tuple[float, float]:
    return (float(lon) - origin_lon) * meters_per_lon, (float(lat) - origin_lat) * meters_per_lat


def _point_segment_distance_m(point: Tuple[float, float], start: Tuple[float, float], end: Tuple[float, float]) -> float:
    px, py = point
    ax, ay = start
    bx, by = end
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom <= 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denom))
    nx = ax + t * dx
    ny = ay + t * dy
    return math.hypot(px - nx, py - ny)


def _iter_shape_parts(points: List[Any], parts: List[int]) -> Iterable[List[Any]]:
    boundaries = list(parts or [0]) + [len(points)]
    for idx in range(len(boundaries) - 1):
        start = int(boundaries[idx])
        end = int(boundaries[idx + 1])
        if end - start >= 2:
            yield points[start:end]


def _point_to_shape_distance_m(
    lon: float,
    lat: float,
    shape_obj: Any,
    origin_lon: float,
    origin_lat: float,
    meters_per_lon: float,
    meters_per_lat: float,
) -> float:
    point = _project(lon, lat, origin_lon, origin_lat, meters_per_lon, meters_per_lat)
    best = float("inf")
    points = getattr(shape_obj, "points", []) or []
    parts = getattr(shape_obj, "parts", [0]) or [0]
    for part in _iter_shape_parts(points, parts):
        previous = part[0]
        prev_projected = _project(previous[0], previous[1], origin_lon, origin_lat, meters_per_lon, meters_per_lat)
        for current in part[1:]:
            current_projected = _project(current[0], current[1], origin_lon, origin_lat, meters_per_lon, meters_per_lat)
            best = min(best, _point_segment_distance_m(point, prev_projected, current_projected))
            previous = current
            prev_projected = current_projected
    return best


def _shape_centroid(shape_obj: Any) -> Tuple[float, float]:
    points = getattr(shape_obj, "points", []) or []
    if not points:
        return 0.0, 0.0
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _record_value(record: Any, fields: List[str], names: List[str]) -> str:
    data = {}
    try:
        data = record.as_dict()
    except Exception:
        try:
            data = {fields[index]: record[index] for index in range(min(len(fields), len(record)))}
        except Exception:
            data = {}

    lower_map = {str(key).lower(): value for key, value in data.items()}
    for name in names:
        value = lower_map.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


@lru_cache(maxsize=4)
def _reader(path: str) -> Any:
    import shapefile

    return shapefile.Reader(path)


def _scan_water_candidates(
    path: Path,
    search_bbox: Tuple[float, float, float, float],
    limit: int,
    fields: List[str],
) -> Tuple[List[Tuple[Any, Any]], int, bool]:
    reader = _reader(str(path))
    selected_fields = [field for field in WATER_FIELD_CANDIDATES if field in fields]
    rows: List[Tuple[Any, Any]] = []
    scanned = 0
    used_native_bbox = True
    try:
        iterator = reader.iterShapeRecords(fields=selected_fields or None, bbox=search_bbox)
    except TypeError:
        iterator = reader.iterShapeRecords()
        used_native_bbox = False

    try:
        for shape_record in iterator:
            scanned += 1
            shape_obj = shape_record.shape
            if used_native_bbox or _intersects_bbox(getattr(shape_obj, "bbox", []), search_bbox):
                rows.append((shape_obj, shape_record.record))
                if len(rows) >= limit:
                    break
    except TypeError:
        # Older pyshp versions may accept the bbox keyword but fail when the
        # generator is consumed. Fall back to a sequential scan in that case.
        rows = []
        scanned = 0
        used_native_bbox = False
        for shape_record in reader.iterShapeRecords():
            scanned += 1
            shape_obj = shape_record.shape
            if _intersects_bbox(getattr(shape_obj, "bbox", []), search_bbox):
                rows.append((shape_obj, shape_record.record))
                if len(rows) >= limit:
                    break
    return rows, scanned, used_native_bbox


def _field_names(path: Path) -> List[str]:
    reader = _reader(str(path))
    return [str(field[0]) for field in reader.fields[1:]]


def _analyze_with_pyshp(geometry: Dict[str, Any], water_path: Path) -> Dict[str, Any]:
    minx, miny, maxx, maxy = bbox_of_geometry(geometry)
    center_lon, center_lat = center_of_bbox([minx, miny, maxx, maxy])
    meters_per_lon, meters_per_lat = _meters_per_degree(center_lat)
    fields = _field_names(water_path)

    candidates: List[Tuple[Any, Any]] = []
    used_bbox: Tuple[float, float, float, float] = (minx, miny, maxx, maxy)
    scanned = 0
    native_bbox_filter = False
    for multiplier in SEARCH_MULTIPLIERS:
        used_bbox = _expand_bbox([minx, miny, maxx, maxy], multiplier)
        candidates, scanned, native_bbox_filter = _scan_water_candidates(water_path, used_bbox, MAX_CANDIDATES, fields)
        if candidates:
            break

    if not candidates:
        return {
            **_missing_status(),
            "available": True,
            "is_placeholder": False,
            "status": "ready",
            "score": 52,
            "source": str(water_path),
            "search_bbox": [round(v, 6) for v in used_bbox],
            "scanned_count": scanned,
            "native_bbox_filter": native_bbox_filter,
            "message": "已接入全国水系数据，但研究范围周边未检索到水体，得水关系偏弱。",
        }

    best: Optional[Dict[str, Any]] = None
    intersects = False
    for shape_obj, record in candidates:
        shape_bbox = getattr(shape_obj, "bbox", [])
        if _intersects_bbox(shape_bbox, [minx, miny, maxx, maxy]):
            intersects = True
        distance_m = _point_to_shape_distance_m(
            center_lon,
            center_lat,
            shape_obj,
            center_lon,
            center_lat,
            meters_per_lon,
            meters_per_lat,
        )
        centroid_lon, centroid_lat = _shape_centroid(shape_obj)
        row = {
            "distance_m": distance_m,
            "centroid_lon": centroid_lon,
            "centroid_lat": centroid_lat,
            "name": _record_value(record, fields, ["name", "NAME", "名称"]),
            "type": _record_value(record, fields, ["fclass_cn", "fclass", "type"]),
        }
        if best is None or row["distance_m"] < best["distance_m"]:
            best = row

    best = best or {}
    nearest_distance_m = float(best.get("distance_m") or 0)
    direction = _direction_name(center_lon, center_lat, float(best.get("centroid_lon") or center_lon), float(best.get("centroid_lat") or center_lat))
    nearest_name = str(best.get("name") or "").strip()
    nearest_type = str(best.get("type") or "").strip()
    water_label = nearest_name or nearest_type or "最近水体"

    if intersects or nearest_distance_m <= 80:
        score = 62
        message = f"研究范围与{water_label}存在相交或贴邻关系，需优先核验洪水位、退让红线与排水安全。"
    elif nearest_distance_m <= 1000:
        score = 86
        message = f"{water_label}位于{direction}侧约 {nearest_distance_m:.0f} m，距离适中，具备较好的亲水环境条件。"
    elif nearest_distance_m <= 3000:
        score = 76
        message = f"{water_label}位于{direction}侧约 {nearest_distance_m:.0f} m，可作为周边水系环境参考。"
    else:
        score = clamp_score(66 - min((nearest_distance_m - 3000) / 1000, 16))
        message = f"{water_label}位于{direction}侧约 {nearest_distance_m:.0f} m，得水关系较弱。"

    return {
        "available": True,
        "is_placeholder": False,
        "status": "ready",
        "nearest_distance_m": round(nearest_distance_m, 1),
        "direction": direction,
        "intersects": bool(intersects),
        "score": int(score),
        "message": message,
        "source": str(water_path),
        "candidate_count": len(candidates),
        "scanned_count": scanned,
        "native_bbox_filter": native_bbox_filter,
        "nearest_name": nearest_name,
        "nearest_type": nearest_type,
    }


def analyze_water(geometry: Dict[str, Any], water_path: Path | None = None) -> Dict[str, Any]:
    paths = resolve_water_paths()
    selected_path = water_path or paths.get("polygon") or paths.get("line")
    if not selected_path or not Path(selected_path).exists():
        return _missing_status()

    try:
        return _analyze_with_pyshp(geometry, Path(selected_path))
    except Exception as exc:
        data = _missing_status()
        data.update({
            "status": "error",
            "source": str(selected_path),
            "message": f"水系分析失败：{str(exc)[:160]}。得水分按中性占位展示。",
        })
        return data
