import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from api.agent_chat import (
    DEFAULT_AGENT_BASE_URL,
    DEFAULT_AGENT_MAX_TOKENS,
    DEFAULT_AGENT_MODEL,
    DEFAULT_AGENT_TEMPERATURE,
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    _call_upstream_chat,
    _extract_assistant_reply,
    _resolve_effective_agent_runtime_sync,
)
from api.api_management import record_api_call
from api.auth import normalize_role, resolve_quota_subject

logger = logging.getLogger(__name__)


AI_INSIGHTS_SYSTEM_PROMPT = """
你是 WebGIS 环境格局分析助手。你只基于输入的 DEM、水系、遥感视觉识别、高德位置语义、评分和报告摘要做文化景观与空间环境解释。
禁止生成确定性吉凶、投资、购房、经营、医疗、法律、婚姻建议。
证据优先级规则：
1. 千问视觉水体识别若 status=ready，则水体有无、类型、方位、大小和形态以 visual_water 为准。
2. 矢量水系 water 作为复核背景；若与 visual_water 冲突，必须在 evidence_conflicts 或 risk_notes 中提醒复核，但水体解释按 visual_water。
3. 高德 location_context 只用于“位置在哪里、附近主要有什么”的语义补充，不得替代 DEM 或遥感事实。
必须只返回 JSON，不要 Markdown，不要代码块。
JSON schema:
{
  "summary": "80 字以内的总体判断",
  "location_context_summary": "80 字以内的位置与周边环境概括",
  "visual_water_interpretation": "80 字以内的视觉水体解释",
  "evidence_conflicts": ["0-3 条证据冲突或复核说明，每条不超过 60 个中文字符"],
  "pattern_insights": ["2-4 条格局洞察，每条不超过 60 个中文字符"],
  "risk_notes": ["2-4 条风险或复核提醒，每条不超过 60 个中文字符"],
  "planning_suggestions": ["2-4 条空间整理建议，每条不超过 60 个中文字符"],
  "culture_notes": ["2-4 条传统环境文化解释，每条不超过 60 个中文字符"],
  "confidence": "high|medium|low"
}
请使用审慎、专业、可解释的中文表达。
""".strip()

AI_INSIGHTS_ENDPOINT = "/api/fengshui/analyze/ai-insights"
MAX_CONTEXT_TEXT = 900
MODEL_PREFERENCE_KEYWORDS = ("flash", "chat", "turbo", "mini", "lite")
MODEL_AVOID_KEYWORDS = ("reason", "thinking", "r1", "pro", "preview")


def _empty_insights(status: str, message: str = "", model: str = "") -> Dict[str, Any]:
    return {
        "available": False,
        "status": status,
        "model": model,
        "summary": "",
        "location_context_summary": "",
        "visual_water_interpretation": "",
        "evidence_conflicts": [],
        "pattern_insights": [],
        "risk_notes": [],
        "planning_suggestions": [],
        "culture_notes": [],
        "confidence": "low",
        "message": message,
    }


