<template>
  <div id="cesiumContainer" class="cesium-container"></div>

  <component
    :is="CesiumAdvancedEffects"
    v-if="shouldLoadAdvancedEffects"
    :get-viewer="getViewer"
    :get-cesium="getCesium"
    :effects-settings="cesiumEffectsSettings"
  />

  <Teleport to="body">
    <CesiumToolsPanel
      v-if="viewerReady"
      :get-viewer="getViewer"
      :get-cesium="getCesium"
      :get-three-d-layers="getThreeDLayers"
      @feature-select="handleFeatureSelect"
      @effects-change="handleEffectsChange"
      @style-change="handleTilesetStyleChange"
    />
  </Teleport>

  <Teleport to="body">
    <CesiumFeaturePopup
      :feature="selectedCesiumFeature"
      @close="selectedCesiumFeature = null"
    />
  </Teleport>

  <!-- 坐标显示面板 -->
  <div class="map-controls-group">
    <div class="mouse-position-content">{{ coordinateDisplay }}</div>
    <div class="divider"></div>
    <button class="home-btn" @click="flyToHome" title="回到初始位置">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
      </svg>
    </button>
  </div>

  <div class="cesium-controls">
    <div class="cesium-basemap-switch" role="group" aria-label="三维底图">
      <button
        v-for="option in CESIUM_BASEMAP_OPTIONS"
        :key="option.id"
        class="basemap-toggle"
        :class="{ active: activeCesiumBasemap === option.id }"
        :disabled="option.requiresToken && !TDT_TOKEN"
        :title="option.title"
        @click="handleCesiumBasemapChange(option.id)"
      >
        {{ option.label }}
      </button>
    </div>
    <button @click="flyToEverest" class="fly-btn">珠穆朗玛</button>
    <button @click="loadSimulatedWind" class="fly-btn">模拟风场</button>
  </div>

  <!-- 风场参数调节面板 -->
  <div v-if="wind2D" class="wind-controls">
    <div class="param-row">
      <label>速度因子: {{ speedFactor.toFixed(1) }}</label>
      <input type="range" min="0.1" max="5" step="0.1" v-model.number="speedFactor" @input="onParamChange" />
    </div>
    <div class="param-row">
      <label>箭头长度: {{ arrowLength / 1000 }}km</label>
      <input type="range" min="5000" max="50000" step="1000" v-model.number="arrowLength" @input="onParamChange" />
    </div>
    <div class="param-row">
      <label>尾迹长度: {{ trailLength / 1000 }}km</label>
      <input type="range" min="5000" max="80000" step="1000" v-model.number="trailLength" @input="onParamChange" />
    </div>
    <div class="param-row">
      <label>透明度: {{ alphaFactor.toFixed(2) }}</label>
      <input type="range" min="0.1" max="1" step="0.05" v-model.number="alphaFactor" @input="onParamChange" />
    </div>
  </div>
</template>

<script setup>
// TODO:
// cesium当前是直接加载来自天地图的资源，非官方的库，因此很多的功能和接口不兼容，
// 需要改为官方库的引用，解决兼容问题（wind2d中与非官方的cesium不兼容，无法正确运行）
// 需要注意到问题是：当前的cesium库使用频率很低，且cesium.js的文件量过大，
// 需要延迟加载，点击了对应的按钮后才触发加载引用，首屏加载的时候为了提高响应速度，
// 绝对不可以引入cesium.js相关的非必要文件
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useMessage } from '../../composables/useMessage';
import { showLoading, hideLoading } from '../../utils/loading';
import { useLayerStore } from '../../stores';
import {
  listPublishedTerrainLayers,
  listPublishedThreeDLayers,
  resolveTerrainTileUrlTemplate,
  resolveThreeDTilesUrl
} from '../../api/threed';
import { createHeightmapTerrainProvider } from '../../composables/cesium/features/useCesiumTerrainProvider';
import CesiumAdvancedEffects from './CesiumAdvancedEffects.vue';
import CesiumFeaturePopup from './CesiumFeaturePopup.vue';
import CesiumToolsPanel from './CesiumToolsPanel.vue';
import Wind2D from './Wind2D';

let Cesium = null;

// --- 配置常量区域 ---
const TDT_TOKEN = import.meta.env.VITE_TIANDITU_TK;
const TDT_SUBDOMAINS = ['0', '1', '2', '3', '4', '5', '6', '7'];
const TDT_SERVICE_ROOT = 'https://t{s}.tianditu.gov.cn/';
const CESIUM_DEFAULT_BASEMAP = 'tianditu-vector';
const CESIUM_BASEMAP_STORAGE_KEY = 'webgis_cesium_basemap_v2';
const CESIUM_BASEMAP_OPTIONS = [
  {
    id: 'tianditu-vector',
    label: '天地图矢量',
    title: '使用天地图矢量和注记，优先匹配 WGS84 / CGCS2000 三维数据',
    requiresToken: true
  },
  {
    id: 'tianditu-imagery',
    label: '天地图影像',
    title: '使用天地图影像和注记；若当前网络或 WAF 拦截，可能加载较慢',
    requiresToken: true
  },
  {
    id: 'amap-vector',
    label: '高德',
    title: '使用高德矢量底图，国内互联网访问稳定但存在 GCJ-02 偏移',
    requiresToken: false
  }
];

