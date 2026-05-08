from typing import Any, Dict


def clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))


def calculate_scores(metrics: Dict[str, Any], water: Dict[str, Any]) -> Dict[str, int]:
    mean_slope = float(metrics.get("mean_slope", 0) or 0)
    max_slope = float(metrics.get("max_slope", 0) or 0)
    relief = float(metrics.get("relief", 0) or 0)
    roughness = float(metrics.get("terrain_roughness", 0) or 0)
    aspect = str(metrics.get("dominant_aspect") or "")

    back_mountain = clamp_score(66 + min(relief / 4, 22) - max(mean_slope - 16, 0) * 1.2)
    front_open = clamp_score(84 - mean_slope * 1.25 - roughness * 18)
    enclosure = clamp_score(68 + min(relief / 10, 16) - max(roughness - 0.45, 0) * 34)
    water_score = int(water.get("score", 60) or 60)
    aspect_light = 88 if aspect in {"南", "东南", "西南"} else 74 if aspect in {"东", "西"} else 58
    terrain_stability = clamp_score(94 - mean_slope * 1.65 - max(max_slope - 28, 0) * 1.15)

    raw_scores = {
        "back_mountain_score": back_mountain,
        "front_open_score": front_open,
        "enclosure_score": enclosure,
        "water_score": water_score,
        "aspect_light_score": aspect_light,
        "terrain_stability_score": terrain_stability,
    }
    weights = {
        "back_mountain_score": 0.2,
        "front_open_score": 0.18,
        "enclosure_score": 0.16,
        "water_score": 0.13,
        "aspect_light_score": 0.15,
        "terrain_stability_score": 0.18,
    }
    if bool(water.get("is_placeholder", True)):
        weights.pop("water_score", None)

    total_weight = sum(weights.values()) or 1
    overall = clamp_score(sum(raw_scores[key] * weight for key, weight in weights.items()) / total_weight)
    raw_scores["overall_score"] = overall
    return raw_scores


def score_level(score: int) -> str:
    if score >= 85:
        return "优"
    if score >= 70:
        return "良"
    if score >= 55:
        return "可优化"
    return "需谨慎"
