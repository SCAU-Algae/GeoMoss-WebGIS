#!/usr/bin/env python3
"""Import a server-side Shapefile ZIP as a published admin 3D layer."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import shapefile

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.auth import get_auth_db_connection  # noqa: E402
from api.shp_to_3dtiles import _find_height_field, process_shp_zip  # noqa: E402


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def read_zip_preview(zip_path: Path) -> tuple[list[str], int, list[float]]:
    import tempfile
    import zipfile
    import shutil

    tmp_dir = Path(tempfile.mkdtemp(prefix="webgis_offline_3d_"))
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(tmp_dir)
        shp_files = list(tmp_dir.glob("**/*.shp"))
        if not shp_files:
            raise ValueError("ZIP 中未找到 .shp 文件")
        reader = shapefile.Reader(str(shp_files[0]))
        fields = [field[0] for field in reader.fields[1:]]
        bbox = [float(value) for value in getattr(reader, "bbox", [])[:4]] if getattr(reader, "bbox", None) else []
        return fields, len(reader), bbox
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def create_layer_and_job(args, fields: list[str], record_count: int, bbox: list[float]) -> tuple[str, str]:
    layer_id = args.layer_id or uuid.uuid4().hex[:12]
    job_id = args.job_id or uuid.uuid4().hex[:12]
    now = iso_now()
    metadata = {
        "split_strategy": "grid",
        "grid_width_m": args.grid_width,
        "grid_height_m": args.grid_height,
        "tile_batch_size": args.tile_batch_size,
        "tile_lod": "overview-parent-fine",
        "source_mode": "server_file",
        "source_path": str(args.zip_path),
        "fields": fields,
        "source_fields": fields,
        "property_fields": ["name", "height_m", "width_m", "depth_m", "lon", "lat", *fields],
    }

    with get_auth_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO three_d_layers (
                id, name, description, status, source_filename, boundary_dataset_id,
                height_field, classification_field, color_ramp, base_color, opacity,
                feature_count, bbox_json, metadata_json, created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, 'processing', ?, '', ?, ?, ?, ?, ?, ?, ?, ?, 'admin', ?, ?)
            ON CONFLICT(id)
            DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                status = 'processing',
                source_filename = excluded.source_filename,
                height_field = excluded.height_field,
                classification_field = excluded.classification_field,
                color_ramp = excluded.color_ramp,
                base_color = excluded.base_color,
                opacity = excluded.opacity,
                feature_count = excluded.feature_count,
                bbox_json = excluded.bbox_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                layer_id,
                args.name,
                args.description,
                args.zip_path.name,
                args.height_field or _find_height_field(fields) or "",
                args.classification_field,
                args.color_ramp,
                args.base_color,
                args.opacity,
                record_count,
                json_dumps(bbox),
                json_dumps(metadata),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO geodata_processing_jobs (
                job_id, job_type, status, phase, progress, message, layer_id, dataset_id,
                created_by, created_at, updated_at
            )
            VALUES (?, 'server_3d_layer', 'queued', 'queued', 0, ?, ?, '', 'admin', ?, ?)
            ON CONFLICT(job_id)
            DO UPDATE SET
                status = 'queued',
                phase = 'queued',
                progress = 0,
                message = excluded.message,
                layer_id = excluded.layer_id,
                updated_at = excluded.updated_at
            """,
            (job_id, "服务器文件离线导入任务已创建", layer_id, now, now),
        )
        conn.commit()
    return layer_id, job_id


def update_job(job_id: str, **updates) -> None:
    if not updates:
        return
    allowed = {"status", "phase", "progress", "message", "result_json", "error", "finished_at"}
    payload = {key: value for key, value in updates.items() if key in allowed}
    if not payload:
        return
    payload["updated_at"] = iso_now()
    keys = list(payload.keys())
    set_clause = ", ".join(f"{key} = ?" for key in keys)
    values = [payload[key] for key in keys]
    values.append(job_id)
    with get_auth_db_connection() as conn:
        conn.execute(f"UPDATE geodata_processing_jobs SET {set_clause} WHERE job_id = ?", tuple(values))
        conn.commit()