const TDT_CESIUM_JS_URL = 'https://api.tianditu.gov.cn/cdn/demo/sanwei/static/cesium/Cesium.js';
const TDT_CESIUM_CSS_URL = 'https://api.tianditu.gov.cn/cdn/demo/sanwei/static/cesium/Widgets/widgets.css';
const TDT_PLUGIN_URLS = [
  'https://api.tianditu.gov.cn/cdn/plugins/cesium/Cesium_ext_min.js',
  'https://api.tianditu.gov.cn/cdn/plugins/cesium/long.min.js',
  'https://api.tianditu.gov.cn/cdn/plugins/cesium/bytebuffer.min.js',
  'https://api.tianditu.gov.cn/cdn/plugins/cesium/protobuf.min.js'
];

// --- 响应式变量 ---
let viewer = null;
let handler = null;
const wind2D = ref(null); // Wind2D 实例
const coordinateDisplay = ref('经度: 0.000000, 纬度: 0.000000, 海拔: 0.00米');
const shouldLoadAdvancedEffects = ref(false);
const activeCesiumBasemap = ref(resolveInitialCesiumBasemap());
const viewerReady = ref(false);
const cesiumEffectsSettings = ref({ fog: false, bloom: false, hbao: false, tilt: false });
const selectedCesiumFeature = ref(null);
const threeDLayers = ref([]);  // { id, name, layerKind, tileset, terrainProvider, visible, loading }
let activeBaseImageryLayers = [];
let next3DLayerId = 0;
const message = useMessage();
const layerStore = useLayerStore();

function syncStoreForLayer(item) {
  layerStore.registerThreeDLayer({
    id: item.id,
    name: item.name,
    visible: item.visible,
    layerKind: item.layerKind || '3dtiles',
    tilesetUrl: item.tilesetUrl || '',
    tileUrlTemplate: item.tileUrlTemplate || '',
    bounds: item.bounds || [],
    description: item.description || '',
    featureCount: item.featureCount || 0,
    metadata: item.metadata || {}
  });
}

// 监听 store 中的可见性变化（例如用户从 TOC 面板勾选/取消勾选）
watch(
  () => layerStore.threeDLayerStateKey,
  (nextKey) => {
    const next = String(nextKey || '')
      .split('|')
      .filter(Boolean)
      .map((entry) => {
        const splitAt = entry.lastIndexOf(':');
        return {
          id: entry.slice(0, splitAt),
          visible: entry.slice(splitAt + 1) === '1'
        };
      });

    next.forEach(({ id, visible }) => {
      const item = threeDLayers.value.find((l) => l.id === id);
      if (item && item.visible !== visible) {
        setThreeDLayerVisibility(id, visible);
      }
    });
    // 若 store 中已不存在某图层（用户通过 TOC 移除），清理本地对应的 primitive
    const storeIds = new Set(next.map((l) => l.id));
    for (let i = threeDLayers.value.length - 1; i >= 0; i--) {
      const local = threeDLayers.value[i];
      if (!storeIds.has(local.id)) {
        if (local.layerKind === 'terrain' && local.visible) resetTerrainProvider();
        try { viewer?.scene?.primitives?.remove(local.tileset); } catch (_) {}
        threeDLayers.value.splice(i, 1);
      }
    }
  }
);

// 监听 3D 模式切换，执行相机俯仰飞行过渡
const wasAny3DVisible = ref(false);
watch(
  () => threeDLayers.value.some(l => l.visible),
  (entering, wasEntering) => {
    if (!viewer || !Cesium) return;
    if (entering && !wasEntering) {
      // 从 2D 俯视 → 3D 透视：从高空正射俯冲至 45° 倾角
      const cam = viewer.camera;
      const curPos = cam.positionCartographic;
      const lon = Cesium.Math.toDegrees(curPos?.longitude || 0);
      const lat = Cesium.Math.toDegrees(curPos?.latitude || 0);
      const alt = Math.max(curPos?.height || 50000, 10000);
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, alt * 0.25),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-40),
          roll: 0
        },
        duration: 2.0
      });
    } else if (!entering && wasEntering) {
      // 从 3D 透视 → 2D 俯视：拉回高空正射视角
      const cam = viewer.camera;
      const curPos = cam.positionCartographic;
      const lon = Cesium.Math.toDegrees(curPos?.longitude || 0);
      const lat = Cesium.Math.toDegrees(curPos?.latitude || 0);
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(lon, lat, 80000),
        orientation: {
          heading: Cesium.Math.toRadians(0),
          pitch: Cesium.Math.toRadians(-90),
          roll: 0
        },
        duration: 1.8
      });
    }
  }
);

