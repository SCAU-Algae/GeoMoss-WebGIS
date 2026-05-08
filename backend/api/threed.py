"""
3D 数据处理 API：SHP 压缩包上传 → 自动生成 3D Tiles。
"""

import asyncio
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.auth import get_auth_db_connection, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/3d", tags=["3d-processing"])

# 临时存储：上传的 SHP 文件（等待用户确认配置后再转换）
_staged_files: Dict[str, dict] = {}
_job_tasks: Dict[str, asyncio.Task] = {}
_conversion_lock = asyncio.Lock()

MAX_PREVIEW_ZIP_BYTES = int(os.getenv("WEBGIS_3D_MAX_UPLOAD_MB", "512")) * 1024 * 1024
MAX_SAFE_FEATURES = int(os.getenv("WEBGIS_3D_MAX_FEATURES", "20000"))
STAGED_TTL_SECONDS = 60 * 60


class ShpConvertOptions(BaseModel):
    file_token: str = Field(...)
    height_field: str = Field(default="")
    base_color: str = Field(default="#68c282")
    opacity: float = Field(default=1.0, ge=0.1, le=1.0)
    classification_field: str = Field(default="")
    color_ramp: str = Field(default="greens")  # greens / blues / reds / warm / cool

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "data" / "3dtiles"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 进程状态缓存（简单的内存字典，正式环境可用 Redis）
_jobs: Dict[str, dict] = {}


class JobStatus(BaseModel):
    job_id: str = Field(...)
    phase: str = Field(default="idle")  # idle / queued / extracting / parsing / generating / done / error / cancelled
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = Field(default="")
    feature_count: int = Field(default=0)
    tileset_url: str = Field(default="")


def _db_connection():
    return get_auth_db_connection()


def _json_loads(text: Any, fallback: Any) -> Any:
    try:
        return json.loads(text) if text else fallback
    except Exception:
        return fallback


