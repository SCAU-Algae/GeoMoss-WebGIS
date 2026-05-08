<template>
  <FloatingPanelFrame
    v-model:open="open"
    class="cesium-tools-frame"
    title="三维工具"
    subtitle="测量、样式、地形与视角"
    launcher-label="3D"
    :default-width="390"
    :default-height="620"
    :min-width="320"
    :min-height="168"
    :dock-gap="72"
    dock-side="right"
    :dock-top="92"
    launcher-side="right"
    launcher-top="88%"
  >
    <div class="cesium-tools-shell">
      <div class="tool-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          class="tool-tab"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          <component :is="tab.icon" :size="15" />
          <span>{{ tab.label }}</span>
        </button>
      </div>

      <section v-show="activeTab === 'measure'" class="tool-section">
        <div class="button-grid">
          <button v-for="tool in measureTools" :key="tool.id" class="tool-button" :class="{ active: registryState.activeToolId === tool.id }" @click="activate(tool.id)">
            <component :is="tool.icon" :size="16" />
            <span>{{ tool.label }}</span>
          </button>
        </div>
        <div class="result-list">
          <div v-if="!registryState.measurements.length" class="empty-line">暂无测量结果</div>
          <div v-for="item in registryState.measurements" :key="item.id" class="result-row">
            <span>{{ item.label }}</span>
            <em>{{ item.createdAt }}</em>
          </div>
        </div>
      </section>

      <section v-show="activeTab === 'style'" class="tool-section">
        <label class="field-line">
          样式模式
          <select v-model="styleSettings.mode" class="tool-input" @change="applyStyle({ notify: false })">
            <option value="height">高度分级</option>
            <option value="solid">统一颜色</option>
          </select>
        </label>
        <label v-if="styleSettings.mode === 'solid'" class="field-line">
          统一颜色
          <input v-model="styleSettings.solidColor" class="tool-input color-input" type="color" @input="applyStyle({ notify: false })" />
        </label>
        <label v-if="styleSettings.mode === 'height'" class="field-line">
          高度字段
          <select v-model="styleSettings.heightField" class="tool-input" @change="applyStyle({ notify: false })">
            <option v-for="field in numericPropertyFields" :key="field" :value="field">{{ field }}</option>
          </select>
        </label>
        <label class="field-line">
          色带
          <select v-model="styleSettings.ramp" class="tool-input" @change="applyStyle({ notify: false })">
            <option value="cyan">青蓝</option>
            <option value="height">绿黄红</option>
            <option value="warm">暖色</option>
            <option value="mono">蓝紫</option>
          </select>
        </label>
        <label class="field-line">
          透明度 {{ Math.round(styleSettings.opacity * 100) }}%
          <input v-model.number="styleSettings.opacity" class="tool-input" type="range" min="0.08" max="1" step="0.02" @input="applyStyle({ notify: false })" />
        </label>
        <label class="check-line">
          <input v-model="styleSettings.outline" type="checkbox" @change="applyStyle({ notify: false })" />
          显示瓦片描边
        </label>
        <label class="field-line">
          筛选字段
          <select v-model="styleSettings.filterField" class="tool-input" @change="applyStyle({ notify: false })">
            <option value="">不筛选</option>
            <option v-for="field in availablePropertyFields" :key="field" :value="field">{{ field }}</option>
          </select>
        </label>
        <label v-if="styleSettings.filterField" class="field-line">
          筛选值
          <input v-model.trim="styleSettings.filterValue" class="tool-input" placeholder="输入字段值关键字" @change="applyStyle({ notify: false })" />
        </label>
        <p v-if="!availablePropertyFields.length" class="hint-text">当前白模还没有可用属性字段，点击建筑或重新发布带字段元数据的图层后可选择。</p>
        <div class="action-pair">
          <button class="primary-action" type="button" @click="applyStyle({ notify: true })">应用到可见白模</button>
          <button class="secondary-action" type="button" @click="resetStyle">重置</button>
        </div>
      </section>

      <section v-show="activeTab === 'draw'" class="tool-section">
        <div class="button-grid">
          <button v-for="tool in drawTools" :key="tool.id" class="tool-button" :class="{ active: registryState.activeToolId === tool.id }" @click="activate(tool.id)">
            <component :is="tool.icon" :size="16" />
            <span>{{ tool.label }}</span>
          </button>
        </div>
        <div class="result-list">
          <div v-if="!registryState.sketches.length" class="empty-line">暂无临时绘制</div>
          <div v-for="item in registryState.sketches" :key="item.id" class="result-row">
            <span>{{ item.label }} · {{ item.pointCount }} 点</span>
            <em>{{ item.createdAt }}</em>
          </div>
        </div>
      </section>

      <section v-show="activeTab === 'inspect'" class="tool-section">
        <div class="status-box">
          <strong>{{ loadingText }}</strong>
          <span>{{ registryState.statusText }}</span>
        </div>
        <div v-if="selectedRows.length" class="property-list">
          <div v-for="row in selectedRows" :key="row.key" class="property-row">
            <span>{{ row.key }}</span>
            <em>{{ row.value }}</em>
          </div>
        </div>
        <div v-else class="empty-line">点击建筑后显示属性</div>
        <button class="primary-action" type="button" @click="zoomToActive">定位当前 3D 图层</button>
      </section>

      <section v-show="activeTab === 'nav'" class="tool-section">
        <div class="nav-readout">
          <div class="compass-dial" :style="{ transform: `rotate(${-headingDeg}deg)` }"><navigation-icon :size="26" /></div>
          <div>
            <strong>{{ headingDeg.toFixed(0) }} deg</strong>
            <span>相机高度 {{ cameraHeightText }}</span>
          </div>
        </div>
        <div class="button-grid">
          <button class="tool-button" @click="flyToShenzhenView"><map-pin-icon :size="16" />深圳</button>
          <button class="tool-button" @click="flyToChinaView"><globe-icon :size="16" />全国</button>
          <button class="tool-button" @click="saveBookmark"><bookmark-plus-icon :size="16" />书签</button>
        </div>
        <div class="result-list">
          <div v-if="!registryState.bookmarks.length" class="empty-line">暂无相机书签</div>
          <button v-for="item in registryState.bookmarks" :key="item.id" class="bookmark-row" @click="restoreBookmark(item)">
            {{ item.name }}
          </button>
        </div>
      </section>

      <section v-show="activeTab === 'fx'" class="tool-section">
        <label class="check-line"><input v-model="effectSettings.fog" type="checkbox" @change="emitEffects" />雾效</label>
        <label class="check-line"><input v-model="effectSettings.bloom" type="checkbox" @change="emitEffects" />泛光/大气</label>
        <label class="check-line"><input v-model="effectSettings.hbao" type="checkbox" @change="emitEffects" />轮廓微阴影</label>
        <label class="check-line"><input v-model="effectSettings.tilt" type="checkbox" @change="emitEffects" />移轴景深</label>
        <p class="hint-text">视觉特效默认保持关闭或轻量状态，需要时手动启用。</p>
      </section>
    </div>
  </FloatingPanelFrame>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import {
  AreaChart as AreaIcon,
  BookmarkPlus as BookmarkPlusIcon,
  CircleDot as PointIcon,
  DraftingCompass as CompassIcon,
  Eye as EyeIcon,
  Globe as GlobeIcon,
  Layers3 as LayersIcon,
  LineChart as LineIcon,
  MapPin as MapPinIcon,
  Navigation as NavigationIcon,
  Pentagon as PolygonIcon,
  Ruler as RulerIcon,
  Sparkles as SparklesIcon,
  TrendingUp as HeightIcon,
  Trash2 as TrashIcon
} from 'lucide-vue-next';
import FloatingPanelFrame from '../FloatingPanelFrame.vue';
import { createCesiumFeatureRegistry } from '../../composables/cesium/useCesiumFeatureRegistry';
import { registerCesiumMeasurementTools } from '../../composables/cesium/features/useCesiumMeasurements';
import { registerCesiumSketchTools } from '../../composables/cesium/features/useCesiumSketchDrawing';
import { applyTilesetStyle, createDefaultTilesetStyleSettings, resetTilesetStyle } from '../../composables/cesium/features/useCesiumTilesetStyling';
import { attachCesiumFeaturePicking } from '../../composables/cesium/features/useCesiumFeaturePicking';
import { captureCameraBookmark, flyToBookmark, flyToChina, flyToShenzhen } from '../../composables/cesium/features/useCesiumNavigation';
import { useMessage } from '../../composables/useMessage';