def _clip_text(value: Any, limit: int = MAX_CONTEXT_TEXT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _compact_analysis_context(base_result: Dict[str, Any]) -> Dict[str, Any]:
    water = (base_result.get("data_status") or {}).get("water") or {}
    dem = (base_result.get("data_status") or {}).get("dem") or {}
    visual = base_result.get("visual_water") or (base_result.get("data_status") or {}).get("visual_water") or {}
    location = base_result.get("location_context") or {}
    pois = location.get("pois") or []
    return {
        "area_info": base_result.get("area_info") or {},
        "terrain_metrics": base_result.get("terrain_metrics") or {},
        "scores": base_result.get("scores") or {},
        "score_level": base_result.get("score_level") or "",
        "spatial_pattern": base_result.get("spatial_pattern") or {},
        "recommendations": (base_result.get("recommendations") or [])[:6],
        "water": {
            "available": bool(water.get("available")),
            "status": water.get("status"),
            "nearest_distance_m": water.get("nearest_distance_m"),
            "direction": water.get("direction"),
            "intersects": bool(water.get("intersects")),
            "score": water.get("score"),
            "message": water.get("message"),
            "nearest_name": water.get("nearest_name"),
            "nearest_type": water.get("nearest_type"),
        },
        "visual_water": {
            "available": bool(visual.get("available")),
            "status": visual.get("status"),
            "model": visual.get("model"),
            "water_presence": visual.get("water_presence"),
            "water_types": visual.get("water_types") or [],
            "dominant_direction": visual.get("dominant_direction"),
            "relative_size": visual.get("relative_size"),
            "shape_pattern": visual.get("shape_pattern"),
            "visual_evidence": visual.get("visual_evidence") or [],
            "confidence": visual.get("confidence"),
            "imagery_label": visual.get("imagery_label"),
            "message": visual.get("message"),
        },
        "location_context": {
            "available": bool(location.get("available")),
            "status": location.get("status"),
            "formatted_address": location.get("formatted_address"),
            "admin": location.get("admin") or {},
            "poi_categories": (location.get("poi_categories") or [])[:8],
            "pois": [
                {
                    "name": poi.get("name"),
                    "type": poi.get("type"),
                    "distance_m": poi.get("distance_m"),
                }
                for poi in pois[:10]
                if isinstance(poi, dict)
            ],
            "aois": (location.get("aois") or [])[:5],
            "roads": (location.get("roads") or [])[:5],
            "message": location.get("message"),
        },
        "evidence_priority": base_result.get("evidence_priority") or {},
        "evidence_conflicts": base_result.get("evidence_conflicts") or [],
        "dem": {
            "available": bool(dem.get("available")),
            "message": dem.get("message"),
            "sample_size": dem.get("sample_size"),
        },
        "report_excerpt": _clip_text(base_result.get("report")),
        "disclaimer": base_result.get("disclaimer") or "",
    }


def _select_insight_model(runtime: Dict[str, Any]) -> str:
    configured = str(runtime.get("model") or "").strip()
    available = [str(item or "").strip() for item in (runtime.get("available_models") or []) if str(item or "").strip()]
    if available:
        preferred_safe = [
            model for model in available
            if any(keyword in model.lower() for keyword in MODEL_PREFERENCE_KEYWORDS)
            and not any(keyword in model.lower() for keyword in MODEL_AVOID_KEYWORDS)
        ]
        if preferred_safe:
            return preferred_safe[0]
        preferred = [
            model for model in available
            if any(keyword in model.lower() for keyword in MODEL_PREFERENCE_KEYWORDS)
        ]
        if preferred:
            return preferred[0]
        safer = [
            model for model in available
            if not any(keyword in model.lower() for keyword in MODEL_AVOID_KEYWORDS)
        ]
        if safer:
            return safer[0]
    return configured


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
    partial = _extract_partial_json_fields(text)
    if partial:
        return partial
    raise ValueError("AI 返回内容不是有效 JSON")


def _extract_partial_json_fields(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}

    def string_field(name: str) -> str:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*"([^"]*)"', raw, flags=re.DOTALL)
        return match.group(1).strip() if match else ""

    def array_field(name: str) -> List[str]:
        match = re.search(rf'"{re.escape(name)}"\s*:\s*\[(.*?)\]', raw, flags=re.DOTALL)
        if not match:
            return []
        return [item.strip() for item in re.findall(r'"([^"]+)"', match.group(1))]

    parsed = {
        "summary": string_field("summary"),
        "location_context_summary": string_field("location_context_summary"),
        "visual_water_interpretation": string_field("visual_water_interpretation"),
        "evidence_conflicts": array_field("evidence_conflicts"),
        "pattern_insights": array_field("pattern_insights"),
        "risk_notes": array_field("risk_notes"),
        "planning_suggestions": array_field("planning_suggestions"),
        "culture_notes": array_field("culture_notes"),
        "confidence": string_field("confidence") or "medium",
    }
    if parsed["summary"] or any(parsed[key] for key in ("pattern_insights", "risk_notes", "planning_suggestions", "culture_notes")):
        return parsed
    if parsed["location_context_summary"] or parsed["visual_water_interpretation"] or parsed["evidence_conflicts"]:
        return parsed
    return {}