// 风场参数绑定（与 Wind2D 实例同步）
const speedFactor = ref(1.0);
const arrowLength = ref(15000);
const trailLength = ref(20000);
const alphaFactor = ref(1.0);

// --- 生命周期 ---
onMounted(() => {
  bootCesium();
});

function clearWind2D() {
  if (!wind2D.value) return;
  try {
    viewer?.scene?.primitives?.remove(wind2D.value);
  } catch {}
  wind2D.value.destroy();
  wind2D.value = null;
}

onUnmounted(() => {
  viewerReady.value = false;
  shouldLoadAdvancedEffects.value = false;
  if (handler) {
    handler.destroy();
    handler = null;
  }
  clearWind2D();
  activeBaseImageryLayers = [];
  if (viewer) {
    try {
      if (viewer._creditCheckInterval) {
        clearInterval(viewer._creditCheckInterval);
      }
      viewer.destroy();
    } catch {}
    viewer = null;
  }
});

// --- 核心功能函数 ---

async function bootCesium() {
  showLoading('正在初始化 3D 场景...');
  try {
    await loadOfficialCesiumRuntime();
    if (!Cesium || !document.getElementById('cesiumContainer')) return;

    initViewer();
    setupInteractions();
    setCesiumBasemap(activeCesiumBasemap.value, { silent: true });

    initOfficialTerrain();
    viewerReady.value = true;
    shouldLoadAdvancedEffects.value = true;
    await refreshPublishedThreeDLayers();
    message.success('3D 底图加载成功。');

    // 风场在初始化完毕后即可准备加载（但需要手动点击按钮或自动加载）
    // 这里不自动加载，避免占满视野，等待用户点击“加载模拟风场”
  } catch (error) {
    message.error('Cesium 运行时加载失败', error);
    message.error('Cesium 初始化失败，请检查网络环境。', { closable: true });
  } finally {
    hideLoading();
  }
}

function getViewer() {
  return viewer;
}

function getCesium() {
  return Cesium || window.Cesium;
}

function getThreeDLayers() {
  return threeDLayers.value;
}

function handleEffectsChange(settings) {
  cesiumEffectsSettings.value = { ...(settings || {}) };
}

function handleTilesetStyleChange() {
  // 样式应用由 CesiumToolsPanel 直接处理；这里保留事件入口，后续可同步到图层配置。
}

function handleFeatureSelect(feature) {
  selectedCesiumFeature.value = feature || null;
}

async function loadOfficialCesiumRuntime() {
  await loadStyleOnce(TDT_CESIUM_CSS_URL, 'tdt-cesium-widgets-style');
  await loadScriptOnce(TDT_CESIUM_JS_URL, 'tdt-cesium-runtime-script');
  for (let i = 0; i < TDT_PLUGIN_URLS.length; i++) {
    await loadScriptOnce(TDT_PLUGIN_URLS[i], `tdt-plugin-${i}`);
  }
  Cesium = window.Cesium;
  if (!Cesium) throw new Error('Cesium global 未找到');
}

function initViewer() {
  const mapCtor = typeof Cesium.Map === 'function' ? Cesium.Map : Cesium.Viewer;
  viewer = new mapCtor('cesiumContainer', {
    imageryProvider: false,
    terrainProvider: undefined,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    infoBox: false,
    selectionIndicator: false,
    timeline: false,
    animation: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    shouldAnimate: true,
  });

  flyToHome(0);

  if (viewer._cesiumWidget?._creditContainer) {
    viewer._cesiumWidget._creditContainer.style.display = 'none';
  }

  viewer.scene.globe.terrainExaggeration = 1;
  viewer.scene.globe.terrainExaggerationRelativeHeight = 0.0;
  viewer.scene.globe.showGroundAtmosphere = true;
  viewer.scene.globe.depthTestAgainstTerrain = true;

  const hideCreditsAggressive = () => {
    if (viewer._cesiumWidget?._creditContainer) {
      viewer._cesiumWidget._creditContainer.style.cssText = 'display: none !important; visibility: hidden !important; width: 0 !important; height: 0 !important;';
      viewer._cesiumWidget._creditContainer.innerHTML = '';
    }
    const creditElems = document.querySelectorAll('[class*="credit"], [class*="geostar"], [class*="GeoStar"]');
    creditElems.forEach(el => {
      el.style.cssText = 'display: none !important; visibility: hidden !important;';
      el.innerHTML = '';
    });
    if (viewer.scene && viewer.scene.frameState && viewer.scene.frameState.creditDisplay) {
      viewer.scene.frameState.creditDisplay.hasCredits = () => false;
      viewer.scene.frameState.creditDisplay.destroy = () => {};
    }
  };
  hideCreditsAggressive();

  const creditCheckInterval = setInterval(() => {
    const creditContainer = document.querySelector('.cesium-credit-container');
    if (creditContainer && creditContainer.innerHTML.length > 0) {
      creditContainer.innerHTML = '';
      creditContainer.style.cssText = 'display: none !important; visibility: hidden !important; width: 0 !important; height: 0 !important;';
    }
  }, 500);
  viewer._creditCheckInterval = creditCheckInterval;

  if (!document.getElementById('cesium-credit-override')) {
    const style = document.createElement('style');
    style.id = 'cesium-credit-override';
    style.textContent = `
      .cesium-credit-container { display: none !important; visibility: hidden !important; height: 0 !important; width: 0 !important; }
      .cesium-credit-text { display: none !important; visibility: hidden !important; }
      .cesium-credit-logo-link { display: none !important; visibility: hidden !important; }
      [class*="credit"] { display: none !important; visibility: hidden !important; }
    `;
    document.head.appendChild(style);
  }
}

