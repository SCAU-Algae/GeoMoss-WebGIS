from typing import Any, Dict, List

from .scoring import score_level


DISCLAIMER = (
    "本分析基于地理空间数据、DEM 地形指标和传统环境文化解释生成，"
    "仅用于 WebGIS 技术实践、环境格局观察与民俗文化娱乐参考；"
    "不构成投资、购房、经营、医疗、婚姻、法律或商业选址建议。"
)


def build_spatial_pattern(metrics: Dict[str, Any], water: Dict[str, Any]) -> Dict[str, str]:
    slope = float(metrics.get("mean_slope", 0) or 0)
    relief = float(metrics.get("relief", 0) or 0)
    aspect = str(metrics.get("dominant_aspect") or "")
    back = "地形起伏较明显，可形成一定背景支撑。" if relief >= 80 else "地形起伏温和，靠山格局更多依赖周边更大尺度地势。"
    front = "坡度较缓，前场开敞和活动面组织条件较好。" if slope < 10 else "坡度偏大，明堂开阔度需结合场地平整与视线遮挡复核。"
    enclosure = "左右围合以地形高差和边界组织为主，适合后续叠加建筑/植被数据增强判断。"
    light = f"主要坡向为{aspect or '未识别'}，采光潜力需结合建筑遮挡、山体遮挡和季节太阳高度复核。"
    return {
        "back_mountain": back,
        "front_open": front,
        "left_right_enclosure": enclosure,
        "water_relation": str(water.get("message") or ""),
        "aspect_light": light,
    }


def build_recommendations(metrics: Dict[str, Any], scores: Dict[str, int], water: Dict[str, Any]) -> List[str]:
    recommendations: List[str] = []
    if float(metrics.get("mean_slope", 0) or 0) <= 10:
        recommendations.append("保持现有缓坡或台地形态，减少大挖大填，优先保留自然排水方向。")
    else:
        recommendations.append("坡度偏大，先做边坡稳定、排水组织和步行可达性复核，再谈空间文化优化。")

    if scores.get("front_open_score", 0) >= 75:
        recommendations.append("前场开阔度较好，入口和院前空间宜保持整洁、明亮、少遮挡。")
    else:
        recommendations.append("前场舒展度一般，可通过控制围挡高度、清理动线和优化开口方向改善明堂观感。")

    if bool(water.get("is_placeholder", True)):
        recommendations.append("当前缺少真实水系数据，建议后续接入河流、湖泊、沟渠和排水口图层。")
    elif bool(water.get("intersects", False)):
        recommendations.append("水体与研究范围相交时，不应只按文化吉象解读，需优先核验洪涝、退让和建设管控。")
    else:
        recommendations.append("已识别水系距离和方向，可作为亲水环境参考，但仍需结合洪水位和排水安全。")

    recommendations.append("若要提升“纳气聚气”的空间感，优先顺序是入口顺畅、前场清爽、水路清楚、边界适度。")
    return recommendations


def build_report(
    area_info: Dict[str, Any],
    metrics: Dict[str, Any],
    pattern: Dict[str, str],
    scores: Dict[str, int],
    water: Dict[str, Any],
) -> str:
    recommendations = build_recommendations(metrics, scores, water)
    return "\n\n".join([
        "一、研究范围\n"
        f"本次分析范围面积约 {area_info.get('area_m2')} 平方米，中心点为 "
        f"{area_info.get('center_lon')}, {area_info.get('center_lat')}。",
        "二、地形概况\n"
        f"平均高程 {metrics.get('mean_elevation')} m，最高 {metrics.get('max_elevation')} m，"
        f"最低 {metrics.get('min_elevation')} m，相对高差 {metrics.get('relief')} m；"
        f"平均坡度 {metrics.get('mean_slope')} deg，主要坡向 {metrics.get('dominant_aspect')}。",
        "三、山水格局\n"
        f"靠山：{pattern.get('back_mountain')}\n"
        f"明堂：{pattern.get('front_open')}\n"
        f"藏风：{pattern.get('left_right_enclosure')}\n"
        f"得水：{pattern.get('water_relation')}",
        "四、综合评价\n"
        f"综合评分 {scores.get('overall_score')} 分，等级为 {score_level(scores.get('overall_score', 0))}。"
        "该评分来自透明规则指标，用于横向比较和提示，不是吉凶断语。",
        "五、整理建议\n" + "\n".join(f"{index + 1}. {item}" for index, item in enumerate(recommendations)),
        "六、免责声明\n" + DISCLAIMER,
    ])


def build_metric_explanations() -> Dict[str, str]:
    return {
        "mean_elevation": "描述场地整体海拔背景，可辅助判断视野、排水和区域地势关系。",
        "relief": "描述范围内最高点和最低点的差值，高差适中更容易形成空间层次。",
        "mean_slope": "描述地表倾斜程度，坡度越大越需要关注建设、安全和雨水径流。",
        "dominant_aspect": "描述主要坡向，对日照、通风、湿度和传统朝向解释均有影响。",
        "terrain_roughness": "描述地形破碎程度，粗糙度高通常意味着整理成本和排水复杂度更高。",
        "water_score": "描述水体距离、方向和相交关系；缺少水系数据时只显示中性占位。",
    }