def _strip_json_field_prefix(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r'^"?(summary|location_context_summary|visual_water_interpretation|evidence_conflicts|pattern_insights|risk_notes|planning_suggestions|culture_notes|confidence)"?\s*:\s*', "", value)
    value = value.strip().strip(",")
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return value.strip().strip(",").strip()


def _normalize_list(value: Any, *, item_limit: int = 4, char_limit: int = 80) -> List[str]:
    if isinstance(value, str):
        raw_items = [piece.strip() for piece in re.split(r"[\n；;]+", value) if piece.strip()]
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _strip_json_field_prefix(item)
        if not text:
            continue
        text = text[:char_limit].rstrip()
        if text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= item_limit:
            break
    return items


def _normalize_ai_payload(payload: Dict[str, Any], *, model: str, base_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    confidence = str(payload.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    fallback = build_rule_based_insights(base_result or {}, status="local_merge") if base_result else {}

    evidence_conflicts = _normalize_list(payload.get("evidence_conflicts"), item_limit=3, char_limit=80)
    if not evidence_conflicts and base_result:
        evidence_conflicts = _normalize_list(
            [item.get("message") for item in (base_result.get("evidence_conflicts") or []) if isinstance(item, dict)],
            item_limit=3,
            char_limit=80,
        )

    return {
        "available": True,
        "status": "ready",
        "model": model,
        "summary": _strip_json_field_prefix(payload.get("summary") or fallback.get("summary") or "")[:120],
        "location_context_summary": _strip_json_field_prefix(payload.get("location_context_summary") or fallback.get("location_context_summary") or "")[:120],
        "visual_water_interpretation": _strip_json_field_prefix(payload.get("visual_water_interpretation") or fallback.get("visual_water_interpretation") or "")[:120],
        "evidence_conflicts": evidence_conflicts,
        "pattern_insights": _normalize_list(payload.get("pattern_insights")) or fallback.get("pattern_insights", []),
        "risk_notes": _normalize_list(payload.get("risk_notes")) or fallback.get("risk_notes", []),
        "planning_suggestions": _normalize_list(payload.get("planning_suggestions")) or fallback.get("planning_suggestions", []),
        "culture_notes": _normalize_list(payload.get("culture_notes")) or fallback.get("culture_notes", []),
        "confidence": confidence,
        "message": "",
    }


def build_rule_based_insights(base_result: Dict[str, Any], *, status: str = "local_fallback", message: str = "") -> Dict[str, Any]:
    metrics = base_result.get("terrain_metrics") or {}
    scores = base_result.get("scores") or {}
    pattern = base_result.get("spatial_pattern") or {}
    water = (base_result.get("data_status") or {}).get("water") or {}
    visual = base_result.get("visual_water") or (base_result.get("data_status") or {}).get("visual_water") or {}
    location = base_result.get("location_context") or {}

    slope = float(metrics.get("mean_slope", 0) or 0)
    relief = float(metrics.get("relief", 0) or 0)
    overall = int(scores.get("overall_score", 0) or 0)
    water_message = str(water.get("message") or pattern.get("water_relation") or "").strip()
    visual_message = _build_visual_water_sentence(visual)
    location_summary = _build_location_context_sentence(location)

    pattern_insights = [
        str(pattern.get("back_mountain") or "靠山格局需结合更大尺度地势复核。"),
        str(pattern.get("front_open") or "明堂条件需结合场地开敞度和动线组织复核。"),
    ]
    if visual_message:
        pattern_insights.append(visual_message)
    elif water_message:
        pattern_insights.append(water_message)

    risk_notes: List[str] = []
    if bool(water.get("intersects")):
        risk_notes.append("水体贴邻或相交，需优先核验洪涝与退让边界。")
    for conflict in base_result.get("evidence_conflicts") or []:
        if isinstance(conflict, dict) and conflict.get("message"):
            risk_notes.append(str(conflict.get("message")))
    if slope >= 10:
        risk_notes.append("坡度偏大，需复核边坡稳定和雨水径流组织。")
    if relief < 30:
        risk_notes.append("高差较小，靠山与围合更多依赖周边城市肌理。")
    if not risk_notes:
        risk_notes.append("基础指标平稳，仍需结合建筑遮挡和现状排水复核。")

    planning_suggestions = [
        "入口与前场宜保持通达、清爽、少遮挡。",
        "水系相关空间应先满足安全退让与排水组织。",
        "后续可叠加建筑、植被和道路数据增强判断。",
    ]
    culture_notes = [
        "传统得水解释更适合转译为亲水性与排水安全。",
        "明堂可理解为前场开敞、视线和活动面的综合质量。",
        "藏风聚气可转译为空间围合、边界秩序与舒适度。",
    ]
    summary = f"综合评分 {overall}，地形坡度约 {slope:g} 度，高差约 {relief:g} m；建议把文化解释与工程安全复核结合使用。"

    return {
        "available": True,
        "status": status,
        "model": "local-rule",
        "summary": summary[:120],
        "location_context_summary": location_summary,
        "visual_water_interpretation": visual_message,
        "evidence_conflicts": _normalize_list(
            [item.get("message") for item in (base_result.get("evidence_conflicts") or []) if isinstance(item, dict)],
            item_limit=3,
            char_limit=80,
        ),
        "pattern_insights": _normalize_list(pattern_insights),
        "risk_notes": _normalize_list(risk_notes),
        "planning_suggestions": _normalize_list(planning_suggestions),
        "culture_notes": _normalize_list(culture_notes),
        "confidence": "medium",
        "message": message,
    }


def _build_visual_water_sentence(visual: Dict[str, Any]) -> str:
    if not visual or not visual.get("available"):
        return ""
    presence = str(visual.get("water_presence") or "unknown")
    direction_map = {
        "north": "北侧",
        "northeast": "东北侧",
        "east": "东侧",
        "southeast": "东南侧",
        "south": "南侧",
        "southwest": "西南侧",
        "west": "西侧",
        "northwest": "西北侧",
        "center": "范围内部",
        "multiple": "多方向",
        "unknown": "方位不明",
    }
    size_map = {"none": "无明显", "small": "小尺度", "medium": "中等尺度", "large": "大尺度", "unknown": "尺度不明"}
    if presence == "none":
        return "视觉模型未识别到明显水体，得水解释宜弱化并复核底图时相。"
    if presence in {"possible", "clear"}:
        direction = direction_map.get(str(visual.get("dominant_direction") or "unknown"), "方位不明")
        size = size_map.get(str(visual.get("relative_size") or "unknown"), "尺度不明")
        shape = str(visual.get("shape_pattern") or "").strip()
        return f"视觉模型识别到{size}水体，主要位于{direction}；{shape}".strip("；")[:120]
    return ""


def _build_location_context_sentence(location: Dict[str, Any]) -> str:
    if not location or not location.get("available"):
        return ""
    address = str(location.get("formatted_address") or "").strip()
    categories = [
        str(item.get("name") or "").strip()
        for item in (location.get("poi_categories") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    category_text = "、".join(categories[:4])
    if address and category_text:
        return f"范围位于{address}附近，周边以{category_text}等要素为主。"[:120]
    if address:
        return f"范围位于{address}附近。"[:120]
    if category_text:
        return f"周边以{category_text}等要素为主。"[:120]
    return ""


def _match_freeform_group(line: str) -> str:
    text = re.sub(r"[\s:：#*【】\\[\\]（）()]+", "", str(line or ""))
    if not text:
        return ""
    if any(keyword in text for keyword in ("格局洞察", "格局分析", "空间格局", "山水格局", "格局")):
        return "pattern_insights"
    if any(keyword in text for keyword in ("风险", "复核", "安全", "问题", "约束")):
        return "risk_notes"
    if any(keyword in text for keyword in ("规划建议", "整理建议", "优化建议", "策略", "建议")):
        return "planning_suggestions"
    if any(keyword in text for keyword in ("文化解释", "文化说明", "传统解释", "风水文化", "文化")):
        return "culture_notes"
    return ""


def _clean_freeform_item(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^```(?:json)?\\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\\s*```$", "", text)
    text = re.sub(r"^[\\-•*\\d一二三四五六七八九十、.．)）\\s]+", "", text)
    text = re.sub(r"^(格局洞察|风险提示|复核风险|整理策略|规划建议|文化解释|文化说明)[:：]\\s*", "", text)
    return _strip_json_field_prefix(text).strip(" \t\r\n-•。；;")


def _route_freeform_sentence(sentence: str) -> str:
    text = str(sentence or "")
    if any(keyword in text for keyword in ("洪涝", "退让", "风险", "安全", "复核", "坡度偏大", "排水")):
        return "risk_notes"
    if any(keyword in text for keyword in ("建议", "宜", "应", "优化", "保持", "控制", "叠加")):
        return "planning_suggestions"
    if any(keyword in text for keyword in ("风水", "明堂", "藏风", "聚气", "得水", "传统", "文化")):
        return "culture_notes"
    if any(keyword in text for keyword in ("格局", "地形", "水系", "坡向", "开敞", "围合")):
        return "pattern_insights"
    return ""


def structure_freeform_ai_reply(raw_text: str, base_result: Dict[str, Any], *, model: str) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    fallback = build_rule_based_insights(
        base_result,
        status="local_fallback",
        message="AI 未返回可结构化内容，已使用本地规则兜底。",
    )
    if len(text) < 8:
        return fallback

    buckets: Dict[str, List[str]] = {
        "pattern_insights": [],
        "risk_notes": [],
        "planning_suggestions": [],
        "culture_notes": [],
    }
    summary = ""
    current_group = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        matched_group = _match_freeform_group(line)
        if matched_group and len(_clean_freeform_item(line)) <= 8:
            current_group = matched_group
            continue

        item = _clean_freeform_item(line)
        if not item or item in {"{", "}"}:
            continue
        if not summary and len(item) >= 10:
            summary = item[:120]
        target_group = current_group or matched_group or _route_freeform_sentence(item)
        if target_group:
            buckets[target_group].append(item)

    sentences = [piece.strip() for piece in re.split(r"[。！？!?；;\\n]+", text) if piece.strip()]
    for sentence in sentences:
        item = _clean_freeform_item(sentence)
        if not item or len(item) < 8:
            continue
        target_group = _route_freeform_sentence(item)
        if target_group:
            buckets[target_group].append(item)

    normalized = {
        key: _normalize_list(values) or fallback.get(key, [])
        for key, values in buckets.items()
    }
    has_ai_items = any(values for values in normalized.values())
    if not has_ai_items:
        return fallback

    return {
        "available": True,
        "status": "ai_text_fallback",
        "model": model,
        "summary": summary or fallback.get("summary", ""),
        "location_context_summary": fallback.get("location_context_summary", ""),
        "visual_water_interpretation": fallback.get("visual_water_interpretation", ""),
        "evidence_conflicts": fallback.get("evidence_conflicts", []),
        "pattern_insights": normalized["pattern_insights"],
        "risk_notes": normalized["risk_notes"],
        "planning_suggestions": normalized["planning_suggestions"],
        "culture_notes": normalized["culture_notes"],
        "confidence": "medium",
        "message": "AI 未返回严格 JSON，已自动结构化其文本。",
    }


def get_ai_insights_status() -> Dict[str, Any]:
    try:
        runtime = _resolve_effective_agent_runtime_sync("")
        api_key = str(runtime.get("api_key") or "").strip()
        model = str(runtime.get("model") or "").strip()
        return {
            "available": bool(api_key and model),
            "model": model,
            "model_source": str(runtime.get("model_source") or "unknown"),
            "api_key_source": str(runtime.get("api_key_source") or "missing"),
            "message": "AI 洞察已接入 Agent 配置。" if api_key and model else "Agent Key 或模型未配置，AI 洞察将自动跳过。",
        }
    except Exception as exc:
        logger.warning("Failed to read fengshui AI status: %s", str(exc))
        return {
            "available": False,
            "model": "",
            "model_source": "error",
            "api_key_source": "error",
            "message": f"AI 洞察状态读取失败：{str(exc)[:120]}",
        }


def _resolve_session_identity(session: Optional[Dict[str, Any]]) -> Dict[str, str]:
    session = session or {}
    username = str(session.get("username") or "").strip() or "fengshui-anonymous"
    role = normalize_role(session.get("role"), username) if session else "system"
    quota_subject = resolve_quota_subject(username, role, session.get("guest_uid")) if session else "fengshui-system"
    return {
        "username": username,
        "role": role,
        "quota_subject": quota_subject,
    }


async def generate_ai_insights(
    request: Request,
    base_result: Dict[str, Any],
    *,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    identity = _resolve_session_identity(session)
    try:
        runtime = await asyncio.to_thread(_resolve_effective_agent_runtime_sync, identity["username"])
        api_key = str(runtime.get("api_key") or "").strip()
        model = _select_insight_model(runtime)
        if not api_key:
            return _empty_insights("unconfigured", "Agent Key 未配置，已跳过 AI 洞察。", model)
        if not model:
            return _empty_insights("unconfigured", "Agent 模型未配置，已跳过 AI 洞察。", model)

        context = _compact_analysis_context(base_result)
        user_prompt = (
            "请根据下面的风水环境格局分析 JSON，补充结构化 AI 洞察。"
            "只能基于输入信息，不要编造未提供的数据。"
            "你的回复第一个字符必须是 {，最后一个字符必须是 }。\n"
            + json.dumps(context, ensure_ascii=False)
        )
        messages = [
            {"role": "system", "content": AI_INSIGHTS_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        started_at = time.perf_counter()
        upstream_status = 200
        try:
            reply = ""
            upstream_data = await _call_upstream_chat(
                request,
                base_url=str(runtime.get("base_url") or DEFAULT_AGENT_BASE_URL),
                api_key=api_key,
                model=model or DEFAULT_AGENT_MODEL,
                messages=messages,
                timeout_seconds=min(45, int(runtime.get("timeout_seconds") or DEFAULT_AGENT_TIMEOUT_SECONDS)),
                max_tokens=min(900, int(runtime.get("max_tokens") or DEFAULT_AGENT_MAX_TOKENS)),
                temperature=min(0.4, float(runtime.get("temperature") or DEFAULT_AGENT_TEMPERATURE)),
                response_format={"type": "json_object"},
            )
            reply = _extract_assistant_reply(upstream_data)
            parsed = _extract_json_object(reply)
            if not _has_minimum_insight_fields(parsed):
                raise ValueError("AI 返回 JSON 缺少必要字段")
            return _normalize_ai_payload(parsed, model=model, base_result=base_result)
        except HTTPException as exc:
            upstream_status = int(exc.status_code)
            return _empty_insights("error", f"AI 洞察调用失败：{str(exc.detail or '')[:140]}", model)
        except ValueError as exc:
            upstream_status = 502
            structured = structure_freeform_ai_reply(reply, base_result, model=model)
            if structured.get("status") == "local_fallback":
                structured["message"] = f"AI 洞察返回格式异常，已使用本地结构化规则兜底：{str(exc)[:80]}"
            return structured
        except Exception as exc:
            upstream_status = 500
            logger.warning("Fengshui AI insight generation failed: %s", str(exc))
            return _empty_insights("error", f"AI 洞察生成失败：{str(exc)[:140]}", model)
        finally:
            elapsed_ms = (time.perf_counter() - started_at) * 1000.0
            try:
                await record_api_call(
                    username=identity["username"],
                    role=identity["role"],
                    endpoint=AI_INSIGHTS_ENDPOINT,
                    status_code=upstream_status,
                    response_time_ms=float(max(0.0, elapsed_ms)),
                    request_params=json.dumps(
                        {
                            "model": model,
                            "model_source": runtime.get("model_source"),
                            "api_key_source": runtime.get("api_key_source"),
                            "quota_subject": identity["quota_subject"],
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception as log_exc:
                logger.warning("Failed to record fengshui AI call: %s", str(log_exc))
    except Exception as exc:
        logger.warning("Fengshui AI runtime resolve failed: %s", str(exc))
        return _empty_insights("error", f"AI 洞察配置读取失败：{str(exc)[:140]}")


def _has_minimum_insight_fields(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("summary") or "").strip():
        return True
    for key in ("pattern_insights", "risk_notes", "planning_suggestions", "culture_notes"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False