def finish_layer(layer_id: str, result: dict, publish: bool) -> None:
    now = iso_now()
    status = "published" if publish else "ready"
    published_at = now if publish else ""
    with get_auth_db_connection() as conn:
        row = conn.execute("SELECT metadata_json FROM three_d_layers WHERE id = ?", (layer_id,)).fetchone()
        metadata = {}
        if row:
            try:
                metadata = json.loads(dict(row).get("metadata_json") or "{}")
            except Exception:
                metadata = {}
        metadata.update({
            "tile_count": int(result.get("tile_count") or 0),
            "lod_enabled": bool(result.get("lod_enabled")),
        })
        conn.execute(
            """
            UPDATE three_d_layers
            SET status = ?, tileset_url = ?, storage_path = ?, feature_count = ?,
                metadata_json = ?, published_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                str(result.get("tileset_url") or ""),
                str(result.get("output_dir") or ""),
                int(result.get("feature_count") or 0),
                json_dumps(metadata),
                published_at,
                now,
                layer_id,
            ),
        )
        conn.commit()


def mark_layer_error(layer_id: str, error: str) -> None:
    with get_auth_db_connection() as conn:
        conn.execute(
            "UPDATE three_d_layers SET status = 'error', updated_at = ? WHERE id = ?",
            (iso_now(), layer_id),
        )
        conn.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", dest="zip_path", type=Path, required=True)
    parser.add_argument("--name", default="服务器 3D 图层")
    parser.add_argument("--description", default="")
    parser.add_argument("--layer-id", default="")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--grid-width", type=float, default=300.0)
    parser.add_argument("--grid-height", type=float, default=300.0)
    parser.add_argument("--tile-batch-size", type=int, default=1500)
    parser.add_argument("--height-field", default="")
    parser.add_argument("--classification-field", default="")
    parser.add_argument("--base-color", default="#47d7c6")
    parser.add_argument("--opacity", type=float, default=0.9)
    parser.add_argument("--color-ramp", default="cool")
    parser.add_argument("--max-features", type=int, default=0)
    parser.add_argument("--publish", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.zip_path = args.zip_path.expanduser().resolve()
    if not args.zip_path.exists():
        print(f"ZIP 不存在: {args.zip_path}", file=sys.stderr)
        return 2

    fields, record_count, bbox = read_zip_preview(args.zip_path)
    if args.max_features > 0 and record_count > args.max_features:
        print(f"要素数 {record_count} 超过限制 {args.max_features}", file=sys.stderr)
        return 3

    layer_id, job_id = create_layer_and_job(args, fields, record_count, bbox)
    output_name = f"admin_{layer_id}"
    height_field = args.height_field or _find_height_field(fields) or ""

    print(f"layer_id={layer_id}")
    print(f"job_id={job_id}")
    print(f"record_count={record_count}")
    print(f"height_field={height_field or 'default'}")

    def progress(progress: float, message: str) -> None:
        update_job(
            job_id,
            status="running",
            phase="processing",
            progress=max(0.0, min(float(progress or 0.0), 1.0)),
            message=str(message or ""),
        )
        print(f"{progress:.3f} {message}", flush=True)

    try:
        update_job(job_id, status="running", phase="extracting", progress=0.02, message="正在处理服务器本地 3D 源数据...")
        result = process_shp_zip(
            str(args.zip_path),
            output_name,
            progress,
            height_field=height_field,
            base_color=args.base_color,
            opacity=args.opacity,
            classification_field=args.classification_field,
            color_ramp=args.color_ramp,
            max_features=args.max_features,
            tile_batch_size=args.tile_batch_size,
            grid_width_m=args.grid_width,
            grid_height_m=args.grid_height,
        )
        finish_layer(layer_id, result, args.publish)
        update_job(
            job_id,
            status="done",
            phase="done",
            progress=1.0,
            message=f"完成：{result.get('feature_count', 0)} 个要素，{result.get('tile_count', 0)} 个精细瓦片",
            result_json=json_dumps(result),
            finished_at=iso_now(),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        mark_layer_error(layer_id, str(exc)[:300])
        update_job(
            job_id,
            status="error",
            phase="error",
            progress=0,
            message=str(exc)[:300],
            error=str(exc)[:1000],
            finished_at=iso_now(),
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
