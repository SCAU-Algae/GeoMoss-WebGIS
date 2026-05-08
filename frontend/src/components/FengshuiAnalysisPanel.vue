<template>
  <div class="fengshui-analysis-panel">
    <section class="analysis-hero">
      <div>
        <div class="eyebrow">山水明堂</div>
        <h3>风水环境格局分析</h3>
        <p>基于 DEM 地形、水系关系和透明规则评分生成文化解读，不做吉凶预测。</p>
      </div>
      <div class="score-orbit" :class="{ muted: !result }">
        <strong>{{ overallScoreText }}</strong>
        <span>{{ result?.score_level || '待分析' }}</span>
      </div>
    </section>

    <section class="analysis-card">
      <div class="section-title">
        <scan-search-icon :size="16" />
        <span>研究范围</span>
      </div>
      <div class="mode-grid">
        <button
          v-for="item in modeOptions"
          :key="item.id"
          type="button"
          class="mode-button"
          :class="{ active: mode === item.id }"
          :disabled="drawing"
          @click="mode = item.id"
        >
          <component :is="item.icon" :size="16" />
          <span>{{ item.label }}</span>
        </button>
      </div>

      <div v-if="mode === 'circle'" class="field-grid">
        <label class="field-line">
          中心经度
          <input v-model.number="circleCenter.lon" class="panel-input" type="number" step="0.000001" />
        </label>
        <label class="field-line">
          中心纬度
          <input v-model.number="circleCenter.lat" class="panel-input" type="number" step="0.000001" />
        </label>
        <label class="field-line span-2">
          分析半径 {{ radiusLabel }}
          <input v-model.number="radiusM" class="panel-input" type="range" min="100" max="20000" step="100" />
        </label>
      </div>

      <div v-else class="draw-mode-box">
        <div class="draw-type-row">
          <button
            v-for="item in drawTypeOptions"
            :key="item.id"
            type="button"
            class="draw-type-button"
            :class="{ active: drawType === item.id }"
            :disabled="drawing"
            @click="handleDrawTypeChange(item.id)"
          >
            {{ item.label }}
          </button>
        </div>
        <button class="secondary-action full-width" type="button" :disabled="drawing" @click="pickStudyArea">
          <loader-2-icon v-if="drawing" :size="16" class="spin" />
          <scan-search-icon v-else :size="16" />
          {{ drawing ? '等待框选' : '在地图上框选范围' }}
        </button>
        <div class="study-area-summary" :class="{ empty: !studyAreaGeojson }">
          {{ studyAreaSummaryText }}
        </div>
      </div>

      <div class="action-row">
        <button class="secondary-action" type="button" :disabled="mode !== 'circle'" @click="useMapCenter">
          <crosshair-icon :size="16" />
          当前地图中心
        </button>
        <button class="primary-action" type="button" :class="{ busy: loading }" :disabled="analysisDisabled" @click="runAnalysis">
          <loader-2-icon v-if="loading" :size="16" class="spin" />
          <sparkles-icon v-else :size="16" />
          {{ loading ? '分析中' : '开始分析' }}
        </button>
      </div>
    </section>

    <section class="status-strip" :class="{ warning: !status?.dem?.available }">
      <database-icon :size="15" />
      <span>{{ dataStatusText }}</span>
    </section>

    <section v-if="result?.ai_insights" class="ai-status-strip" :class="{ muted: !result.ai_insights.available }">
      <sparkles-icon :size="15" />
      <span>{{ aiStatusText }}</span>
    </section>

    <section v-if="result" class="analysis-card">
      <div class="section-title">
        <radar-icon :size="16" />
        <span>格局评分</span>
      </div>
      <div class="report-summary">
        <div class="summary-emblem">
          <component :is="scoreLevelIcon" :size="24" />
        </div>
        <div>
          <span>综合判断</span>
          <strong>{{ overallScoreText }} / 100 · {{ result?.score_level || '待分析' }}</strong>
          <p>{{ reportLeadText }}</p>
        </div>
      </div>
      <div class="score-grid">
        <div v-for="item in scoreRows" :key="item.key" class="score-card">
          <component :is="item.icon" :size="18" />
          <div>
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
          <div class="mini-bar"><i :style="{ width: `${item.value}%` }"></i></div>
        </div>
      </div>
    </section>

    <section v-if="result" class="analysis-card evidence-card">
      <div class="section-title">
        <satellite-icon :size="16" />
        <span>证据增强</span>
      </div>
      <div class="evidence-grid">
        <div class="evidence-item" :class="{ muted: !visualWater.available }">
          <div class="evidence-head">
            <scan-eye-icon :size="18" />
            <strong>视觉水体</strong>
            <span>{{ visualWaterStatusLabel }}</span>
          </div>
          <p>{{ visualWaterText }}</p>
          <div v-if="visualWater.available" class="evidence-tags">
            <span>{{ directionLabel(visualWater.dominant_direction) }}</span>
            <span>{{ sizeLabel(visualWater.relative_size) }}</span>
            <span>{{ confidenceLabel(visualWater.confidence) }}</span>
          </div>
        </div>
        <div class="evidence-item" :class="{ muted: !locationContext.available }">
          <div class="evidence-head">
            <map-pinned-icon :size="18" />
            <strong>地理语义</strong>
            <span>{{ locationContext.available ? '已接入' : '未接入' }}</span>
          </div>
          <p>{{ locationContextText }}</p>
          <div v-if="poiCategoryTags.length" class="evidence-tags">
            <span v-for="item in poiCategoryTags" :key="item">{{ item }}</span>
          </div>
        </div>
      </div>
      <div v-if="evidenceConflictTexts.length" class="conflict-box">
        <shield-alert-icon :size="16" />
        <div>
          <strong>证据复核</strong>
          <p v-for="item in evidenceConflictTexts" :key="item">{{ item }}</p>
        </div>
      </div>
    </section>

    <section v-if="result" class="analysis-card">
      <div class="section-title">
        <mountain-icon :size="16" />
        <span>地形指标</span>
      </div>
      <div class="metric-grid">
        <div v-for="item in metricRows" :key="item.key" class="metric-row">
          <component :is="item.icon" :size="18" />
          <div>
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <em>{{ item.note }}</em>
          </div>
        </div>
      </div>
    </section>

    <section v-if="result" class="analysis-card">
      <div class="section-title">
        <waves-icon :size="16" />
        <span>山水解释</span>
      </div>
      <div class="pattern-list">
        <div v-for="item in patternRows" :key="item.key" class="pattern-row">
          <component :is="item.icon" :size="18" />
          <div>
            <span>{{ item.label }}</span>
            <p>{{ item.value }}</p>
          </div>
        </div>
      </div>
    </section>

    <section v-if="result?.ai_insights?.available" class="analysis-card ai-insight-card">
      <div class="section-title">
        <brain-circuit-icon :size="16" />
        <span>AI 深度洞察</span>
      </div>
      <div class="ai-summary">
        <sparkles-icon :size="19" />
        <p>{{ result.ai_insights.summary || 'AI 已完成补充分析。' }}</p>
        <span>{{ aiConfidenceText }}</span>
      </div>
      <div v-if="aiContextRows.length" class="ai-context-grid">
        <div v-for="row in aiContextRows" :key="row.label">
          <span>{{ row.label }}</span>
          <p>{{ row.value }}</p>
        </div>
      </div>
      <div class="ai-insight-grid">
        <div v-for="group in aiInsightGroups" :key="group.key" class="ai-insight-group">
          <div class="ai-group-title">
            <component :is="group.icon" :size="16" />
            <span>{{ group.label }}</span>
          </div>
          <ul>
            <li v-for="item in group.items" :key="item">{{ item }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section v-if="result" class="analysis-card">
      <div class="section-title">
        <list-checks-icon :size="16" />
        <span>整理建议</span>
      </div>
      <ol class="recommendation-list">
        <li v-for="item in result.recommendations || []" :key="item">
          <check-circle-2-icon :size="17" />
          <span>{{ item }}</span>
        </li>
      </ol>
    </section>

    <section v-if="result" class="analysis-card report-card">
      <div class="section-title">
        <file-text-icon :size="16" />
        <span>完整报告</span>
      </div>
      <p>{{ result.report }}</p>
      <small>{{ result.disclaimer }}</small>
    </section>

    <section v-else class="empty-state">
      <compass-icon :size="28" />
      <span>选择范围后开始分析，结果会在这里展开。</span>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import {
  Aperture as ApertureIcon,
  BrainCircuit as BrainCircuitIcon,
  Circle as CircleIcon,
  CheckCircle2 as CheckCircle2Icon,
  Compass as CompassIcon,
  Crosshair as CrosshairIcon,
  Database as DatabaseIcon,
  Eye as EyeIcon,
  FileText as FileTextIcon,
  Gauge as GaugeIcon,
  Gem as GemIcon,
  Loader2 as Loader2Icon,
  ListChecks as ListChecksIcon,
  MapPinned as MapPinnedIcon,
  Mountain as MountainIcon,
  Route as RouteIcon,
  Pentagon as PentagonIcon,
  Radar as RadarIcon,
  Satellite as SatelliteIcon,
  ShieldAlert as ShieldAlertIcon,
  ScanEye as ScanEyeIcon,
  ScanSearch as ScanSearchIcon,
  Sparkles as SparklesIcon,
  SunMedium as SunMediumIcon,
  TrendingUp as TrendingUpIcon,
  Waves as WavesIcon
} from 'lucide-vue-next';
import { apiAnalyzeFengshui, apiFengshuiStatus } from '../api/fengshui';
import { useMessage } from '../composables/useMessage';

const props = defineProps({
  active: { type: Boolean, default: true },
  getMapCenter: { type: Function, default: null },
  startStudyAreaDraw: { type: Function, default: null }
});

const message = useMessage();
const loading = ref(false);
const drawing = ref(false);
const status = ref(null);
const result = ref(null);
const mode = ref('circle');
const circleCenter = reactive({ lon: 113.351948, lat: 23.160345 });
const radiusM = ref(1500);
const drawType = ref('Polygon');
const studyAreaGeojson = ref(null);
const studyAreaMeta = ref(null);

const modeOptions = [
  { id: 'circle', label: '中心半径', icon: CircleIcon },
  { id: 'geojson', label: '地图绘制', icon: PentagonIcon }
];

const drawTypeOptions = [
  { id: 'Polygon', label: '多边形' },
  { id: 'Rectangle', label: '矩形' },
  { id: 'Circle', label: '圆形' }
];

const radiusLabel = computed(() => {
  const value = Number(radiusM.value || 0);
  return value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value.toFixed(0)} m`;
});

const overallScoreText = computed(() => {
  const score = result.value?.scores?.overall_score;
  return Number.isFinite(Number(score)) ? String(score) : '--';
});

const dataStatusText = computed(() => {
  if (!status.value) return '正在读取 DEM 与水系数据状态...';
  const demText = status.value.dem?.available ? 'DEM 已就绪' : 'DEM 不可用，将降级为模拟指标';
  const waterText = status.value.water?.available ? '水系已接入' : '水系未接入';
  const aiText = status.value.ai?.available ? 'AI 洞察可用' : 'AI 洞察未配置';
  return `${demText} / ${waterText} / ${aiText}`;
});

const aiStatusText = computed(() => {
  const ai = result.value?.ai_insights;
  if (!ai) return 'AI 洞察未请求';
  if (ai.available) {
    const modelText = ai.model ? `（${ai.model}）` : '';
    return `AI 洞察已生成${modelText}`;
  }
  return ai.message || 'AI 洞察暂不可用，基础分析结果仍可使用';
});

const aiConfidenceText = computed(() => {
  const confidence = String(result.value?.ai_insights?.confidence || 'medium');
  const map = { high: '高置信', medium: '中等置信', low: '低置信' };
  return map[confidence] || '中等置信';
});

const visualWater = computed(() => result.value?.visual_water || result.value?.data_status?.visual_water || {});

const locationContext = computed(() => result.value?.location_context || {});

const evidenceConflictTexts = computed(() => {
  const direct = result.value?.evidence_conflicts || [];
  const aiConflicts = result.value?.ai_insights?.evidence_conflicts || [];
  const items = [
    ...direct.map((item) => item?.message || item).filter(Boolean),
    ...aiConflicts
  ];
  return [...new Set(items.map((item) => String(item || '').trim()).filter(Boolean))].slice(0, 3);
});

const visualWaterStatusLabel = computed(() => {
  const visual = visualWater.value || {};
  if (!visual.available) return visual.status === 'unconfigured' ? '未配置' : '不可用';
  const presence = String(visual.water_presence || '');
  if (presence === 'clear') return '明确识别';
  if (presence === 'possible') return '可能存在';
  if (presence === 'none') return '未见明显水体';
  return '已完成';
});

const visualWaterText = computed(() => {
  const visual = visualWater.value || {};
  if (!visual.available) return visual.message || '千问视觉未返回可用结果，当前仍保留 DEM 与矢量水系分析。';
  const types = Array.isArray(visual.water_types) && visual.water_types.length
    ? visual.water_types.map(waterTypeLabel).join('、')
    : '水体';
  const shape = String(visual.shape_pattern || '').trim();
  const base = visual.water_presence === 'none'
    ? '视觉模型未识别到明显水体。'
    : `视觉模型识别到${types}，主要位于${directionLabel(visual.dominant_direction)}，规模为${sizeLabel(visual.relative_size)}。`;
  return shape ? `${base}${shape}` : base;
});

const locationContextText = computed(() => {
  const location = locationContext.value || {};
  if (!location.available) return location.message || '高德地理语义未返回可用结果。';
  const address = String(location.formatted_address || '').trim();
  const categories = poiCategoryTags.value.slice(0, 4).join('、');
  if (address && categories) return `${address}附近，周边主要包含${categories}等要素。`;
  if (address) return `${address}附近。`;
  if (categories) return `周边主要包含${categories}等要素。`;
  return location.message || '已获取位置语义。';
});

const poiCategoryTags = computed(() => {
  const categories = locationContext.value?.poi_categories || [];
  return categories
    .map((item) => item?.name || item)
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .slice(0, 6);
});

const aiContextRows = computed(() => {
  const ai = result.value?.ai_insights || {};
  return [
    { label: '位置语义', value: ai.location_context_summary },
    { label: '视觉水体', value: ai.visual_water_interpretation },
  ].filter((item) => String(item.value || '').trim());
});

const studyAreaSummaryText = computed(() => {
  if (!studyAreaGeojson.value) return '尚未框选研究范围';
  const bbox = studyAreaMeta.value?.bbox || [];
  if (bbox.length >= 4) {
    return `已框选范围：${Number(bbox[0]).toFixed(4)}, ${Number(bbox[1]).toFixed(4)} 至 ${Number(bbox[2]).toFixed(4)}, ${Number(bbox[3]).toFixed(4)}`;
  }
  return '已框选研究范围';
});

const analysisDisabled = computed(() => {
  if (loading.value || drawing.value) return true;
  return mode.value === 'geojson' && !studyAreaGeojson.value;
});

const scoreLevelIcon = computed(() => {
  const level = String(result.value?.score_level || '');
  if (/优|佳|良/.test(level)) return GemIcon;
  if (/中|平/.test(level)) return GaugeIcon;
  return ApertureIcon;
});

const reportLeadText = computed(() => {
  const area = result.value?.area_info;
  if (!area) return '完成分析后，这里会汇总研究范围、地形格局和水系关系。';
  const km2 = Number(area.area_m2 || 0) / 1000000;
  const areaText = Number.isFinite(km2) && km2 > 0 ? `${km2.toFixed(2)} km²` : '当前范围';
  return `本次研究范围约 ${areaText}，系统已综合地形起伏、坡向开敞度和水系关系生成下列判断。`;
});

const scoreRows = computed(() => {
  const scores = result.value?.scores || {};
  return [
    { key: 'overall_score', label: '综合', value: Number(scores.overall_score || 0), icon: SparklesIcon },
    { key: 'back_mountain_score', label: '靠山', value: Number(scores.back_mountain_score || 0), icon: MountainIcon },
    { key: 'front_open_score', label: '明堂', value: Number(scores.front_open_score || 0), icon: EyeIcon },
    { key: 'enclosure_score', label: '藏风', value: Number(scores.enclosure_score || 0), icon: CompassIcon },
    { key: 'water_score', label: '得水', value: Number(scores.water_score || 0), icon: WavesIcon },
    { key: 'terrain_stability_score', label: '稳定', value: Number(scores.terrain_stability_score || 0), icon: GaugeIcon }
  ];
});

const metricRows = computed(() => {
  const metrics = result.value?.terrain_metrics || {};
  const explanations = result.value?.metric_explanations || {};
  return [
    { key: 'mean_elevation', label: '平均高程', value: `${metrics.mean_elevation ?? '--'} m`, note: explanations.mean_elevation, icon: MountainIcon },
    { key: 'relief', label: '相对高差', value: `${metrics.relief ?? '--'} m`, note: explanations.relief, icon: TrendingUpIcon },
    { key: 'mean_slope', label: '平均坡度', value: `${metrics.mean_slope ?? '--'} deg`, note: explanations.mean_slope, icon: RouteIcon },
    { key: 'dominant_aspect', label: '主要坡向', value: metrics.dominant_aspect || '--', note: explanations.dominant_aspect, icon: CompassIcon },
    { key: 'terrain_roughness', label: '粗糙度', value: metrics.terrain_roughness ?? '--', note: explanations.terrain_roughness, icon: GaugeIcon }
  ];
});

const patternRows = computed(() => {
  const pattern = result.value?.spatial_pattern || {};
  return [
    { key: 'back_mountain', label: '靠山', value: pattern.back_mountain, icon: MountainIcon },
    { key: 'front_open', label: '明堂', value: pattern.front_open, icon: EyeIcon },
    { key: 'left_right_enclosure', label: '藏风', value: pattern.left_right_enclosure, icon: MapPinnedIcon },
    { key: 'water_relation', label: '得水', value: pattern.water_relation, icon: WavesIcon },
    { key: 'aspect_light', label: '采光', value: pattern.aspect_light, icon: SunMediumIcon }
  ].filter((item) => item.value);
});

const aiInsightGroups = computed(() => {
  const ai = result.value?.ai_insights || {};
  return [
    { key: 'pattern_insights', label: '格局洞察', items: ai.pattern_insights || [], icon: CompassIcon },
    { key: 'risk_notes', label: '复核风险', items: ai.risk_notes || [], icon: ShieldAlertIcon },
    { key: 'planning_suggestions', label: '整理策略', items: ai.planning_suggestions || [], icon: ListChecksIcon },
    { key: 'culture_notes', label: '文化解释', items: ai.culture_notes || [], icon: BrainCircuitIcon }
  ].filter((group) => group.items.length);
});

function directionLabel(value) {
  const map = {
    north: '北侧',
    northeast: '东北侧',
    east: '东侧',
    southeast: '东南侧',
    south: '南侧',
    southwest: '西南侧',
    west: '西侧',
    northwest: '西北侧',
    center: '范围内部',
    multiple: '多方向',
    unknown: '方位不明',
  };
  return map[String(value || '').toLowerCase()] || '方位不明';
}

function sizeLabel(value) {
  const map = {
    none: '无明显',
    small: '小尺度',
    medium: '中等尺度',
    large: '大尺度',
    unknown: '尺度不明',
  };
  return map[String(value || '').toLowerCase()] || '尺度不明';
}

function confidenceLabel(value) {
  const map = { high: '高置信', medium: '中等置信', low: '低置信' };
  return map[String(value || '').toLowerCase()] || '中等置信';
}

function waterTypeLabel(value) {
  const map = {
    river: '河流',
    lake: '湖泊',
    pond: '池塘',
    canal: '沟渠',
    reservoir: '水库',
    wetland: '湿地',
    coast: '海岸水域',
    unknown: '水体',
  };
  return map[String(value || '').toLowerCase()] || '水体';
}

async function loadStatus() {
  try {
    const response = await apiFengshuiStatus();
    status.value = response?.data || response || null;
  } catch (error) {
    message.warning(error?.message || '风水分析数据状态读取失败');
  }
}

function useMapCenter() {
  const center = props.getMapCenter?.();
  if (!center) {
    message.warning('地图中心暂不可用');
    return;
  }
  circleCenter.lon = Number(center.lon || center.lng || circleCenter.lon);
  circleCenter.lat = Number(center.lat || circleCenter.lat);
}

function handleDrawTypeChange(nextType) {
  drawType.value = nextType;
  studyAreaGeojson.value = null;
  studyAreaMeta.value = null;
}

async function pickStudyArea() {
  if (!props.active) {
    message.warning('请先打开风水分析面板再框选范围');
    return;
  }
  if (typeof props.startStudyAreaDraw !== 'function') {
    message.warning('地图框选能力尚未就绪');
    return;
  }
  drawing.value = true;
  try {
    const payload = await props.startStudyAreaDraw(drawType.value);
    studyAreaGeojson.value = payload?.geojson || null;
    studyAreaMeta.value = payload || null;
    if (!studyAreaGeojson.value) {
      message.warning('未获取到有效框选范围');
      return;
    }
    message.success('已获取地图框选范围');
  } catch (error) {
    const detail = String(error?.message || '').trim();
    if (!/取消|cancel/i.test(detail)) {
      message.warning(detail || '地图框选未完成');
    }
  } finally {
    drawing.value = false;
  }
}

async function runAnalysis() {
  if (mode.value === 'geojson') {
    if (!studyAreaGeojson.value) {
      message.warning('请先在地图上框选研究范围');
      return;
    }
    loading.value = true;
    try {
      const response = await apiAnalyzeFengshui({
        mode: 'geojson',
        geojson: studyAreaGeojson.value,
        include_ai: true,
        include_visual: true,
        include_location_context: true
      });
      result.value = response?.data || response || null;
      message.success('风水环境格局分析完成');
    } catch (error) {
      message.error(error?.message || '风水分析失败');
    } finally {
      loading.value = false;
    }
    return;
  }

  const lon = Number(circleCenter.lon);
  const lat = Number(circleCenter.lat);
  const radius = Number(radiusM.value);
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || lon < -180 || lon > 180 || lat < -90 || lat > 90) {
    message.warning('请输入有效经纬度');
    return;
  }
  if (!Number.isFinite(radius) || radius < 20 || radius > 200000) {
    message.warning('请输入有效分析半径');
    return;
  }

  loading.value = true;
  try {
    const response = await apiAnalyzeFengshui({
      mode: 'circle',
      center: { lon, lat },
      radius_m: radius,
      include_ai: true,
      include_visual: true,
      include_location_context: true
    });
    result.value = response?.data || response || null;
    if (result.value?.data_status?.dem && !result.value.data_status.dem.available) {
      message.warning(result.value.data_status.dem.message || 'DEM 不可用，已使用模拟指标');
    } else {
      message.success('风水环境格局分析完成');
    }
  } catch (error) {
    message.error(error?.message || '风水分析失败');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadStatus();
  useMapCenter();
});
</script>

<style scoped>
.fengshui-analysis-panel {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  color: var(--text-primary);
}

.analysis-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 96px;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background:
    linear-gradient(135deg, rgba(71, 215, 198, 0.14), rgba(255, 255, 255, 0.035)),
    rgba(255, 255, 255, 0.04);
}

.eyebrow {
  font-size: 11px;
  color: var(--neon-cyan);
  letter-spacing: 0;
  margin-bottom: 4px;
}

.analysis-hero h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
}

.analysis-hero p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.score-orbit {
  aspect-ratio: 1;
  border-radius: 50%;
  display: grid;
  place-items: center;
  align-content: center;
  border: 1px solid rgba(71, 215, 198, 0.45);
  background: rgba(71, 215, 198, 0.1);
  box-shadow: inset 0 0 24px rgba(71, 215, 198, 0.12);
}

.score-orbit strong {
  font-size: 27px;
  color: var(--neon-cyan);
  line-height: 1;
}

.score-orbit span {
  font-size: 11px;
  color: var(--text-secondary);
}

.score-orbit.muted {
  opacity: 0.68;
}

.analysis-card,
.status-strip,
.ai-status-strip,
.empty-state {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.045);
}

.analysis-card {
  padding: 14px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--neon-cyan);
  font-size: 14px;
  font-weight: 700;
  margin-bottom: 12px;
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.mode-button,
.draw-type-button,
.secondary-action,
.primary-action {
  min-height: 38px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  cursor: pointer;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.045);
  transition: background var(--duration-fast) var(--ease-spatial), border-color var(--duration-fast) var(--ease-spatial), color var(--duration-fast) var(--ease-spatial);
}

.mode-button.active,
.draw-type-button.active,
.secondary-action:hover {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  background: var(--neon-cyan-dim);
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.field-line {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.span-2 {
  grid-column: span 2;
}

.panel-input {
  width: 100%;
  min-width: 0;
  height: 34px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  color: var(--text-primary);
  background: rgba(0, 0, 0, 0.2);
  box-sizing: border-box;
}

input[type="range"].panel-input {
  padding: 0;
  accent-color: var(--neon-cyan);
}

.draw-mode-box,
.coming-soon {
  padding: 12px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.035);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.draw-type-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.draw-type-button {
  min-height: 34px;
  font-size: 12px;
}

.full-width {
  width: 100%;
}

.study-area-summary {
  margin-top: 10px;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.14);
  font-size: 12px;
  line-height: 1.45;
}

.study-area-summary.empty {
  color: rgba(255, 255, 255, 0.45);
}

.action-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}

.primary-action {
  color: #031515;
  border-color: rgba(71, 215, 198, 0.82);
  background: linear-gradient(135deg, var(--neon-cyan), #9cf5e9);
  font-weight: 700;
}

.primary-action:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.primary-action.busy:disabled {
  cursor: wait;
}

.secondary-action:disabled,
.mode-button:disabled,
.draw-type-button:disabled {
  opacity: 0.52;
  cursor: not-allowed;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.status-strip {
  min-height: 38px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.status-strip.warning {
  color: #f6c86d;
  border-color: rgba(246, 200, 109, 0.28);
}

.ai-status-strip {
  min-height: 36px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--neon-cyan);
  font-size: 12px;
}

.ai-status-strip.muted {
  color: var(--text-secondary);
}

.score-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.report-summary {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid rgba(71, 215, 198, 0.24);
  border-radius: var(--radius-sm);
  background:
    linear-gradient(135deg, rgba(71, 215, 198, 0.12), rgba(255, 255, 255, 0.035)),
    rgba(0, 0, 0, 0.16);
}

.summary-emblem {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: var(--neon-cyan);
  border: 1px solid rgba(71, 215, 198, 0.38);
  background: rgba(71, 215, 198, 0.1);
  box-shadow: inset 0 0 20px rgba(71, 215, 198, 0.12);
}

.report-summary span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
}

.report-summary strong {
  display: block;
  margin-top: 2px;
  color: var(--text-primary);
  font-size: 19px;
  line-height: 1.25;
}

.report-summary p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.score-card {
  min-width: 0;
  padding: 11px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.14);
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.score-card > svg,
.metric-row > svg,
.pattern-row > svg,
.recommendation-list svg {
  flex: 0 0 auto;
  color: var(--neon-cyan);
  margin-top: 2px;
}

.score-card span,
.metric-row span,
.pattern-row span {
  color: var(--text-secondary);
  font-size: 12px;
}

.score-card strong {
  display: block;
  margin: 4px 0 8px;
  font-size: 21px;
  color: var(--text-primary);
  line-height: 1;
}

.mini-bar {
  grid-column: 1 / -1;
  height: 4px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.mini-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--neon-cyan);
}

.metric-grid,
.pattern-list {
  display: grid;
  gap: 10px;
}

.metric-row,
.pattern-row {
  min-width: 0;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.14);
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
}

.metric-row strong {
  display: block;
  margin-top: 3px;
  font-size: 17px;
  line-height: 1.25;
}

.metric-row em {
  display: block;
  margin-top: 6px;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.52));
  font-size: 13px;
  line-height: 1.58;
  font-style: normal;
}

.pattern-row p {
  margin: 6px 0 0;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.68;
}

.ai-insight-card {
  background:
    linear-gradient(135deg, rgba(71, 215, 198, 0.1), rgba(112, 137, 255, 0.08)),
    rgba(255, 255, 255, 0.045);
}

.evidence-card {
  background:
    linear-gradient(135deg, rgba(71, 215, 198, 0.08), rgba(255, 255, 255, 0.035)),
    rgba(255, 255, 255, 0.045);
}

.evidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.evidence-item {
  min-width: 0;
  padding: 12px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(71, 215, 198, 0.18);
  background: rgba(0, 0, 0, 0.16);
}

.evidence-item.muted {
  border-color: var(--border-subtle);
  opacity: 0.72;
}

.evidence-head {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  gap: 7px;
  align-items: center;
  color: var(--text-primary);
}

.evidence-head svg {
  color: var(--neon-cyan);
}

.evidence-head strong {
  font-size: 13px;
}

.evidence-head span {
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  color: var(--neon-cyan);
  background: rgba(71, 215, 198, 0.1);
  font-size: 11px;
  white-space: nowrap;
}

.evidence-item p {
  margin: 9px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.evidence-tags span {
  max-width: 100%;
  min-height: 22px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--border-subtle);
  font-size: 11px;
}

.conflict-box {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
  margin-top: 10px;
  padding: 11px;
  border-radius: var(--radius-sm);
  color: #f6c86d;
  border: 1px solid rgba(246, 200, 109, 0.26);
  background: rgba(246, 200, 109, 0.08);
}

.conflict-box svg {
  margin-top: 2px;
  flex: 0 0 auto;
}

.conflict-box strong {
  display: block;
  font-size: 13px;
}

.conflict-box p {
  margin: 5px 0 0;
  color: rgba(255, 232, 183, 0.88);
  font-size: 12px;
  line-height: 1.55;
}

.ai-summary {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 9px;
  align-items: start;
  padding: 12px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.16);
  border: 1px solid rgba(71, 215, 198, 0.22);
}

.ai-summary svg,
.ai-group-title svg {
  color: var(--neon-cyan);
  flex: 0 0 auto;
}

.ai-summary p {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.65;
}

.ai-summary span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  color: var(--neon-cyan);
  background: rgba(71, 215, 198, 0.1);
  font-size: 11px;
  white-space: nowrap;
}

.ai-context-grid {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.ai-context-grid div {
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(71, 215, 198, 0.16);
  background: rgba(0, 0, 0, 0.13);
}

.ai-context-grid span {
  display: block;
  color: var(--neon-cyan);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 5px;
}

.ai-context-grid p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.ai-insight-grid {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

.ai-insight-group {
  padding: 11px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.14);
}

.ai-group-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

.ai-insight-group ul {
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.ai-insight-group li + li {
  margin-top: 5px;
}

.recommendation-list {
  margin: 0;
  padding: 0;
  display: grid;
  gap: 9px;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.65;
  list-style: none;
}

.recommendation-list li {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
  padding: 10px;
  border-radius: var(--radius-sm);
  background: rgba(0, 0, 0, 0.14);
}

.report-card p {
  margin: 0;
  white-space: pre-line;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.75;
}

.report-card small {
  display: block;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.empty-state {
  min-height: 130px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: center;
}

@container (max-width: 380px) {
  .analysis-hero {
    grid-template-columns: 1fr;
  }

  .score-orbit {
    width: 88px;
    justify-self: start;
  }

  .field-grid,
  .score-grid,
  .evidence-grid,
  .action-row {
    grid-template-columns: 1fr;
  }

  .report-summary {
    grid-template-columns: 1fr;
  }

  .ai-summary {
    grid-template-columns: 24px minmax(0, 1fr);
  }

  .ai-summary span {
    grid-column: 2;
    justify-self: start;
  }

  .span-2 {
    grid-column: auto;
  }
}
</style>