const props = defineProps({
  getViewer: { type: Function, required: true },
  getCesium: { type: Function, required: true },
  getThreeDLayers: { type: Function, default: () => [] }
});

const emit = defineEmits(['style-change', 'effects-change', 'feature-select']);

const message = useMessage();
const open = ref(false);
const activeTab = ref('measure');
const headingDeg = ref(0);
const cameraHeight = ref(0);
const styleSettings = ref(createDefaultTilesetStyleSettings());
const effectSettings = ref({ fog: false, bloom: false, hbao: false, tilt: false });
const discoveredPropertyFields = ref([]);

const registry = createCesiumFeatureRegistry({
  getViewer: props.getViewer,
  getCesium: props.getCesium,
  message
});
const registryState = registry.state;

const tabs = [
  { id: 'measure', label: '测量', icon: RulerIcon },
  { id: 'style', label: '样式', icon: LayersIcon },
  { id: 'draw', label: '绘制', icon: PolygonIcon },
  { id: 'inspect', label: '属性', icon: EyeIcon },
  { id: 'nav', label: '视角', icon: CompassIcon },
  { id: 'fx', label: '特效', icon: SparklesIcon }
];

const measureTools = [
  { id: 'measure-distance', label: '距离', icon: RulerIcon },
  { id: 'measure-area', label: '面积', icon: AreaIcon },
  { id: 'measure-height', label: '高度', icon: HeightIcon },
  { id: 'measure-clear', label: '清空', icon: TrashIcon }
];