function setupInteractions() {
  handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((movement) => {
    const ray = viewer.camera.getPickRay(movement.endPosition);
    if (!ray) return;
    const position = viewer.scene.globe.pick(ray, viewer.scene);
    if (position) {
      const cartographic = Cesium.Cartographic.fromCartesian(position);
      const lng = Cesium.Math.toDegrees(cartographic.longitude).toFixed(6);
      const lat = Cesium.Math.toDegrees(cartographic.latitude).toFixed(6);
      const height = cartographic.height.toFixed(2);
      coordinateDisplay.value = `经度: ${lng}, 纬度: ${lat}, 海拔: ${height}米`;
    }
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
}

function isCesiumBasemapAvailable(id) {
  const option = CESIUM_BASEMAP_OPTIONS.find((item) => item.id === String(id || '').trim());
  if (!option) return false;
  return !(option.requiresToken && !TDT_TOKEN);
}

function resolveCesiumBasemapId(id) {
  const normalized = String(id || '').trim();
  if (isCesiumBasemapAvailable(normalized)) return normalized;
  if (isCesiumBasemapAvailable(CESIUM_DEFAULT_BASEMAP)) return CESIUM_DEFAULT_BASEMAP;
  return 'amap-vector';
}

function resolveInitialCesiumBasemap() {
  if (typeof window === 'undefined') return resolveCesiumBasemapId(CESIUM_DEFAULT_BASEMAP);
  try {
    return resolveCesiumBasemapId(window.localStorage.getItem(CESIUM_BASEMAP_STORAGE_KEY) || CESIUM_DEFAULT_BASEMAP);
  } catch (_) {
    return resolveCesiumBasemapId(CESIUM_DEFAULT_BASEMAP);
  }
}

function persistCesiumBasemap(id) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CESIUM_BASEMAP_STORAGE_KEY, id);
  } catch (_) {}
}

function clearBaseImageryLayers() {
  const imageryLayers = viewer?.imageryLayers;
  if (!imageryLayers) {
    activeBaseImageryLayers = [];
    return;
  }

  for (let i = activeBaseImageryLayers.length - 1; i >= 0; i--) {
    try {
      imageryLayers.remove(activeBaseImageryLayers[i], true);
    } catch (_) {}
  }
  activeBaseImageryLayers = [];
}

function createAmapVectorProvider() {
  return new Cesium.UrlTemplateImageryProvider({
    url: 'https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    minimumLevel: 1,
    maximumLevel: 18
  });
}

function createTiandituTemplateProvider(type, maxLevel = 17) {
  return new Cesium.UrlTemplateImageryProvider({
    url: `${TDT_SERVICE_ROOT}DataServer?T=${type}&x={x}&y={y}&l={z}&tk=${TDT_TOKEN}`,
    subdomains: TDT_SUBDOMAINS,
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    minimumLevel: 1,
    maximumLevel: maxLevel
  });
}

function createTiandituImageryProviders() {
  return [
    createTiandituTemplateProvider('img_w', 17),
    createTiandituTemplateProvider('cia_w', 17)
  ];
}

function createTiandituVectorProviders() {
  return [
    createTiandituTemplateProvider('vec_w', 18),
    createTiandituTemplateProvider('cva_w', 18)
  ];
}

function setCesiumBasemap(id, options = {}) {
  if (!viewer || !Cesium) return false;
  const nextId = resolveCesiumBasemapId(id);
  const requestedId = String(id || '').trim();
  const nextOption = CESIUM_BASEMAP_OPTIONS.find((item) => item.id === nextId);

  if (activeCesiumBasemap.value === nextId && activeBaseImageryLayers.length > 0) {
    return true;
  }

  clearBaseImageryLayers();
  const imageryLayers = viewer.imageryLayers;
  if (!imageryLayers) return false;

  const providers = nextId === 'tianditu-vector'
    ? createTiandituVectorProviders()
    : (nextId === 'tianditu-imagery'
      ? createTiandituImageryProviders()
      : [createAmapVectorProvider()]);

  activeBaseImageryLayers = providers.map((provider) => imageryLayers.addImageryProvider(provider));
  activeCesiumBasemap.value = nextId;
  persistCesiumBasemap(nextId);

  if (!options.silent) {
    if (requestedId && requestedId !== nextId) {
      message.warning('天地图 Token 未配置，已回退到高德三维底图。');
    } else {
      message.success(`三维底图已切换为${nextOption?.label || '默认图源'}`);
    }
  }
  return true;
}

