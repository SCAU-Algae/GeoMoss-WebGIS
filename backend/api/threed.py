"""
3D 数据处理 API：SHP 压缩包上传 → 自动生成 3D Tiles。
"""

import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from api.auth import require_api_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/3d", tags=["3d-processing"])

# 临时存储：上传的 SHP 文件（等待用户确认配置后再转换）
_staged_files: Dict[str, dict] = {}


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
    phase: str = Field(default="idle")  # idle / extracting / parsing / generating / done / error
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = Field(default="")
    feature_count: int = Field(default=0)
    tileset_url: str = Field(default="")


def _update_job(job_id: str, **kwargs):
    if job_id in _jobs:
        _jobs[job_id].update(kwargs)


@router.post("/preview-shp")
async def preview_shp_zip(file: UploadFile = File(...)):
    """上传 SHP 压缩包并返回字段列表，让用户选择高度字段。"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 格式的压缩包")

    file_token = uuid.uuid4().hex[:12]
    tmp_dir = OUTPUT_ROOT / "_uploads"
    tmp_dir.mkdir(exist_ok=True)
    zip_path = tmp_dir / f"{file_token}_preview.zip"

    try:
        with open(zip_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
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
        record_count = len(sf.records())

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
        raise HTTPException(status_code=400, detail=f"解析失败: {str(e)}")


@router.post("/upload-shp", response_model=JobStatus)
async def convert_shp_to_3dtiles(
    payload: ShpConvertOptions,
    _user: dict = Depends(require_api_access),
):
    """使用预览阶段暂存的文件 + 用户选择的配置，生成 3D Tiles。"""
    staged = _staged_files.pop(payload.file_token, None)
    if not staged:
        raise HTTPException(status_code=400, detail="文件已过期，请重新上传")

    job_id = uuid.uuid4().hex[:12]
    safe_name = f"{job_id}_3d_buildings"
    _jobs[job_id] = {"job_id": job_id, "phase": "idle", "progress": 0, "message": "准备转换...", "feature_count": 0, "tileset_url": ""}

    def _progress(progress: float, message: str):
        _update_job(job_id, phase="processing", progress=progress, message=message)

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
        )

        _update_job(
            job_id,
            phase="done",
            progress=1.0,
            message=f"完成：{result['feature_count']} 栋建筑",
            feature_count=result["feature_count"],
            tileset_url=result["tileset_url"],
        )

        # 清理暂存文件
        import shutil
        zip_path = staged["zip_path"]
        extract_dir = staged["extract_dir"]
        zip_path and Path(zip_path).unlink(missing_ok=True)
        extract_dir and shutil.rmtree(extract_dir, ignore_errors=True)

    except Exception as e:
        logger.exception("3D Tiles 生成失败")
        _update_job(job_id, phase="error", progress=0.0, message=str(e)[:200])

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