const drawTools = [
  { id: 'draw-point', label: '点', icon: PointIcon },
  { id: 'draw-line', label: '线', icon: LineIcon },
  { id: 'draw-polygon', label: '面', icon: PolygonIcon },
  { id: 'draw-clear', label: '清空', icon: TrashIcon }
];

const cameraHeightText = computed(() => {
  const value = Number(cameraHeight.value || 0);
  if (value >= 1000) return `${(value / 1000).toFixed(1)} km`;
  return `${value.toFixed(0)} m`;
});

const loadingText = computed(() => {
  const layers = props.getThreeDLayers?.() || [];
  const visible = layers.filter((item) => item.visible);
  const loading = visible.filter((item) => item.loading).length;
  return `图层：可见 ${visible.length} 个 / 加载中 ${loading} 个`;
});

const selectedRows = computed(() => {
  const propsMap = registryState.selectedFeature?.properties || {};
  return Object.entries(propsMap)
    .filter(([key]) => !String(key).startsWith('_'))
    .slice(0, 18)
    .map(([key, value]) => ({ key, value: typeof value === 'object' ? JSON.stringify(value) : String(value) }));
});

const availablePropertyFields = computed(() => {
  const fields = new Set(['name', 'height_m', 'width_m', 'depth_m', 'lon', 'lat']);
  visibleThreeDLayerRecords().forEach((layer) => {
    collectFieldNames(layer?.metadata).forEach((field) => fields.add(field));
    collectFieldNames(layer?.tileset?.metadata).forEach((field) => fields.add(field));
  });
  discoveredPropertyFields.value.forEach((field) => fields.add(field));
  Object.keys(registryState.selectedFeature?.properties || {}).forEach((field) => fields.add(field));
  return Array.from(fields).filter(Boolean).sort(fieldSort);
});