function handleCesiumBasemapChange(id) {
  setCesiumBasemap(id);
}

function initOfficialTerrain() {
  viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
  return false;
}

function resetTerrainProvider() {
  if (!viewer || !Cesium) return;
  viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider();
}

function applyTerrainLayer(item, visible) {
  if (!viewer || !Cesium || !item) return false;
  item.visible = !!visible;
  if (!visible) {
    resetTerrainProvider();
    layerStore.setThreeDLayerVisibility(item.id, false);
    return true;
  }

  if (!item.terrainProvider) {
    item.terrainProvider = createHeightmapTerrainProvider(Cesium, item);
  }
  if (!item.terrainProvider) {
    message.warning('当前 Cesium 运行时不支持动态 DEM 地形，已保留椭球地形。');
    layerStore.setThreeDLayerVisibility(item.id, false);
    item.visible = false;
    return false;
  }

  viewer.terrainProvider = item.terrainProvider;
  layerStore.setThreeDLayerVisibility(item.id, true);
  const bounds = Array.isArray(item.bounds) ? item.bounds : [];
  if (bounds.length >= 4) {
    viewer.camera.flyTo({
      destination: Cesium.Rectangle.fromDegrees(bounds[0], bounds[1], bounds[2], bounds[3]),
      duration: 1.8
    });
  }
  message.success(`地形图层 "${item.name}" 已启用`);
  return true;
}

// --- 风场集成代码 ---
/**
 * 生成一个覆盖中国区域的模拟风场数据
 * 用于快速验证效果，实际项目中应替换为真实 API 数据
 */
function generateSimulatedWindData() {
  const centerLon = 104.0;  // 中国几何中心
  const centerLat = 35.0;
  const layerCount = 5;
  const altitudes = [0, 2000, 5000, 10000, 15000];  // 不同高度层（海拔米）
  const sizeMesh = [30000, 30000, 25000, 25000, 20000]; // 网格间距（米）
  const counts = [30, 30, 25, 25, 20]; // 各层网格分辨率 (nx=ny)
  
  const totalPoints = counts.reduce((sum, c) => sum + c * c, 0);
  const hspeed = new Array(totalPoints);
  const hdir = new Array(totalPoints);
  const vspeed = new Array(totalPoints);

  let offset = 0;
  for (let k = 0; k < layerCount; k++) {
    const nx = counts[k];
    const ny = counts[k];
    const gridSize = sizeMesh[k];
    // 模拟一个旋转风场 + 噪声
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const idx = offset + j * nx + i;
        // 生成位置偏移（相对于中心，单位：度）
        const dx = (i - nx / 2) * (gridSize / 111320.0);
        const dy = (j - ny / 2) * (gridSize / 111320.0 / Math.cos(Cesium.Math.toRadians(centerLat)));
        // 风向：绕中心旋转 + 随机扰动
        const baseAngle = Math.atan2(dy, dx) + Math.PI / 2; // 逆时针旋转
        const angle = baseAngle + 0.2 * Math.sin(i * 0.5) * Math.cos(j * 0.5);
        hdir[idx] = Cesium.Math.toDegrees(angle) % 360;
        // 风速：随高度增加，中心附近更大
        const dist = Math.sqrt(dx * dx + dy * dy);
        const maxDist = 15; // 约15度范围
        const factor = Math.max(0, 1 - dist / maxDist);
        hspeed[idx] = (5 + k * 2) * factor + 2 * Math.random();
        vspeed[idx] = 0.5 * Math.sin(i * 0.3) * Math.cos(j * 0.3);
      }
    }
    offset += nx * ny;
  }

  return {
    longitude: centerLon,
    latitude: centerLat,
    altitude: altitudes,
    sizeMesh: sizeMesh,
    count: counts,
    hspeed: hspeed,
    hdir: hdir,
    vspeed: vspeed,
  };
}

/**
 * 点击按钮加载风场
 */
function loadSimulatedWind() {
  if (!viewer || !Cesium) {
    message.error('Cesium 尚未初始化');
    return;
  }

  // 如果已有实例则先销毁
  clearWind2D();

  const data = generateSimulatedWindData();

  // 创建 Wind2D 实例（与面板参数同步）
  wind2D.value = new Wind2D(viewer, {
    maxWindSpeed: 20,         // 最大风速（用于归一化）
    cesium: Cesium,
    speedFactor: speedFactor.value,
    arrowLength: arrowLength.value,
    trailLength: trailLength.value,
    alphaFactor: alphaFactor.value,
  });

  // 加载数据，内部会自动设置粒子数
  wind2D.value.loadData(data);

  // 按 Cesium Primitive 协议注册到场景渲染管线
  viewer.scene.primitives.add(wind2D.value);

  // 飞到风场中央
  wind2D.value.flyTo();

  message.success('风场加载成功，可通过下方滑块调节样式');
}

