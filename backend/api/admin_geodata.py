"""
Admin geodata management.

The public map consumes published 3D layers only. Administrators own the
heavy data lifecycle: boundary datasets, 3D production jobs, publish state,
and deletion.
"""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import shapefile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from api.auth import get_auth_db_connection, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/geodata", tags=["admin-geodata"])

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
GEODATA_ROOT = DATA_ROOT / "admin_geodata"
UPLOAD_ROOT = GEODATA_ROOT / "uploads"
BOUNDARY_ROOT = GEODATA_ROOT / "boundaries"
THREED_ROOT = DATA_ROOT / "3dtiles"
BOUNDARY_COMPONENT_EXTENSIONS = {".shp", ".dbf", ".shx", ".prj", ".cpg"}

for path in (UPLOAD_ROOT, BOUNDARY_ROOT, THREED_ROOT):
    path.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = int(os.getenv("WEBGIS_3D_MAX_UPLOAD_MB", "512")) * 1024 * 1024
MAX_SAFE_FEATURES = int(os.getenv("WEBGIS_3D_MAX_FEATURES", "20000"))
MAX_ADMIN_FEATURES = int(os.getenv("WEBGIS_3D_MAX_ADMIN_FEATURES", "500000"))
DEFAULT_TILE_BATCH_SIZE = int(os.getenv("WEBGIS_3D_TILE_BATCH_SIZE", "1500"))
STAGED_TTL_SECONDS = 60 * 60

_staged_uploads: Dict[str, dict] = {}
_job_tasks: Dict[str, asyncio.Task] = {}
_conversion_lock = asyncio.Lock()


class BoundaryConfirmRequest(BaseModel):
    file_token: str
    name: str = Field(..., min_length=1, max_length=160)
    field_code: str = Field(..., min_length=1, max_length=120)
    field_name: str = Field(..., min_length=1, max_length=120)
    field_level: str = Field(default="", max_length=120)


class ThreeDCreateRequest(BaseModel):
    file_token: str
    name: str = Field(..., min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    height_field: str = Field(default="", max_length=120)
    base_color: str = Field(default="#47d7c6", max_length=24)
    opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    classification_field: str = Field(default="", max_length=120)
    color_ramp: str = Field(default="cool", max_length=40)
    split_strategy: str = Field(default="grid", max_length=40)
    boundary_dataset_id: str = Field(default="", max_length=80)
    grid_width_m: float = Field(default=1000.0, ge=50.0, le=100000.0)
    grid_height_m: float = Field(default=1000.0, ge=50.0, le=100000.0)
    tile_batch_size: int = Field(default=DEFAULT_TILE_BATCH_SIZE, ge=100, le=10000)
    publish_when_done: bool = Field(default=False)


class LayerStatusRequest(BaseModel):
    status: str = Field(..., max_length=40)


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


def _safe_member_path(root: Path, member_name: str) -> Path:
    target = (root / member_name).resolve()
    root_resolved = root.resolve()
    if not str(target).startswith(str(root_resolved)):
        raise ValueError("压缩包包含不安全路径")
    return target


def _safe_extract(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            _safe_member_path(target_dir, member.filename)
        archive.extractall(target_dir)


async def _save_upload(file: UploadFile, prefix: str) -> Path:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 压缩包")

    zip_path = UPLOAD_ROOT / f"{prefix}.zip"
    total = 0
    try:
        with open(zip_path, "wb") as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"压缩包超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB 上限",
                    )
                handle.write(chunk)
    except HTTPException:
        zip_path.unlink(missing_ok=True)
        raise
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="文件保存失败")

    return zip_path


def _safe_upload_name(filename: str) -> str:
    name = Path(str(filename or "")).name.strip()
    if not name:
        name = f"upload_{uuid.uuid4().hex[:8]}"
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".", " ") else "_" for ch in name)[:180]