const numericPropertyFields = computed(() => {
  const preferred = ['height_m', 'width_m', 'depth_m', 'lon', 'lat'];
  const numericLike = availablePropertyFields.value.filter((field) => (
    preferred.includes(field)
    || /height|高度|floor|层|width|depth|area|count|lon|lat|x|y|z|elev|高程/i.test(field)
  ));
  return numericLike.length ? numericLike : ['height_m'];
});

let cameraTimer = null;
let pickingCleanup = null;

function activate(id) {
  registry.activateTool(id);
}

function visibleThreeDLayerRecords() {
  return (props.getThreeDLayers?.() || [])
    .filter((item) => item.visible && item.tileset && item.layerKind !== 'terrain');
}

function visibleTilesets() {
  return visibleThreeDLayerRecords().map((item) => item.tileset);
}

function collectFieldNames(value, bucket = new Set()) {
  if (!value) return bucket;
  if (Array.isArray(value)) {
    value.forEach((item) => {
      if (typeof item === 'string') bucket.add(item);
      else collectFieldNames(item, bucket);
    });
    return bucket;
  }
  if (typeof value !== 'object') return bucket;

  ['fields', 'source_fields', 'property_fields', 'properties'].forEach((key) => {
    if (!Array.isArray(value[key])) return;
    value[key].forEach((item) => {
      if (typeof item === 'string') bucket.add(item);
      else if (item?.name) bucket.add(String(item.name));
    });
  });

  if (value.source && typeof value.source === 'object') {
    Object.keys(value.source).forEach((key) => bucket.add(key));
  }

  return bucket;
}

function fieldSort(a, b) {
  const rank = (field) => {
    if (field === 'name' || field === '名称') return 0;
    if (field === 'height_m' || /height|高度/i.test(field)) return 1;
    if (field === 'batch_id') return 8;
    return 5;
  };
  const diff = rank(a) - rank(b);
  return diff || String(a).localeCompare(String(b), 'zh-CN');
}

function syncStyleFields() {
  const fields = availablePropertyFields.value;
  if (!fields.includes(styleSettings.value.heightField)) {
    styleSettings.value.heightField = numericPropertyFields.value[0] || 'height_m';
  }
  if (styleSettings.value.filterField && !fields.includes(styleSettings.value.filterField)) {
    styleSettings.value.filterField = '';
    styleSettings.value.filterValue = '';
  }
}

function applyStyle(options = {}) {
  const Cesium = props.getCesium?.();
  const targets = visibleTilesets();
  targets.forEach((tileset) => applyTilesetStyle(Cesium, tileset, styleSettings.value));
  emit('style-change', { ...styleSettings.value });
  if (options.notify && targets.length) message.success(`已更新 ${targets.length} 个 3D Tiles 图层样式`);
}

function resetStyle() {
  const targets = visibleTilesets();
  targets.forEach((tileset) => resetTilesetStyle(tileset));
  styleSettings.value = createDefaultTilesetStyleSettings();
  emit('style-change', { reset: true });
  if (targets.length) message.success(`已重置 ${targets.length} 个 3D Tiles 图层样式`);
}

function emitEffects() {
  emit('effects-change', { ...effectSettings.value });
}

function zoomToActive() {
  const viewer = props.getViewer?.();
  const Cesium = props.getCesium?.();
  const first = visibleTilesets()[0];
  if (!viewer || !Cesium || !first) {
    message.warning('当前没有可定位的 3D Tiles 图层');
    return;
  }
  viewer.flyTo(first, {
    duration: 1.5,
    offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-35), (first.boundingSphere?.radius || 5000) * 1.7)
  });
}

function flyToShenzhenView() {
  flyToShenzhen(props.getViewer?.(), props.getCesium?.());
}

function flyToChinaView() {
  flyToChina(props.getViewer?.(), props.getCesium?.());
}

function saveBookmark() {
  const bookmark = captureCameraBookmark(props.getViewer?.(), props.getCesium?.());
  if (!bookmark) return;
  registryState.bookmarks.unshift(bookmark);
  registryState.bookmarks.splice(8);
}