/**
 * 滑块参数变化时，实时更新 Wind2D 实例
 */
function onParamChange() {
  if (!wind2D.value) return;
  wind2D.value.speedFactor = speedFactor.value;
  wind2D.value.arrowLength = arrowLength.value;
  wind2D.value.trailLength = trailLength.value;
  wind2D.value.alphaFactor = alphaFactor.value;
}

// --- 辅助工具函数 ---
function loadScriptOnce(url, id) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id);
    if (existing) {
      if (existing.getAttribute('data-loaded') === 'true') {
        resolve();
        return;
      }
      existing.addEventListener('load', () => resolve(), { once: true });
      existing.addEventListener('error', () => reject(new Error(`脚本加载失败: ${url}`)), { once: true });
      return;
    }
    const script = document.createElement('script');
    script.id = id;
    script.src = url;
    script.async = true;
    script.onload = () => {
      script.setAttribute('data-loaded', 'true');
      resolve();
    };
    script.onerror = () => reject(new Error(`脚本加载失败: ${url}`));
    document.head.appendChild(script);
  });
}

function loadStyleOnce(url, id) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id);
    if (existing) {
      resolve();
      return;
    }
    const link = document.createElement('link');
    link.id = id;
    link.rel = 'stylesheet';
    link.href = url;
    link.onload = () => resolve();
    link.onerror = () => reject(new Error(`样式加载失败: ${url}`));
    document.head.appendChild(link);
  });
}

function flyToHome(param) {
  if (!viewer) return;
  const duration = typeof param === 'number' ? param : 2;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(104.1954, 35.8617, 15000000),
    orientation: {
      heading: 0.0,
      pitch: -Cesium.Math.PI_OVER_TWO,
      roll: 0.0
    },
    duration: duration
  });
}

function flyToEverest() {
  if (!viewer) return;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(86.9250, 27.9881, 9000),
    orientation: {
      heading: Cesium.Math.toRadians(0.0),
      pitch: Cesium.Math.toRadians(-25.0),
      roll: 0.0
    },
    duration: 3
  });
}

/**
 * 加载用户自定义 3D Tiles（白模 / 城市模型等）
 * @param {string} url - tileset.json 的 URL（绝对路径或项目相对路径）
 * @param {object} options - 可选配置 { flyTo?: boolean, name?: string }
 */
async function load3DTilesUrl(url, options = {}) {
  if (!viewer || !Cesium) {
    message.error('3D 场景尚未就绪');
    return null;
  }
  const { flyTo = true, name = '', id = '', description = '', featureCount = 0, metadata = {} } = options || {};
  try {
    const resolvedUrl = resolveThreeDTilesUrl(url);
    const tileset = await Cesium.Cesium3DTileset.fromUrl(resolvedUrl);
    const layerId = id || `3d_${++next3DLayerId}`;
    const displayName = name || `3D 模型 ${next3DLayerId}`;
    if (name) tileset._name = displayName;

    viewer.scene.primitives.add(tileset);
    const existing = threeDLayers.value.find((item) => item.id === layerId);
    if (existing) {
      existing.tileset = tileset;
      existing.visible = true;
      existing.layerKind = '3dtiles';
      existing.tilesetUrl = resolvedUrl;
      existing.loading = false;
    } else {
      threeDLayers.value.push({
        id: layerId,
        name: displayName,
        layerKind: '3dtiles',
        tileset,
        visible: true,
        tilesetUrl: resolvedUrl,
        description,
        featureCount,
        metadata,
        loading: false
      });
    }
    syncStoreForLayer({ id: layerId, name: displayName, layerKind: '3dtiles', visible: true, tilesetUrl: resolvedUrl, description, featureCount, metadata });

    if (flyTo) {
      viewer.flyTo(tileset, {
        duration: 2.5,
        offset: new Cesium.HeadingPitchRange(
          Cesium.Math.toRadians(0.0),
          Cesium.Math.toRadians(-35.0),
          (tileset.boundingSphere?.radius || 5000) * 2.0
        )
      });
    }
    message.success(`3D 图层 "${displayName}" 已加载`);
    return tileset;
  } catch (error) {
    message.error(`3D 模型加载失败: ${error}`);
    return null;
  }
}