async def _save_boundary_components(files: List[UploadFile], token: str) -> Path:
    target_dir = UPLOAD_ROOT / f"_boundary_components_{token}"
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    saved_extensions = set()
    component_stems = set()
    saved_count = 0

    try:
        for item in files or []:
            filename = _safe_upload_name(item.filename or "")
            suffix = Path(filename).suffix.lower()
            if suffix not in BOUNDARY_COMPONENT_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"不支持的行政区划文件类型: {suffix or filename}")
            if suffix in saved_extensions:
                raise HTTPException(status_code=400, detail=f"同一套 Shapefile 只能包含一个 {suffix} 文件")

            component_stems.add(Path(filename).stem.lower())

            path = target_dir / filename
            if path.exists():
                stem = path.stem
                path = target_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suffix}"

            with open(path, "wb") as handle:
                while chunk := await item.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"行政区划文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB 上限",
                        )
                    handle.write(chunk)

            saved_extensions.add(suffix)
            saved_count += 1

        required = {".shp", ".dbf", ".shx"}
        missing = sorted(required - saved_extensions)
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"请同时选择完整 Shapefile 组件文件，缺少: {', '.join(missing)}",
            )
        if len(component_stems) > 1:
            raise HTTPException(status_code=400, detail="请选择同一套 Shapefile 组件文件，文件主名必须一致")
        if saved_count <= 0:
            raise HTTPException(status_code=400, detail="请选择行政区划 Shapefile 组件文件")
        return target_dir
    except HTTPException:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="行政区划文件保存失败")


def _preview_shp(zip_path: Path, token: str, purpose: str, max_count: int = 50) -> Dict[str, Any]:
    extract_dir = UPLOAD_ROOT / f"_{purpose}_{token}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        _safe_extract(zip_path, extract_dir)
        shp_files = list(extract_dir.glob("**/*.shp"))
        if not shp_files:
            raise ValueError("压缩包中未找到 .shp 文件")

        shp_path = shp_files[0]
        reader = shapefile.Reader(str(shp_path))
        fields = [field[0] for field in reader.fields[1:]]
        sample_records = []
        bbox = [float(v) for v in getattr(reader, "bbox", [])[:4]] if getattr(reader, "bbox", None) else []

        count = len(reader)
        for record in reader.iterRecords():
            row = {}
            try:
                row = dict(record.as_dict())
            except Exception:
                row = {}
            if len(sample_records) < max_count:
                sample_records.append(row)
            if len(sample_records) >= max_count:
                break

        if purpose == "3d" and MAX_ADMIN_FEATURES > 0 and count > MAX_ADMIN_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"当前数据超过管理员任务安全上限 {MAX_ADMIN_FEATURES} 个要素，请先缩小范围或调高后台上限",
            )

        _staged_uploads[token] = {
            "token": token,
            "purpose": purpose,
            "zip_path": str(zip_path),
            "extract_dir": str(extract_dir),
            "shp_path": str(shp_path),
            "fields": fields,
            "record_count": count,
            "bbox": bbox,
            "source_filename": zip_path.name,
            "created_at": time.monotonic(),
        }

        return {
            "status": "success",
            "file_token": token,
            "fields": fields,
            "record_count": count,
            "bbox": bbox,
            "samples": sample_records,
        }
    except HTTPException:
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"解析失败: {str(exc)}")


def _preview_shp_dir(source_dir: Path, token: str, purpose: str, max_count: int = 50) -> Dict[str, Any]:
    try:
        shp_files = list(source_dir.glob("*.shp"))
        if not shp_files:
            raise ValueError("未找到 .shp 文件")

        shp_path = shp_files[0]
        reader = shapefile.Reader(str(shp_path))
        fields = [field[0] for field in reader.fields[1:]]
        sample_records = []
        bbox = [float(v) for v in getattr(reader, "bbox", [])[:4]] if getattr(reader, "bbox", None) else []

        count = len(reader)
        for record in reader.iterRecords():
            try:
                row = dict(record.as_dict())
            except Exception:
                row = {}
            if len(sample_records) < max_count:
                sample_records.append(row)
            if len(sample_records) >= max_count:
                break

        _staged_uploads[token] = {
            "token": token,
            "purpose": purpose,
            "zip_path": "",
            "extract_dir": str(source_dir),
            "source_dir": str(source_dir),
            "shp_path": str(shp_path),
            "fields": fields,
            "record_count": count,
            "bbox": bbox,
            "source_filename": ",".join(sorted(path.name for path in source_dir.iterdir() if path.is_file())),
            "created_at": time.monotonic(),
        }

        return {
            "status": "success",
            "file_token": token,
            "fields": fields,
            "record_count": count,
            "bbox": bbox,
            "samples": sample_records,
        }
    except HTTPException:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(source_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"解析失败: {str(exc)}")


