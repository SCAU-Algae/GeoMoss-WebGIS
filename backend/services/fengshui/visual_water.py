import base64
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Request

from api.auth import get_auth_db_connection


logger = logging.getLogger(__name__)

DASHSCOPE_COMPATIBLE_URL = os.getenv(
    "DASHSCOPE_COMPATIBLE_CHAT_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
QWEN_VISION_TIMEOUT_SECONDS = float(os.getenv("FENGSHUI_QWEN_VISION_TIMEOUT_SECONDS", "80"))
QWEN_VISION_MAX_TOKENS = int(os.getenv("FENGSHUI_QWEN_VISION_MAX_TOKENS", "1000"))
QWEN_VISION_MODELS = [
    item.strip()
    for item in os.getenv(
        "FENGSHUI_QWEN_VISION_MODELS",
        "qwen3-vl-plus,qwen-vl-max-latest,qwen-vl-max,qwen3.6-plus,qwen3.5-plus,qwen-vl-plus-latest,qwen-vl-plus",
    ).split(",")
    if item.strip()
]

QWEN_WATER_SYSTEM_PROMPT = """
你是遥感图像水体识别专家。输入图像为北向上方的在线遥感证据图，青色线框是用户选择的研究范围，白色十字大致为范围中心。
任务是识别研究范围内及周边可见水体，只输出可核验的视觉事实，不做风水评价。
当矢量水系和视觉图像冲突时，视觉识别结果会作为水体事实的优先证据，所以请谨慎判断，宁可标注不确定也不要臆测。
必须只返回 JSON，不要 Markdown，不要代码块，不要解释 JSON 之外的内容。
JSON schema:
{
  "water_presence": "none|possible|clear",
  "water_types": ["river|lake|pond|canal|reservoir|wetland|coast|unknown"],
  "dominant_direction": "north|northeast|east|southeast|south|southwest|west|northwest|center|multiple|unknown",
  "relative_size": "none|small|medium|large",
  "shape_pattern": "80 字以内，说明水体形态、位置与范围关系",
  "visual_evidence": ["1-4 条视觉证据，每条不超过 50 个中文字符"],
  "confidence": "high|medium|low"
}
""".strip()


def _empty_visual(status: str, message: str = "", model: str = "") -> Dict[str, Any]:
    return {
        "available": False,
        "status": status,
        "model": model,
        "water_presence": "unknown",
        "water_types": [],
        "dominant_direction": "unknown",
        "relative_size": "unknown",
        "shape_pattern": "",
        "visual_evidence": [],
        "confidence": "low",
        "conflict_policy": "visual_priority",
        "message": message,
    }


def _get_api_key_from_db_sync(key_name: str) -> str:
    try:
        with get_auth_db_connection() as conn:
            row = conn.execute(
                "SELECT key_value FROM api_keys WHERE key_name = ?",
                (key_name,),
            ).fetchone()
            if row:
                return str(dict(row).get("key_value") or "").strip()
    except Exception:
        pass
    return ""


def resolve_dashscope_api_key() -> Dict[str, str]:
    db_key = _get_api_key_from_db_sync("dashscope_api_key") or _get_api_key_from_db_sync("qwen_vision_api_key")
    if db_key:
        return {"api_key": db_key, "source": "database"}

    for env_name in ("DASHSCOPE_API_KEY", "QWEN_VISION_API_KEY", "ALIYUN_BAILIAN_API_KEY"):
        value = str(os.getenv(env_name, "") or "").strip()
        if value:
            return {"api_key": value, "source": env_name}
    return {"api_key": "", "source": "missing"}


def get_visual_water_status() -> Dict[str, Any]:
    key_info = resolve_dashscope_api_key()
    model = QWEN_VISION_MODELS[0] if QWEN_VISION_MODELS else ""
    return {
        "available": bool(key_info["api_key"] and model),
        "model": model,
        "api_key_source": key_info["source"],
        "message": "千问视觉水体识别已配置。" if key_info["api_key"] else "千问视觉 API Key 未配置，视觉识别将跳过。",
    }


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("千问视觉返回内容不是有效 JSON")


def _normalize_enum(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else fallback


def _normalize_list(value: Any, *, allowed: Optional[set[str]] = None, limit: int = 4) -> List[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in re.split(r"[,，、;；\n]+", value) if item.strip()]
    elif isinstance(value, list):
        raw_items = [str(item or "").strip() for item in value if str(item or "").strip()]
    else:
        raw_items = []

    output: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = item.lower() if allowed else item[:70]
        if allowed and normalized not in allowed:
            normalized = "unknown"
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _extract_assistant_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(parts)
    return ""


def _normalize_visual_payload(payload: Dict[str, Any], *, model: str, capture: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
    water_types = _normalize_list(
        payload.get("water_types"),
        allowed={"river", "lake", "pond", "canal", "reservoir", "wetland", "coast", "unknown"},
        limit=5,
    )
    return {
        "available": True,
        "status": "ready",
        "model": model,
        "water_presence": _normalize_enum(payload.get("water_presence"), {"none", "possible", "clear"}, "possible"),
        "water_types": water_types,
        "dominant_direction": _normalize_enum(
            payload.get("dominant_direction"),
            {"north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest", "center", "multiple", "unknown"},
            "unknown",
        ),
        "relative_size": _normalize_enum(payload.get("relative_size"), {"none", "small", "medium", "large"}, "unknown"),
        "shape_pattern": str(payload.get("shape_pattern") or "").strip()[:120],
        "visual_evidence": _normalize_list(payload.get("visual_evidence"), limit=4),
        "confidence": _normalize_enum(payload.get("confidence"), {"high", "medium", "low"}, "medium"),
        "conflict_policy": "visual_priority",
        "imagery_source": capture.get("imagery_source") or "",
        "imagery_label": capture.get("imagery_label") or "",
        "image_size": capture.get("image_size") or {},
        "zoom": capture.get("zoom"),
        "elapsed_ms": round(float(elapsed_ms), 1),
        "message": "千问视觉已完成水体识别。",
    }


async def analyze_visual_water(
    request: Request,
    capture: Dict[str, Any],
    *,
    area_info: Optional[Dict[str, Any]] = None,
    water_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not capture.get("available") or not capture.get("image_bytes"):
        return _empty_visual("no_image", capture.get("message") or "没有可用遥感截图，已跳过视觉水体识别。")

    key_info = resolve_dashscope_api_key()
    api_key = key_info["api_key"]
    if not api_key:
        return _empty_visual("unconfigured", "千问视觉 API Key 未配置，已跳过视觉水体识别。")
    if not QWEN_VISION_MODELS:
        return _empty_visual("unconfigured", "千问视觉模型未配置，已跳过视觉水体识别。")

    image_b64 = base64.b64encode(bytes(capture.get("image_bytes") or b"")).decode("ascii")
    data_url = f"data:{capture.get('mime_type') or 'image/jpeg'};base64,{image_b64}"
    context = {
        "area_info": area_info or {},
        "vector_water_hint": {
            "available": bool((water_status or {}).get("available")),
            "direction": (water_status or {}).get("direction"),
            "nearest_distance_m": (water_status or {}).get("nearest_distance_m"),
            "intersects": bool((water_status or {}).get("intersects")),
            "nearest_name": (water_status or {}).get("nearest_name"),
            "nearest_type": (water_status or {}).get("nearest_type"),
        },
        "image_note": "图像为北向上方；青色边线是研究范围；白色十字为中心。",
    }
    user_text = (
        "请识别这张北向遥感证据图中的水体事实，并严格按指定 JSON schema 返回。"
        "如果矢量水系提示与图像观感冲突，请以图像事实为准。"
        + json.dumps(context, ensure_ascii=False)
    )
    messages = [
        {"role": "system", "content": QWEN_WATER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    started_at = time.perf_counter()
    last_message = ""
    for model in QWEN_VISION_MODELS:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(QWEN_VISION_TIMEOUT_SECONDS, connect=8.0),
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    DASHSCOPE_COMPATIBLE_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.0,
                        "max_tokens": QWEN_VISION_MAX_TOKENS,
                    },
                )
            if response.status_code != 200:
                try:
                    error_payload = response.json()
                except Exception:
                    error_payload = {}
                last_message = str(error_payload.get("message") or error_payload.get("error") or response.text or "")
                logger.warning("Qwen vision model %s failed: HTTP %s %s", model, response.status_code, last_message[:160])
                continue
            payload = response.json()
            text = _extract_assistant_text(payload)
            parsed = _extract_json_object(text)
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            return _normalize_visual_payload(parsed, model=model, capture=capture, elapsed_ms=elapsed_ms)
        except Exception as exc:
            last_message = str(exc)
            logger.warning("Qwen visual water analysis failed with model %s: %s", model, last_message[:180])
            continue

    return _empty_visual(
        "error",
        f"千问视觉调用失败：{last_message[:160]}" if last_message else "千问视觉调用失败。",
        QWEN_VISION_MODELS[0],
    )