async function refreshPublishedThreeDLayers() {
  try {
    const [tilesPayload, terrainPayload] = await Promise.all([
      listPublishedThreeDLayers(),
      listPublishedTerrainLayers().catch(() => ({ data: [] }))
    ]);
    const list = Array.isArray(tilesPayload?.data) ? tilesPayload.data : [];
    const terrainList = Array.isArray(terrainPayload?.data) ? terrainPayload.data : [];
    const previous = new Map(threeDLayers.value.map((item) => [item.id, item]));
    const normalizedTiles = list
      .map((item) => {
        const id = `3d_pub_${String(item?.id || '').trim()}`;
        const tilesetUrlValue = resolveThreeDTilesUrl(item?.tileset_url || '');
        if (!item?.id || !tilesetUrlValue) return null;
        const existing = previous.get(id);
        return {
          id,
          sourceId: String(item.id),
          layerKind: '3dtiles',
          name: String(item?.name || '3D 图层'),
          visible: existing?.visible === true || layerStore.threeDLayers?.find?.((layer) => layer.id === id)?.visible === true,
          tileset: existing?.tileset || null,
          tilesetUrl: tilesetUrlValue,
          description: String(item?.description || ''),
          featureCount: Number(item?.feature_count || 0),
          metadata: item?.metadata || {},
          loading: existing?.loading === true
        };
      })
      .filter(Boolean);
    const normalizedTerrain = terrainList
      .map((item) => {
        const id = `terrain_pub_${String(item?.id || '').trim()}`;
        const tileUrlTemplate = resolveTerrainTileUrlTemplate(item?.tile_url_template || '');
        if (!item?.id || !tileUrlTemplate) return null;
        const existing = previous.get(id);
        return {
          id,
          sourceId: String(item.id),
          layerKind: 'terrain',
          name: String(item?.name || 'DEM 地形'),
          visible: existing?.visible === true || layerStore.threeDLayers?.find?.((layer) => layer.id === id)?.visible === true,
          terrainProvider: existing?.terrainProvider || null,
          tileUrlTemplate,
          bounds: Array.isArray(item?.bounds) ? item.bounds.map(Number).filter(Number.isFinite) : [],
          description: String(item?.description || ''),
          featureCount: 1,
          metadata: item?.metadata || {},
          loading: false
        };
      })
      .filter(Boolean);

    const normalized = [...normalizedTiles, ...normalizedTerrain];

    threeDLayers.value = normalized;
    layerStore.syncPublishedThreeDLayers?.(normalized.map((item) => ({
      id: item.id,
      name: item.name,
      visible: item.visible,
      layerKind: item.layerKind || '3dtiles',
      tilesetUrl: item.tilesetUrl,
      tileUrlTemplate: item.tileUrlTemplate,
      bounds: item.bounds,
      description: item.description,
      featureCount: item.featureCount,
      metadata: item.metadata
    })));
    normalized.forEach((item) => {
      if (item.visible && item.layerKind === 'terrain') {
        applyTerrainLayer(item, true);
      } else if (item.visible && !item.tileset && item.tilesetUrl) {
        setThreeDLayerVisibility(item.id, true);
      }
    });
  } catch (error) {
    layerStore.syncPublishedThreeDLayers?.([]);
    message.warning(`3D 图层列表加载失败: ${error?.message || error}`);
  }
}

function setThreeDLayerVisibility(id, visible) {
  const item = threeDLayers.value.find((l) => l.id === id);
  if (!item) return false;
  const nextVisible = !!visible;
  if (item.layerKind === 'terrain') {
    return applyTerrainLayer(item, nextVisible);
  }
  if (nextVisible && !item.tileset && item.tilesetUrl) {
    if (item.loading) return true;
    item.loading = true;
    load3DTilesUrl(item.tilesetUrl, {
      id: item.id,
      name: item.name,
      description: item.description,
      featureCount: item.featureCount,
      metadata: item.metadata,
      flyTo: true
    }).finally(() => {
      item.loading = false;
    });
    layerStore.setThreeDLayerVisibility(id, true);
    return true;
  }
  item.visible = nextVisible;
  if (item.tileset) item.tileset.show = item.visible;
  layerStore.setThreeDLayerVisibility(id, item.visible);
  return true;
}

function removeThreeDLayer(id) {
  const idx = threeDLayers.value.findIndex((l) => l.id === id);
  if (idx < 0) return false;
  const item = threeDLayers.value[idx];
  if (item.layerKind === 'terrain' && item.visible) resetTerrainProvider();
  try { viewer?.scene?.primitives?.remove(item.tileset); } catch (_) {}
  threeDLayers.value.splice(idx, 1);
  layerStore.unregisterThreeDLayer(id);
  message.info(`3D 图层 "${item.name}" 已移除`);
  return true;
}

function zoomToThreeDLayer(id) {
  const item = threeDLayers.value.find((l) => l.id === id);
  if (!item || !viewer || !Cesium) return false;
  if (item.layerKind === 'terrain') {
    const bounds = Array.isArray(item.bounds) ? item.bounds : [];
    if (bounds.length < 4) return false;
    viewer.camera.flyTo({
      destination: Cesium.Rectangle.fromDegrees(bounds[0], bounds[1], bounds[2], bounds[3]),
      duration: 1.8
    });
    return true;
  }
  if (!item.tileset) return false;
  try {
    viewer.flyTo(item.tileset, {
      duration: 2.0,
      offset: new Cesium.HeadingPitchRange(
        Cesium.Math.toRadians(0.0),
        Cesium.Math.toRadians(-35.0),
        (item.tileset.boundingSphere?.radius || 5000) * 2.0
      )
    });
    return true;
  } catch (_) {
    return false;
  }
}