def _cleanup_staged(staged: dict, keep_zip: bool = False) -> None:
    zip_path = str(staged.get("zip_path") or "")
    if not keep_zip and zip_path:
        Path(zip_path).unlink(missing_ok=True)
    extract_dir = str(staged.get("extract_dir") or "")
    if extract_dir:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _prune_staged_uploads() -> None:
    try:
        now = time.monotonic()
    except RuntimeError:
        now = time.monotonic()

    expired = [
        token
        for token, staged in _staged_uploads.items()
        if now - float(staged.get("created_at", now)) > STAGED_TTL_SECONDS
    ]
    for token in expired:
        staged = _staged_uploads.pop(token, None)
        if staged:
            _cleanup_staged(staged)


def _field_value(properties: dict, field_name: str) -> str:
    if not field_name:
        return ""
    if field_name in properties:
        return str(properties.get(field_name) or "").strip()
    target = field_name.lower()
    for key, value in properties.items():
        if str(key).lower() == target:
            return str(value or "").strip()
    return ""


def _boundary_feature_payload(record: Any, shape: Any, payload: BoundaryConfirmRequest) -> Dict[str, Any]:
    properties = {}
    try:
        properties = dict(record.as_dict())
    except Exception:
        properties = {}

    points = [(float(x), float(y)) for x, y in getattr(shape, "points", [])]
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    else:
        bbox = []

    parts = list(getattr(shape, "parts", []) or [])
    if not parts:
        parts = [0]
    part_ranges = []
    for index, start in enumerate(parts):
        end = parts[index + 1] if index + 1 < len(parts) else len(points)
        part_ranges.append((int(start), int(end)))

    rings = []
    for start, end in part_ranges:
        ring = [[float(x), float(y)] for x, y in points[start:end]]
        if len(ring) >= 4:
            rings.append(ring)

    if len(rings) == 1:
        geometry = {"type": "Polygon", "coordinates": [rings[0]]}
    elif len(rings) > 1:
        geometry = {"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}
    else:
        geometry = {}

    return {
        "code": _field_value(properties, payload.field_code),
        "name": _field_value(properties, payload.field_name),
        "level": _field_value(properties, payload.field_level),
        "bbox": bbox,
        "geometry": geometry,
        "properties": properties,
    }


def _confirm_boundary_sync(staged: dict, payload: BoundaryConfirmRequest, admin_username: str) -> Dict[str, Any]:
    fields = [str(item) for item in staged.get("fields") or []]
    for required in (payload.field_code, payload.field_name):
        if required not in fields:
            raise HTTPException(status_code=400, detail=f"字段不存在: {required}")
    if payload.field_level and payload.field_level not in fields:
        raise HTTPException(status_code=400, detail=f"字段不存在: {payload.field_level}")

    dataset_id = uuid.uuid4().hex[:12]
    now_iso = _iso_now()
    permanent_dir = BOUNDARY_ROOT / dataset_id
    permanent_dir.mkdir(parents=True, exist_ok=True)
    source_zip = Path(str(staged.get("zip_path") or ""))
    source_dir = Path(str(staged.get("source_dir") or staged.get("extract_dir") or ""))
    if source_zip.exists():
        storage_path = permanent_dir / "source.zip"
        shutil.copy2(source_zip, storage_path)
    elif source_dir.exists():
        storage_path = permanent_dir / "source"
        shutil.copytree(source_dir, storage_path, dirs_exist_ok=True)
    else:
        shutil.rmtree(permanent_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="行政区划源文件已失效，请重新上传")

    reader = shapefile.Reader(str(staged["shp_path"]))
    feature_rows = []
    for shape_record in reader.iterShapeRecords():
        item = _boundary_feature_payload(shape_record.record, shape_record.shape, payload)
        if not item["code"] or not item["name"]:
            continue
        feature_rows.append(item)

    if not feature_rows:
        shutil.rmtree(permanent_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="未能读取有效行政区划编码和名称")

    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO admin_boundary_datasets (
                id, name, source_filename, storage_path, field_code, field_name, field_level,
                fields_json, feature_count, bbox_json, status, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?)
            """,
            (
                dataset_id,
                payload.name.strip(),
                str(staged.get("source_filename") or source_zip.name or "shapefile-components"),
                str(storage_path),
                payload.field_code,
                payload.field_name,
                payload.field_level,
                _json_dumps(fields),
                len(feature_rows),
                _json_dumps(staged.get("bbox") or []),
                admin_username,
                now_iso,
                now_iso,
            ),
        )
        for item in feature_rows:
            conn.execute(
                """
                INSERT INTO admin_boundary_features (
                    dataset_id, code, name, level, bbox_json, geometry_json, properties_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, code)
                DO UPDATE SET
                    name = excluded.name,
                    level = excluded.level,
                    bbox_json = excluded.bbox_json,
                    geometry_json = excluded.geometry_json,
                    properties_json = excluded.properties_json
                """,
                (
                    dataset_id,
                    item["code"],
                    item["name"],
                    item["level"],
                    _json_dumps(item["bbox"]),
                    _json_dumps(item["geometry"]),
                    _json_dumps(item["properties"]),
                    now_iso,
                ),
            )
        conn.commit()

    return {"id": dataset_id, "name": payload.name.strip(), "feature_count": len(feature_rows)}


def _list_boundaries_sync() -> List[Dict[str, Any]]:
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, source_filename, field_code, field_name, field_level,
                   fields_json, feature_count, bbox_json, status, created_by, created_at, updated_at
            FROM admin_boundary_datasets
            ORDER BY updated_at DESC
            """
        ).fetchall()

    result = []
    for row in rows:
        item = _row_to_dict(row)
        item["fields"] = _json_loads(item.pop("fields_json", "[]"), [])
        item["bbox"] = _json_loads(item.pop("bbox_json", "[]"), [])
        result.append(item)
    return result


