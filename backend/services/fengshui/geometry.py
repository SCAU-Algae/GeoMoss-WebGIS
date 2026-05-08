import math
from typing import Any, Dict, Iterable, List, Tuple


EARTH_RADIUS_M = 6_371_008.8


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def make_circle_feature(lon: float, lat: float, radius_m: float, segments: int = 96) -> Dict[str, Any]:
    lon = float(lon)
    lat = float(lat)
    radius_m = clamp(float(radius_m), 20.0, 200_000.0)
    lat_rad = math.radians(lat)
    angular = radius_m / EARTH_RADIUS_M
    coords: List[List[float]] = []

    for index in range(max(24, int(segments))):
        bearing = 2 * math.pi * index / max(24, int(segments))
        point_lat = math.asin(
            math.sin(lat_rad) * math.cos(angular)
            + math.cos(lat_rad) * math.sin(angular) * math.cos(bearing)
        )
        point_lon = math.radians(lon) + math.atan2(
            math.sin(bearing) * math.sin(angular) * math.cos(lat_rad),
            math.cos(angular) - math.sin(lat_rad) * math.sin(point_lat),
        )
        coords.append([math.degrees(point_lon), math.degrees(point_lat)])

    coords.append(coords[0])
    return {
        "type": "Feature",
        "properties": {"shape": "circle", "radius_m": radius_m, "center": [lon, lat]},
        "geometry": {"type": "Polygon", "coordinates": [coords]},
    }


def geometry_from_feature(feature: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(feature, dict):
        raise ValueError("研究范围必须是 GeoJSON Feature 或 Geometry")
    if feature.get("type") == "Feature":
        geometry = feature.get("geometry") or {}
    else:
        geometry = feature
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("风水分析第一阶段仅支持面状研究范围")
    return geometry


def iter_lonlat_points(geometry: Dict[str, Any]) -> Iterable[Tuple[float, float]]:
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geom_type == "Polygon":
        for ring in coordinates:
            for point in ring:
                if len(point) >= 2:
                    yield float(point[0]), float(point[1])
    elif geom_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                for point in ring:
                    if len(point) >= 2:
                        yield float(point[0]), float(point[1])


def bbox_of_geometry(geometry: Dict[str, Any]) -> List[float]:
    points = list(iter_lonlat_points(geometry))
    if not points:
        raise ValueError("研究范围没有有效坐标")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def center_of_bbox(bbox: List[float]) -> Tuple[float, float]:
    return ((float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2)


def approximate_area_m2(geometry: Dict[str, Any]) -> float:
    bbox = bbox_of_geometry(geometry)
    center_lat = (bbox[1] + bbox[3]) / 2
    meters_per_lon = 111_320 * max(math.cos(math.radians(center_lat)), 0.01)
    meters_per_lat = 110_540

    def ring_area(ring: List[Any]) -> float:
        if len(ring) < 4:
            return 0.0
        area = 0.0
        origin_lon, origin_lat = float(ring[0][0]), float(ring[0][1])
        projected: List[Tuple[float, float]] = []
        for point in ring:
            x = (float(point[0]) - origin_lon) * meters_per_lon
            y = (float(point[1]) - origin_lat) * meters_per_lat
            projected.append((x, y))
        for index in range(len(projected) - 1):
            x1, y1 = projected[index]
            x2, y2 = projected[index + 1]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2

    geom_type = geometry.get("type")
    total = 0.0
    if geom_type == "Polygon":
        rings = geometry.get("coordinates") or []
        if rings:
            total += ring_area(rings[0])
            for hole in rings[1:]:
                total -= ring_area(hole)
    elif geom_type == "MultiPolygon":
        for polygon in geometry.get("coordinates") or []:
            if polygon:
                total += ring_area(polygon[0])
                for hole in polygon[1:]:
                    total -= ring_area(hole)
    return max(0.0, total)


def build_area_info(geometry: Dict[str, Any]) -> Dict[str, Any]:
    bbox = bbox_of_geometry(geometry)
    center_lon, center_lat = center_of_bbox(bbox)
    return {
        "bbox": [round(float(value), 7) for value in bbox],
        "center_lon": round(center_lon, 7),
        "center_lat": round(center_lat, 7),
        "area_m2": round(approximate_area_m2(geometry), 2),
        "vertex_count": sum(1 for _ in iter_lonlat_points(geometry)),
    }