function hasThreeDLayer(id) {
  return threeDLayers.value.some((l) => l.id === id);
}

defineExpose({
  load3DTilesUrl,
  refreshPublishedThreeDLayers,
  getViewer,
  getCesium,
  setThreeDLayerVisibility,
  removeThreeDLayer,
  zoomToThreeDLayer,
  hasThreeDLayer
});
</script>

<style scoped>
/* 原有样式保持不变 */
.cesium-container {
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
}

.tileset-input-group {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
  justify-content: center;
}
.tileset-url-input {
  padding: 6px 12px;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 6px;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 12px;
  width: 280px;
  outline: none;
}
.tileset-url-input::placeholder {
  color: rgba(255,255,255,0.5);
}
.upload-3dtiles-btn {
  cursor: pointer;
}

.upload-shp-btn.disabled {
  opacity: 0.5;
  pointer-events: none;
}

.shp-progress-overlay {
  position: absolute;
  bottom: 180px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
}
.shp-progress-card {
  background: var(--glass-bg-heavy);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-md) var(--space-lg);
  color: var(--text-primary);
  font-family: var(--font-body);
  min-width: 340px;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  box-shadow: var(--shadow-panel);
}
.shp-progress-title {
  font-size: var(--font-size-sm);
  font-weight: 500;
  margin-bottom: var(--space-sm);
  color: var(--neon-cyan);
}
.shp-progress-bar-wrap {
  height: 5px;
  background: rgba(0, 229, 255, 0.08);
  border-radius: var(--radius-full);
  overflow: hidden;
  margin-bottom: var(--space-sm);
}
.shp-progress-bar {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s var(--ease-out-expo);
  background: linear-gradient(90deg, var(--neon-cyan), var(--neon-green));
  box-shadow: 0 0 8px rgba(0, 229, 255, 0.4);
}
.shp-progress-bar.uploading {
  background: linear-gradient(90deg, #38bdf8, #818cf8);
}
.shp-progress-bar.processing {
  background: linear-gradient(90deg, #f59e0b, #f97316);
}
@keyframes shp-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.shp-progress-text {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-bottom: 2px;
}
.shp-progress-detail {
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
.shp-progress-stats {
  display: flex;
  gap: var(--space-md);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  margin-top: var(--space-xs);
}

.cesium-controls {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1200;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
  max-width: calc(100% - 24px);
}

.cesium-basemap-switch {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  background: var(--glass-bg-heavy);
  box-shadow: var(--shadow-panel);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.basemap-toggle {
  min-width: 58px;
  height: 32px;
  border: 0;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 12px;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  transition: color var(--duration-fast) var(--ease-spatial),
    background var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
}

.basemap-toggle:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.basemap-toggle.active {
  color: var(--deep-1);
  background: var(--neon-cyan);
  box-shadow: var(--neon-cyan-glow);
  font-weight: 600;
}

.basemap-toggle:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.fly-btn {
  background: var(--surface-1);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  padding: 8px 18px;
  border-radius: var(--radius-full);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 400;
  transition: all var(--duration-fast) var(--ease-out-expo);
  backdrop-filter: blur(8px);
}
.fly-btn:hover {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  box-shadow: var(--neon-cyan-glow);
  background: var(--surface-hover);
}

@media (max-width: 768px) {
  .cesium-controls {
    bottom: 74px;
    width: calc(100% - 24px);
    gap: 8px;
  }

  .cesium-basemap-switch {
    order: -1;
  }

  .basemap-toggle {
    min-width: 52px;
    height: 30px;
    padding: 0 10px;
  }
}

/* 风场控制面板样式 */
.wind-controls {
  position: absolute;
  bottom: 120px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2;
  background: var(--glass-bg-heavy);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  color: var(--text-primary);
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-panel);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-md);
  min-width: 600px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.param-row label {
  min-width: 100px;
  text-align: right;
  font-weight: bold;
}

.param-row input[type="range"] {
  width: 120px;
  cursor: pointer;
  accent-color: #42b983;
}

.map-controls-group {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: linear-gradient(to right, rgba(10, 121, 51, 0.9), rgba(8, 96, 41, 0.9));
  color: white;
  padding: 5px 10px;
  border-radius: 6px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.3);
  z-index: 1000;
  border: 1px solid rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .map-controls-group {
    width: 90%;
    justify-content: center;
    bottom: 15px;
  }
  .mouse-position-content {
    font-size: 12px;
    min-width: auto;
  }
  .wind-controls {
    flex-direction: column;
    min-width: auto;
    width: 90%;
    bottom: 180px;
  }
}

.mouse-position-content {
  font-size: 14px;
  font-weight: bold;
  min-width: 120px;
  text-align: center;
  display: flex;
  align-items: center;
  justify-content: center;
}

.divider {
  width: 1px;
  height: 20px;
  background-color: rgba(255, 255, 255, 0.4);
}

.home-btn {
  background: transparent;
  border: none;
  color: white;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.home-btn:hover {
  background-color: rgba(255, 255, 255, 0.2);
}
</style>