def _get_boundary_regions_sync(dataset_id: str) -> List[Dict[str, Any]]:
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, name, level, bbox_json
            FROM admin_boundary_features
            WHERE dataset_id = ?
            ORDER BY code ASC
            """,
            (dataset_id,),
        ).fetchall()
    return [
        {
            "code": str(dict(row).get("code") or ""),
            "name": str(dict(row).get("name") or ""),
            "level": str(dict(row).get("level") or ""),
            "bbox": _json_loads(dict(row).get("bbox_json"), []),
        }
        for row in rows
    ]


def _has_ready_boundary_sync() -> bool:
    with _db_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM admin_boundary_datasets WHERE status = 'ready'").fetchone()
    return int((_row_to_dict(row).get("cnt") if row else 0) or 0) > 0


def _has_ready_boundary_dataset_sync(dataset_id: str) -> bool:
    dataset_id = str(dataset_id or "").strip()
    if not dataset_id:
        return False
    with _db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM admin_boundary_datasets WHERE id = ? AND status = 'ready'",
            (dataset_id,),
        ).fetchone()
    return int((_row_to_dict(row).get("cnt") if row else 0) or 0) > 0


def _create_job_sync(job_id: str, job_type: str, layer_id: str, dataset_id: str, admin_username: str, message: str) -> None:
    now_iso = _iso_now()
    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO geodata_processing_jobs (
                job_id, job_type, status, phase, progress, message, layer_id, dataset_id,
                created_by, created_at, updated_at
            )
            VALUES (?, ?, 'queued', 'queued', 0, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, job_type, message, layer_id, dataset_id, admin_username, now_iso, now_iso),
        )
        conn.commit()


def _update_job_sync(job_id: str, **updates: Any) -> None:
    if not updates:
        return
    allowed = {
        "status", "phase", "progress", "message", "result_json",
        "error", "cancel_requested", "finished_at",
    }
    keys = [key for key in updates if key in allowed]
    if not keys:
        return
    updates["updated_at"] = _iso_now()
    keys.append("updated_at")
    set_clause = ", ".join(f"{key} = ?" for key in keys)
    values = [updates[key] for key in keys]
    values.append(job_id)
    with _db_connection() as conn:
        conn.execute(f"UPDATE geodata_processing_jobs SET {set_clause} WHERE job_id = ?", tuple(values))
        conn.commit()


def _get_job_sync(job_id: str) -> Optional[Dict[str, Any]]:
    with _db_connection() as conn:
        row = conn.execute(
            """
            SELECT job_id, job_type, status, phase, progress, message, layer_id, dataset_id,
                   result_json, error, cancel_requested, created_by, created_at, updated_at, finished_at
            FROM geodata_processing_jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    if not row:
        return None
    item = _row_to_dict(row)
    item["result"] = _json_loads(item.pop("result_json", "{}"), {})
    return item