def _public_layer_from_row(row: Any) -> dict:
    item = dict(row)
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or "3D 图层"),
        "description": str(item.get("description") or ""),
        "status": str(item.get("status") or ""),
        "tileset_url": str(item.get("tileset_url") or ""),
        "feature_count": int(item.get("feature_count") or 0),
        "bbox": _json_loads(item.get("bbox_json"), []),
        "metadata": _json_loads(item.get("metadata_json"), {}),
        "published_at": str(item.get("published_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
    }


@router.get("/layers/published")
async def list_published_3d_layers():
    """普通用户只读取管理员发布后的 3D 图层。"""
    with _db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, description, status, tileset_url, feature_count,
                   bbox_json, metadata_json, published_at, updated_at
            FROM three_d_layers
            WHERE status = 'published' AND tileset_url != ''
            ORDER BY sort_order ASC, updated_at DESC
            """
        ).fetchall()

    layers = [_public_layer_from_row(row) for row in rows]
    return {
        "status": "success",
        "data": layers,
        "available": bool(layers),
    }


def _update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


def _job_status(job_id: str, phase: str, progress: float, message: str, **kwargs) -> dict:
    return {
        "job_id": job_id,
        "phase": phase,
        "progress": progress,
        "message": message,
        "feature_count": kwargs.get("feature_count", 0),
        "tileset_url": kwargs.get("tileset_url", ""),
    }


def _cleanup_staged(staged: dict) -> None:
    zip_path = staged.get("zip_path")
    extract_dir = staged.get("extract_dir")
    if zip_path:
        Path(zip_path).unlink(missing_ok=True)
    if extract_dir:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _prune_staged_files() -> None:
    now = asyncio.get_running_loop().time()
    expired = [
        token
        for token, staged in _staged_files.items()
        if now - float(staged.get("created_at", now)) > STAGED_TTL_SECONDS
    ]
    for token in expired:
        staged = _staged_files.pop(token, None)
        if staged:
            _cleanup_staged(staged)


@router.post("/preview-shp")
async def preview_shp_zip(
    file: UploadFile = File(...),
    _user: dict = Depends(require_admin),
):
    """上传 SHP 压缩包并返回字段列表，让用户选择高度字段。"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 格式的压缩包")

    _prune_staged_files()

    file_token = uuid.uuid4().hex[:12]
    tmp_dir = OUTPUT_ROOT / "_uploads"
    tmp_dir.mkdir(exist_ok=True)
    zip_path = tmp_dir / f"{file_token}_preview.zip"

    try:
        total_bytes = 0
        with open(zip_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_PREVIEW_ZIP_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"压缩包超过 {MAX_PREVIEW_ZIP_BYTES // 1024 // 1024} MB 上限，请切片后上传",
                    )
                f.write(chunk)
    except HTTPException:
        zip_path.unlink(missing_ok=True)
        raise
    except Exception:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="文件保存失败")

    # 解压并解析字段
    try:
        import zipfile as zf
        extract_dir = tmp_dir / f"_preview_{file_token}"
        extract_dir.mkdir(exist_ok=True)
        with zf.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        shp_files = list(extract_dir.glob("**/*.shp"))
        if not shp_files:
            raise ValueError("未找到 .shp 文件")

        import shapefile
        sf = shapefile.Reader(str(shp_files[0]))
        fields = [f[0] for f in sf.fields[1:]]
        record_count = 0
        for _ in sf.iterRecords():
            record_count += 1
            if record_count > MAX_SAFE_FEATURES:
                break
        if record_count > MAX_SAFE_FEATURES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"当前 SHP 要素数超过本服务器安全上限 {MAX_SAFE_FEATURES}。"
                    "请先按行政区/网格切片后分批转换。"
                ),
            )

        # 自动检测高度字段
        from api.shp_to_3dtiles import _find_height_field
        suggested = _find_height_field(fields)

        # 存储暂存信息
        _staged_files[file_token] = {
            "zip_path": str(zip_path),
            "extract_dir": str(extract_dir),
            "shp_path": str(shp_files[0]),
            "fields": fields,
            "record_count": record_count,
            "created_at": asyncio.get_running_loop().time(),
        }

        return {
            "status": "success",
            "file_token": file_token,
            "fields": fields,
            "record_count": record_count,
            "suggested_height_field": suggested,
        }
    except Exception as e:
        zip_path.unlink(missing_ok=True)
        extract_dir = tmp_dir / f"_preview_{file_token}"
        shutil.rmtree(extract_dir, ignore_errors=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")


async def _run_shp_conversion_job(job_id: str, staged: dict, payload: ShpConvertOptions, safe_name: str) -> None:
    def _progress(progress: float, message: str):
        _update_job(job_id, phase="processing", progress=progress, message=message)

    async with _conversion_lock:
        if _jobs.get(job_id, {}).get("phase") == "cancelled":
            _cleanup_staged(staged)
            return

        try:
            from api.shp_to_3dtiles import process_shp_zip

            _update_job(job_id, phase="extracting", progress=0.02, message="正在解压 Shapefile...")

            result = await asyncio.to_thread(
                process_shp_zip,
                staged["zip_path"],
                safe_name,
                _progress,
                height_field=payload.height_field,
                base_color=payload.base_color,
                opacity=payload.opacity,
                classification_field=payload.classification_field,
                color_ramp=payload.color_ramp,
                max_features=MAX_SAFE_FEATURES,
            )

            _update_job(
                job_id,
                phase="done",
                progress=1.0,
                message=f"完成：{result['feature_count']} 栋建筑",
                feature_count=result["feature_count"],
                tileset_url=result["tileset_url"],
            )
            _cleanup_staged(staged)
        except asyncio.CancelledError:
            _update_job(job_id, phase="cancelled", progress=0.0, message="任务已取消")
            _cleanup_staged(staged)
            raise
        except Exception as e:
            logger.exception("3D Tiles 生成失败")
            _update_job(job_id, phase="error", progress=0.0, message=str(e)[:300])
            _cleanup_staged(staged)
        finally:
            _job_tasks.pop(job_id, None)


@router.post("/upload-shp", response_model=JobStatus)
async def convert_shp_to_3dtiles(
    payload: ShpConvertOptions,
    _user: dict = Depends(require_admin),
):
    """使用预览阶段暂存的文件 + 用户选择的配置，创建后台转换任务。"""
    staged = _staged_files.pop(payload.file_token, None)
    if not staged:
        raise HTTPException(status_code=400, detail="文件已过期，请重新上传")

    record_count = int(staged.get("record_count") or 0)
    if record_count > MAX_SAFE_FEATURES:
        _cleanup_staged(staged)
        raise HTTPException(
            status_code=413,
            detail=(
                f"当前 SHP 包含 {record_count} 个要素，超过本服务器安全上限 {MAX_SAFE_FEATURES}。"
                "请先按行政区/网格切片后分批转换。"
            ),
        )

    job_id = uuid.uuid4().hex[:12]
    safe_name = f"{job_id}_3d_buildings"
    queued = _conversion_lock.locked()
    _jobs[job_id] = _job_status(
        job_id,
        "queued" if queued else "idle",
        0.0,
        "已有转换任务运行中，当前任务已排队" if queued else "任务已创建，准备转换...",
    )
    _job_tasks[job_id] = asyncio.create_task(_run_shp_conversion_job(job_id, staged, payload, safe_name))

    return _jobs[job_id]


@router.post("/job/{job_id}/cancel", response_model=JobStatus)
async def cancel_job(job_id: str, _user: dict = Depends(require_admin)):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = _job_tasks.get(job_id)
    if task and not task.done():
        task.cancel()
    _update_job(job_id, phase="cancelled", progress=0.0, message="任务已取消")
    return _jobs[job_id]


@router.get("/job/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """查询 3D 处理任务的进度。"""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _jobs[job_id]


@router.get("/tiles/{path:path}")
async def serve_3dtiles_file(path: str):
    """提供 3D Tiles 静态文件（tileset.json / .b3dm）。"""
    safe_path = os.path.normpath(path)
    full_path = OUTPUT_ROOT / safe_path
    if not full_path.exists() or not full_path.is_relative_to(OUTPUT_ROOT):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(full_path)