function restoreBookmark(item) {
  flyToBookmark(props.getViewer?.(), props.getCesium?.(), item);
}

function updateCameraReadout() {
  const viewer = props.getViewer?.();
  const Cesium = props.getCesium?.();
  if (!viewer || !Cesium) return;
  headingDeg.value = (Cesium.Math.toDegrees(viewer.camera.heading) + 360) % 360;
  cameraHeight.value = Number(viewer.camera.positionCartographic?.height || 0);
}

onMounted(() => {
  registerCesiumMeasurementTools(registry);
    registerCesiumSketchTools(registry);
    pickingCleanup = attachCesiumFeaturePicking(registry);
    cameraTimer = window.setInterval(updateCameraReadout, 500);
    registryState.statusText = '属性拾取待命';
    updateCameraReadout();
});

onUnmounted(() => {
  if (cameraTimer) window.clearInterval(cameraTimer);
  pickingCleanup?.();
  registry.destroy();
});

watch(activeTab, (tab) => {
  registryState.activeCategory = tab;
});

watch(
  () => registryState.selectedFeature,
  (feature) => {
    const keys = Object.keys(feature?.properties || {});
    if (keys.length) {
      discoveredPropertyFields.value = Array.from(new Set([...discoveredPropertyFields.value, ...keys])).slice(0, 160);
      syncStyleFields();
    }
    emit('feature-select', feature);
  },
  { deep: true }
);

watch(
  () => props.getThreeDLayers?.().map((item) => `${item.id}:${item.visible ? 1 : 0}:${Object.keys(item.metadata || {}).join(',')}`).join('|'),
  () => syncStyleFields(),
  { immediate: true }
);
</script>

<style scoped>
.cesium-tools-frame {
  z-index: 3900;
}

.cesium-tools-shell {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgba(7, 14, 18, 0.72);
  color: var(--text-primary);
}

.tool-tabs {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--border-subtle);
}

.tool-tab,
.tool-button,
.primary-action,
.secondary-action,
.bookmark-row {
  min-height: 36px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.06);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
}

.tool-tab.active,
.tool-button.active,
.tool-button:hover,
.primary-action:hover,
.secondary-action:hover,
.bookmark-row:hover {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  background: var(--neon-cyan-dim);
}

.tool-tab span {
  font-size: 12px;
}

.tool-section {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}

.button-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.field-line {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.tool-input {
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: rgba(0,0,0,0.25);
  color: var(--text-primary);
  padding: 8px 10px;
}

.check-line {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.primary-action {
  width: 100%;
}

.secondary-action {
  padding: 0 12px;
}

.action-pair {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.color-input {
  min-height: 38px;
  padding: 4px;
}

.result-list,
.property-list {
  display: grid;
  gap: 6px;
  margin-top: 12px;
}

.result-row,
.property-row,
.status-box,
.nav-readout {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.045);
  padding: 9px;
}

.status-box {
  display: grid;
  gap: 4px;
  font-size: 12px;
}

.status-box span {
  color: var(--text-muted);
}

.result-row,
.property-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}

.property-row em {
  max-width: 60%;
  color: var(--text-muted);
  overflow-wrap: anywhere;
  font-style: normal;
}

.empty-line,
.hint-text {
  color: var(--text-muted);
  font-size: 12px;
  padding: 10px 0;
}

.nav-readout {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.compass-dial {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 1px solid var(--border-active);
  display: grid;
  place-items: center;
  color: var(--neon-cyan);
  background: radial-gradient(circle, rgba(71,215,198,0.18), rgba(0,0,0,0.18));
  transition: transform 220ms var(--ease-spatial);
}

.bookmark-row {
  justify-content: flex-start;
  padding: 0 10px;
}

@container (max-width: 360px) {
  .tool-tabs {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .button-grid,
  .action-pair {
    grid-template-columns: 1fr;
  }
}
</style>