def _list_jobs_sync(limit: int = 20) -> List[Dict[str, Any]]:
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT job_id, job_type, status, phase, progress, message, layer_id, dataset_id,
                   result_json, error, cancel_requested, created_by, created_at, updated_at, finished_at
            FROM geodata_processing_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 20), 100)),),
        ).fetchall()
    result = []
    for row in rows:
        item = _row_to_dict(row)
        item["result"] = _json_loads(item.pop("result_json", "{}"), {})
        result.append(item)
    return result


def _insert_layer_sync(layer_id: str, payload: ThreeDCreateRequest, staged: dict, admin_username: str) -> None:
    now_iso = _iso_now()
    metadata = {
        "split_strategy": payload.split_strategy,
        "grid_width_m": payload.grid_width_m,
        "grid_height_m": payload.grid_height_m,
        "tile_batch_size": payload.tile_batch_size,
        "publish_when_done": payload.publish_when_done,
        "fields": [str(item) for item in staged.get("fields") or []],
        "source_fields": [str(item) for item in staged.get("fields") or []],
        "property_fields": [
            "name",
            "height_m",
            "width_m",
            "depth_m",
            "lon",
            "lat",
            *[str(item) for item in staged.get("fields") or []],
        ],
    }
    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO three_d_layers (
                id, name, description, status, source_filename, boundary_dataset_id,
                height_field, classification_field, color_ramp, base_color, opacity,
                feature_count, bbox_json, metadata_json, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, 'processing', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                layer_id,
                payload.name.strip(),
                payload.description.strip(),
                str(staged.get("source_filename") or ""),
                payload.boundary_dataset_id,
                payload.height_field,
                payload.classification_field,
                payload.color_ramp,
                payload.base_color,
                payload.opacity,
                int(staged.get("record_count") or 0),
                _json_dumps(staged.get("bbox") or []),
                _json_dumps(metadata),
                admin_username,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()


def _finish_layer_sync(layer_id: str, result: dict, payload: ThreeDCreateRequest) -> None:
    now_iso = _iso_now()
    status_value = "published" if payload.publish_when_done else "ready"
    published_at = now_iso if payload.publish_when_done else ""
    metadata = {
        "split_strategy": payload.split_strategy,
        "grid_width_m": payload.grid_width_m,
        "grid_height_m": payload.grid_height_m,
        "tile_batch_size": payload.tile_batch_size,
        "tile_count": result.get("tile_count", 0),
        "fields": [],
        "source_fields": [],
        "property_fields": ["name", "height_m", "width_m", "depth_m", "lon", "lat"],
    }
    with _db_connection() as conn:
        previous = conn.execute(
            "SELECT metadata_json FROM three_d_layers WHERE id = ?",
            (layer_id,),
        ).fetchone()
        if previous:
            previous_metadata = _json_loads(dict(previous).get("metadata_json"), {})
            metadata.update(previous_metadata)
            metadata.update({
                "tile_count": result.get("tile_count", 0),
                "split_strategy": payload.split_strategy,
                "grid_width_m": payload.grid_width_m,
                "grid_height_m": payload.grid_height_m,
                "tile_batch_size": payload.tile_batch_size,
            })
        conn.execute(
            """
            UPDATE three_d_layers
            SET status = ?, tileset_url = ?, storage_path = ?, feature_count = ?,
                metadata_json = ?, published_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status_value,
                str(result.get("tileset_url") or ""),
                str(result.get("output_dir") or ""),
                int(result.get("feature_count") or 0),
                _json_dumps(metadata),
                published_at,
                now_iso,
                layer_id,
            ),
        )
        conn.commit()


def _mark_layer_error_sync(layer_id: str, error: str) -> None:
    with _db_connection() as conn:
        conn.execute(
            "UPDATE three_d_layers SET status = 'error', updated_at = ? WHERE id = ?",
            (_iso_now(), layer_id),
        )
        conn.commit()


async def _run_three_d_job(job_id: str, layer_id: str, staged: dict, payload: ThreeDCreateRequest) -> None:
    def _progress(progress: float, message: str) -> None:
        _update_job_sync(
            job_id,
            status="running",
            phase="processing",
            progress=max(0, min(float(progress or 0), 1)),
            message=str(message or ""),
        )

    async with _conversion_lock:
        try:
            from api.shp_to_3dtiles import process_shp_zip

            split_strategy = str(payload.split_strategy or "grid").strip().lower()
            regions = []
            if split_strategy == "admin_boundary":
                regions = await asyncio.to_thread(_get_boundary_regions_sync, payload.boundary_dataset_id)
                if not regions:
                    raise ValueError("所选行政区划数据集没有可用分区")

            _update_job_sync(job_id, status="running", phase="extracting", progress=0.02, message="正在准备后台转换...")

            output_name = f"admin_{layer_id}"
            result = await asyncio.to_thread(
                process_shp_zip,
                staged["zip_path"],
                output_name,
                _progress,
                height_field=payload.height_field,
                base_color=payload.base_color,
                opacity=payload.opacity,
                classification_field=payload.classification_field,
                color_ramp=payload.color_ramp,
                max_features=MAX_ADMIN_FEATURES,
                tile_batch_size=payload.tile_batch_size,
                grid_width_m=payload.grid_width_m if split_strategy == "grid" else 0,
                grid_height_m=payload.grid_height_m if split_strategy == "grid" else 0,
                split_regions=regions if split_strategy == "admin_boundary" else None,
            )
            await asyncio.to_thread(_finish_layer_sync, layer_id, result, payload)
            _update_job_sync(
                job_id,
                status="done",
                phase="done",
                progress=1.0,
                message=f"完成：{result.get('feature_count', 0)} 个要素",
                result_json=_json_dumps(result),
                finished_at=_iso_now(),
            )
        except asyncio.CancelledError:
            _mark_layer_error_sync(layer_id, "任务已取消")
            _update_job_sync(
                job_id,
                status="cancelled",
                phase="cancelled",
                progress=0,
                message="任务已取消",
                finished_at=_iso_now(),
            )
            raise
        except Exception as exc:
            logger.exception("管理员 3D 图层转换失败")
            _mark_layer_error_sync(layer_id, str(exc)[:300])
            _update_job_sync(
                job_id,
                status="error",
                phase="error",
                progress=0,
                message=str(exc)[:300],
                error=str(exc)[:1000],
                finished_at=_iso_now(),
            )
        finally:
            _cleanup_staged(staged)
            _job_tasks.pop(job_id, None)


def _layer_from_row(row: Any) -> Dict[str, Any]:
    item = _row_to_dict(row)
    item["bbox"] = _json_loads(item.pop("bbox_json", "[]"), [])
    item["metadata"] = _json_loads(item.pop("metadata_json", "{}"), {})
    return item


def _list_layers_sync(include_all: bool = True) -> List[Dict[str, Any]]:
    where = "" if include_all else "WHERE status = 'published'"
    with _db_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT id, name, description, status, tileset_url, storage_path, source_filename,
                   boundary_dataset_id, height_field, classification_field, color_ramp, base_color,
                   opacity, feature_count, bbox_json, metadata_json, sort_order, published_at,
                   created_by, created_at, updated_at
            FROM three_d_layers
            {where}
            ORDER BY sort_order ASC, updated_at DESC
            """
        ).fetchall()
    return [_layer_from_row(row) for row in rows]


@router.get("/boundaries")
async def list_boundary_datasets(_session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return {"status": "success", "data": await asyncio.to_thread(_list_boundaries_sync)}


@router.post("/boundaries/preview")
async def preview_boundary_dataset(
    files: List[UploadFile] = File(...),
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    _prune_staged_uploads()
    token = uuid.uuid4().hex[:12]
    source_dir = await _save_boundary_components(files, token)
    return await asyncio.to_thread(_preview_shp_dir, source_dir, token, "boundary")


@router.post("/boundaries/confirm")
async def confirm_boundary_dataset(
    payload: BoundaryConfirmRequest,
    session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    staged = _staged_uploads.pop(payload.file_token, None)
    if not staged or staged.get("purpose") != "boundary":
        raise HTTPException(status_code=400, detail="行政区划文件已过期，请重新上传")
    try:
        data = await asyncio.to_thread(
            _confirm_boundary_sync,
            staged,
            payload,
            str(session.get("username") or "admin"),
        )
        return {"status": "success", "data": data}
    finally:
        _cleanup_staged(staged)


@router.delete("/boundaries/{dataset_id}")
async def delete_boundary_dataset(
    dataset_id: str,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    with _db_connection() as conn:
        row = conn.execute("SELECT storage_path FROM admin_boundary_datasets WHERE id = ?", (dataset_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="行政区划数据集不存在")
        conn.execute("DELETE FROM admin_boundary_features WHERE dataset_id = ?", (dataset_id,))
        conn.execute("DELETE FROM admin_boundary_datasets WHERE id = ?", (dataset_id,))
        conn.commit()
    shutil.rmtree(BOUNDARY_ROOT / dataset_id, ignore_errors=True)
    return {"status": "success"}


@router.get("/3d/layers")
async def list_admin_3d_layers(_session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return {"status": "success", "data": await asyncio.to_thread(_list_layers_sync, True)}


@router.post("/3d/preview")
async def preview_three_d_source(
    file: UploadFile = File(...),
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    _prune_staged_uploads()
    token = uuid.uuid4().hex[:12]
    zip_path = await _save_upload(file, f"3d_{token}")
    preview = await asyncio.to_thread(_preview_shp, zip_path, token, "3d")
    from api.shp_to_3dtiles import _find_height_field
    preview["suggested_height_field"] = _find_height_field(preview.get("fields") or [])
    preview["split_modes"] = [
        {"value": "grid", "label": "网格切分"},
        {"value": "admin_boundary", "label": "行政区划切分"},
    ]
    return preview


@router.post("/3d/layers")
async def create_three_d_layer(
    payload: ThreeDCreateRequest,
    session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    staged = _staged_uploads.pop(payload.file_token, None)
    if not staged or staged.get("purpose") != "3d":
        raise HTTPException(status_code=400, detail="3D 源文件已过期，请重新上传")

    split_strategy = str(payload.split_strategy or "grid").strip().lower()
    if split_strategy not in {"grid", "admin_boundary"}:
        _cleanup_staged(staged)
        raise HTTPException(status_code=400, detail="切分策略只能是 grid 或 admin_boundary")

    if split_strategy == "admin_boundary":
        if not payload.boundary_dataset_id:
            _cleanup_staged(staged)
            raise HTTPException(status_code=400, detail="行政区划切分必须选择行政区划数据集")
        if not await asyncio.to_thread(_has_ready_boundary_sync):
            _cleanup_staged(staged)
            raise HTTPException(status_code=400, detail="请先上传并确认行政区划数据集")
        if not await asyncio.to_thread(_has_ready_boundary_dataset_sync, payload.boundary_dataset_id):
            _cleanup_staged(staged)
            raise HTTPException(status_code=400, detail="所选行政区划数据集不存在或未就绪")

    if split_strategy == "grid" and (payload.grid_width_m <= 0 or payload.grid_height_m <= 0):
        _cleanup_staged(staged)
        raise HTTPException(status_code=400, detail="网格切分必须设置有效长宽")

    layer_id = uuid.uuid4().hex[:12]
    job_id = uuid.uuid4().hex[:12]
    admin_username = str(session.get("username") or "admin")

    await asyncio.to_thread(_insert_layer_sync, layer_id, payload, staged, admin_username)
    await asyncio.to_thread(
        _create_job_sync,
        job_id,
        "three_d_layer",
        layer_id,
        payload.boundary_dataset_id,
        admin_username,
        "后台转换任务已创建",
    )
    _job_tasks[job_id] = asyncio.create_task(_run_three_d_job(job_id, layer_id, staged, payload))
    return {"status": "success", "data": {"job_id": job_id, "layer_id": layer_id}}


@router.post("/3d/layers/{layer_id}/status")
async def update_three_d_layer_status(
    layer_id: str,
    payload: LayerStatusRequest,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    status_value = str(payload.status or "").strip().lower()
    if status_value not in {"published", "ready", "archived"}:
        raise HTTPException(status_code=400, detail="状态只能是 published、ready 或 archived")
    now_iso = _iso_now()
    published_at = now_iso if status_value == "published" else ""
    with _db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE three_d_layers
            SET status = ?, published_at = ?, updated_at = ?
            WHERE id = ? AND status != 'processing'
            """,
            (status_value, published_at, now_iso, layer_id),
        )
        conn.commit()
        if int(cursor.rowcount or 0) <= 0:
            raise HTTPException(status_code=404, detail="图层不存在或正在处理")
    return {"status": "success"}


@router.delete("/3d/layers/{layer_id}")
async def delete_three_d_layer(
    layer_id: str,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    with _db_connection() as conn:
        row = conn.execute("SELECT storage_path FROM three_d_layers WHERE id = ?", (layer_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="3D 图层不存在")
        storage_path = str(_row_to_dict(row).get("storage_path") or "")
        conn.execute("DELETE FROM three_d_layers WHERE id = ?", (layer_id,))
        conn.commit()

    if storage_path:
        shutil.rmtree(storage_path, ignore_errors=True)
    else:
        shutil.rmtree(THREED_ROOT / f"admin_{layer_id}", ignore_errors=True)
    return {"status": "success"}


@router.get("/jobs")
async def list_processing_jobs(
    limit: int = 20,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    return {"status": "success", "data": await asyncio.to_thread(_list_jobs_sync, limit)}


@router.get("/jobs/{job_id}")
async def get_processing_job(job_id: str, _session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    job = await asyncio.to_thread(_get_job_sync, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"status": "success", "data": job}


@router.post("/jobs/{job_id}/cancel")
async def cancel_processing_job(job_id: str, _session: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    task = _job_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
    await asyncio.to_thread(
        _update_job_sync,
        job_id,
        cancel_requested=1,
        status="cancelled",
        phase="cancelled",
        progress=0,
        message="任务已取消",
        finished_at=_iso_now(),
    )
    return {"status": "success"}
