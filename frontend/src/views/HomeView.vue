<script setup>
/**
 * HomeView.vue - 主页面组件
 * 
 * 功能：
 * - 2D/3D 地图切换
 * - AI 助手集成
 * - 新闻侧边栏展示
 * - 鼠标特效
 */
import { ref, reactive, computed, watch, defineAsyncComponent, onMounted, onUnmounted, nextTick, h } from 'vue';
import { useMessage } from '../composables/useMessage';
import { useAttrStore, useWeatherStore, useAppStore, useCompassStore, useTOCStore, useLayerStore } from '../stores';
import { showLoading, hideLoading } from '../utils/loading';
import { apiLogVisit } from '../api/backend';
const message = useMessage();
const attrStore = useAttrStore();
const weatherStore = useWeatherStore();
const compassStore = useCompassStore();
const tocStore = useTOCStore();
const layerStore = useLayerStore();

// 首屏地图初始化 Loading 已由路由守卫管理（Loading Relay）
// showLoading('正在初始化地图与核心环境...'); // 已由 router.beforeEach 接力处理

// ========== 1. 组件导入 ==========
// 同步导入：核心 2D 地图及 UI 组件 (保证首屏速度)
import TopBar from '../components/TopBar.vue';
import ControlsPanel from '@/components/ControlsPanel.vue';
import MapContainer from '../components/MapContainer.vue';
import MagicCursor from '../components/MagicCursor.vue';
import FloatingAccountPanel from '../components/UserCenter/FloatingAccountPanel.vue';
import PersistentAnnouncementBar from '../components/PersistentAnnouncementBar.vue';
import {
    Check as CheckIcon,
    Info as InfoIcon,
    TriangleAlert as TriangleAlertIcon,
    X as XIcon
} from 'lucide-vue-next';

// Cesium 组件按点击事件懒加载：避免首屏产生 3D 相关请求
const CesiumContainer = ref(null);
const cesiumContainerRef = ref(null);

const SidePanelLoading = {
    name: 'SidePanelLoading',
    render() {
        return h('div', { class: 'sidepanel-loading-state' }, [
            h('div', { class: 'sidepanel-loading-spinner' }),
            h('span', { class: 'sidepanel-loading-text' }, '侧边面板资源加载中...')
        ]);
    }
};

// 异步导入：SidePanel 组件 (优化：延迟加载图片资源)
const SidePanel = defineAsyncComponent({
    loader: () => import('../components/SidePanel.vue'),
    loadingComponent: SidePanelLoading,
    delay: 0,
    timeout: 15000,
    onError(error, retry, fail, attempts) {
        const text = String(error?.message || error || '');
        const isStaleOptimizeDep = text.includes('Outdated Optimize Dep') || text.includes('Failed to fetch dynamically imported module');
        if (isStaleOptimizeDep && attempts <= 1) {
            retry();
            return;
        }
        message.error('侧边面板加载失败，请刷新页面后重试。');
        fail(error);
    }
});

const WeatherPanelLoading = {
    name: 'WeatherPanelLoading',
    render() {
        return h('div', { class: 'sidepanel-loading-state weather-loading-state' }, [
            h('div', { class: 'sidepanel-loading-spinner' }),
            h('span', { class: 'sidepanel-loading-text' }, '天气看板资源加载中...')
        ]);
    }
};

const WeatherChartPanel = defineAsyncComponent({
    loader: () => import('../components/WeatherChartPanel.vue'),
    loadingComponent: WeatherPanelLoading,
    delay: 0,
    timeout: 15000,
    onError(error, retry, fail, attempts) {
        const text = String(error?.message || error || '');
        const isStaleOptimizeDep = text.includes('Outdated Optimize Dep') || text.includes('Failed to fetch dynamically imported module');
        if (isStaleOptimizeDep && attempts <= 1) {
            retry();
            return;
        }
        message.error('天气看板加载失败，请刷新页面后重试。');
        fail(error);
    }
});

// ========== 2. 响应式状态 ==========
// 地图位置信息
const locationInfo = reactive({
    isInDihuan: false,
    lonLat: [0, 0]
});

// UI 状态
const selectedImage = ref('');
const currentNewsIndex = ref(0);
const is3DMode = computed(() => (layerStore?.threeDLayers || []).some(l => l.visible));
const isCesiumLoaded = ref(false);
const isCesiumLoading = ref(false);
let last3DMode = false;
const isWeatherBoardMode = ref(false);
const shouldLoadWeatherChartPanel = ref(false);
const isMagicMode = ref(false);
const magicEffectData = ref('');
const isSidePanelCollapsed = ref(true);
const shouldLoadSidePanel = ref(false);
const sidePanelWarmupScheduled = ref(false);
const activeSidePanelTab = ref('toolbox'); // 'info' | 'chat' | 'toolbox' | 'bus' | 'drive' | 'compass'
const userLayers = ref([]);
const featureQueryResult = ref(null);
const showQueryPanel = ref(false);
const toolboxOverview = ref({ drawCount: 0, uploadCount: 0, layers: [] });
const baseLayers = ref([]);
const uploadProgress = ref({ phase: 'idle' });
const latestSearchPoi = ref({});
const activeFeature = ref({ key: 'info', label: '新闻' });
const isAccountPanelOpen = ref(false);
const isAccountPanelFullscreen = ref(false);
const colorTheme = ref('dark');

// 组件引用
const mapContainerRef = ref(null);
const mapCoreLoadingSettled = ref(false);
let sidePanelWarmupTimer = null;
let sidePanelWarmupIdleId = null;
const THEME_STORAGE_KEY = 'webgis_color_theme';

// ========== 访问记录延迟执行标志 ==========
// 确保 visitLog 不与底图加载竞争网络资源
const visitLogScheduled = ref(false);

// ========== 3. 事件处理函数 ==========

function readInitialTheme() {
    if (typeof window === 'undefined') return 'dark';
    try {
        const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
        if (stored === 'light' || stored === 'dark') return stored;
        return 'dark';
    } catch {
        return 'dark';
    }
}

function applyColorTheme(theme) {
    const nextTheme = theme === 'light' ? 'light' : 'dark';
    colorTheme.value = nextTheme;
    if (typeof document !== 'undefined') {
        document.documentElement.dataset.theme = nextTheme;
    }
    if (typeof window !== 'undefined') {
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
        } catch {}
    }
}

function toggleColorTheme() {
    applyColorTheme(colorTheme.value === 'dark' ? 'light' : 'dark');
}

/** 地图位置变化处理 */
function handleLocationChange(locationData) {
    Object.assign(locationInfo, locationData);

    const lon = Number(locationData?.lon);
    const lat = Number(locationData?.lat);
    if (Number.isFinite(lon) && Number.isFinite(lat)) {
        weatherStore.setMapPointTrigger({
            lon,
            lat,
            source: String(locationData?.source || 'location-change')
        });
    }
}

function handleMapClick(locationData) {
    const lon = Number(locationData?.lon);
    const lat = Number(locationData?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;

    weatherStore.setMapPointTrigger({
        lon,
        lat,
        source: String(locationData?.source || 'map-click')
    });
}

/** 更新新闻图片 */
function handleUpdateNewsImage(imageSrc) {
    selectedImage.value = imageSrc;
}

/** 新闻切换处理 */
function handleNewsChanged(newsIndex) {
    currentNewsIndex.value = newsIndex;
}

/** 切换侧边栏展开/收起 */
function toggleSidePanel() {
    // 首次展开时才加载SidePanel组件及其资源
    if (isSidePanelCollapsed.value && !shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = !isSidePanelCollapsed.value;
    if (isSidePanelCollapsed.value) {
        compassStore.setPlacementMode(false);
    }
    message.soup();
}

function stopCompassTransientInteractions() {
    compassStore.setPlacementMode(false);
}

/** 打开 AI 聊天面板 */
function openChat() {
    stopCompassTransientInteractions();
    activeSidePanelTab.value = 'chat';
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
}

function openToolbox() {
    stopCompassTransientInteractions();
    activeSidePanelTab.value = 'toolbox';
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
}

async function openCompassPanel() {
    activeSidePanelTab.value = 'compass';
    compassStore.setEnabled(true);
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
    await compassStore.ensureConfigLoaded();
}

function openBusPlanner() {
    stopCompassTransientInteractions();
    activeSidePanelTab.value = 'bus';
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
}

function openDrivePlanner() {
    stopCompassTransientInteractions();
    activeSidePanelTab.value = 'drive';
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
}

function getMapUserLocation(enableHighAccuracy = true) {
    return mapContainerRef.value?.getCurrentLocation?.(enableHighAccuracy);
}

function startBusPointPick(type) {
    return mapContainerRef.value?.startBusPointPick?.(type);
}

function drawRouteOnMap(route) {
    return mapContainerRef.value?.drawRouteOnMap?.(route);
}

function zoomToBusRouteStep(stepIndex) {
    return mapContainerRef.value?.zoomToBusRouteStep?.(stepIndex);
}

function previewBusRouteStep(stepIndex) {
    return mapContainerRef.value?.previewBusRouteStep?.(stepIndex);
}

function clearBusRouteStepPreview() {
    return mapContainerRef.value?.clearBusRouteStepPreview?.();
}

function drawDriveRouteOnMap(routeLatLonStr) {
    return mapContainerRef.value?.drawDriveRouteOnMap?.(routeLatLonStr);
}

function zoomToDriveRouteStep(stepIndex) {
    return mapContainerRef.value?.zoomToDriveRouteStep?.(stepIndex);
}

function previewDriveRouteStep(stepIndex) {
    return mapContainerRef.value?.previewDriveRouteStep?.(stepIndex);
}

function clearDriveRouteStepPreview() {
    return mapContainerRef.value?.clearDriveRouteStepPreview?.();
}

function handleActivateFeature(feature) {
    activeFeature.value = feature || { key: 'info', label: '新闻' };
}

function handleSwitchSidePanelTab(tab) {
    if (tab !== 'compass') {
        stopCompassTransientInteractions();
    }
    activeSidePanelTab.value = tab;
}

function handleControlsOpenTab(tab) {
    const next = String(tab || '').trim();
    if (!next) return;

    handleSwitchSidePanelTab(next);
    if (!shouldLoadSidePanel.value) {
        shouldLoadSidePanel.value = true;
    }
    isSidePanelCollapsed.value = false;
}

function handleControlsMapInteraction(type) {
    const nextType = String(type || '').trim();
    if (!nextType) return;
    mapContainerRef.value?.activateInteraction?.(nextType);
}

function handleControlsShowAnalysis() {
    message.info('分析功能入口已接入，后续可扩展缓冲区/最短路径专属面板。');
}

async function handleControlsDistrictSelect(payload) {
    const adcode = String(payload?.value || '').trim();
    const districtName = String(payload?.label || '').trim() || adcode;

    if (!/^\d{6}$/.test(adcode)) {
        message.warning('行政区 adcode 无效，请重新选择。');
        return;
    }

    try {
        const result = await mapContainerRef.value?.focusDistrictByAdcode?.({
            adcode,
            name: districtName,
            fit: true
        });

        if (!result) {
            message.warning('地图尚未准备完成，请稍后再试。');
            return;
        }

        message.success(`已加载行政区边界：${districtName}`);
    } catch (error) {
        const detail = String(error?.message || '').trim();
        message.error(detail || '行政区边界加载失败');
    }
}

/**
 * 处理卷帘分析（双底图对比）事件
 */
async function handleEnableBasemapSwipe(payload) {
    const { leftBasemap, rightBasemap, mode } = payload || {};

    if (!mapContainerRef.value) {
        message.error('地图容器未准备好');
        return;
    }

    try {
        await mapContainerRef.value?.enableBasemapSwipe?.({
            leftBasemapId: leftBasemap,
            rightBasemapId: rightBasemap,
            mode: mode || 'horizontal'
        });
    } catch (error) {
        const detail = String(error?.message || '').trim();
        message.error(detail || '卷帘分析启用失败，请检查底图配置');
    }
}

function getLayerMetaById(layerId) {
    const id = String(layerId || '').trim();
    if (!id) return null;
    return tocStore.getLayerMeta(id);
}

function isDistrictLayer(layerId) {
    return String(getLayerMetaById(layerId)?.sourceType || '') === 'district-boundary';
}

function getDistrictMeta(layerId) {
    const meta = getLayerMetaById(layerId);
    if (!meta || String(meta.sourceType || '') !== 'district-boundary') return null;
    return meta;
}

function focusDistrictLayer(layerId) {
    const meta = getDistrictMeta(layerId);
    if (!meta) return false;

    mapContainerRef.value?.focusDistrictByAdcode?.({
        adcode: meta.adcode,
        name: meta.name,
        fit: true
    });
    return true;
}

function handleDistrictLayerVisibility(layerId, visible) {
    const meta = getDistrictMeta(layerId);
    if (!meta) return false;

    mapContainerRef.value?.setDistrictLayerVisibility?.(meta.adcode, !!visible);
    return true;
}

function handleDistrictLayerRemove(layerId) {
    const meta = getDistrictMeta(layerId);
    if (!meta) return false;

    mapContainerRef.value?.removeDistrictLayer?.(meta.adcode);
    message.success(`已移除行政区划图层：${meta.name}`);
    return true;
}

function syncDistrictLayerVisibility(layerId) {
    const activeId = String(layerId || '').trim();
    const districtLayers = tocStore.layerMetadataList.filter((meta) => String(meta.sourceType || '') === 'district-boundary');
    if (!districtLayers.length) return;

    districtLayers.forEach((meta) => {
        const shouldShow = meta.id === activeId;
        if (meta.visible === shouldShow) return;
        tocStore.upsertLayerMeta({
            ...meta,
            visible: shouldShow
        });
    });
}

function handleAccountPanelFullscreenChange(fullscreen) {
    isAccountPanelFullscreen.value = Boolean(fullscreen);
    if (isAccountPanelFullscreen.value) {
        isAccountPanelOpen.value = true;
    }
}

function handleToggleAccountPanel() {
    isAccountPanelOpen.value = !isAccountPanelOpen.value;
}

/** 主地图关键内容就绪后，消除加载状态并在空闲时预加载侧边面板资源。 */
function settleMapCoreLoading(payload = {}) {
    if (mapCoreLoadingSettled.value) return;
    mapCoreLoadingSettled.value = true;

    const appStore = useAppStore();
    appStore.markGisInitComplete();

    hideLoading();

    if (payload?.isError) {
        const detail = String(payload?.message || '').trim();
        message.error(detail || '地图资源加载失败，请刷新页面后重试。');
    }
}

/** 主地图关键内容就绪后，消除加载状态并在空闲时预加载侧边面板资源。 */
function handleMapCoreReady() {
    settleMapCoreLoading();

    // ========== Phase 1: 处理侧边面板预热 ==========
    if (sidePanelWarmupScheduled.value || shouldLoadSidePanel.value) {
        // 侧边面板已在加载或已加载，先执行 visitLog
    } else {
        sidePanelWarmupScheduled.value = true;

        const preloadSidePanel = () => {
            if (!shouldLoadSidePanel.value) {
                shouldLoadSidePanel.value = true;
            }
        };

        const queuePreload = () => {
            if (typeof window === 'undefined') return;
            sidePanelWarmupTimer = window.setTimeout(preloadSidePanel, 900);
        };

        if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
            sidePanelWarmupIdleId = window.requestIdleCallback(queuePreload, { timeout: 2200 });
        } else {
            queuePreload();
        }
    }

    // ========== Phase 2: 处理访问记录（非关键，延后到底图就绪后）==========
    // 关键改进：visitLog 不再与底图加载竞争
    // 原本在 HomeView.onMounted() 中立即执行，现在延后到这里
    if (!visitLogScheduled.value) {
        visitLogScheduled.value = true;
        executeVisitLogAsync();
    }
}

/** 异步执行访问记录，不阻塞底图和侧边面板加载 */
async function executeVisitLogAsync() {
    try {
        const visitPayload = await buildVisitLogPayload();
        const visitResponse = await apiLogVisit(visitPayload);
        const encodedPos = String(visitResponse?.data?.encoded_pos || '0');
        syncVisitPosCodeToUrl(encodedPos);
    } catch {
        // 访问记录失败不影响主页面使用
    }
}

function handleMapCoreFailed(payload = {}) {
    settleMapCoreLoading({
        isError: true,
        message: String(payload?.message || '').trim() || '地图初始化失败，请检查网络后重试。'
    });
}

/** 关闭 AI 聊天，切换回新闻模式 */
function handleCloseChat() {
    activeSidePanelTab.value = 'info';
    activeFeature.value = { key: 'info', label: '新闻' };
}

function openWeatherPanel() {
    stopCompassTransientInteractions();
    activeSidePanelTab.value = 'weather';
    if (!shouldLoadSidePanel.value) shouldLoadSidePanel.value = true;
    isSidePanelCollapsed.value = false;
    // Trigger map center weather query
    nextTick(() => {
        const center = mapContainerRef.value?.getMapCenter?.();
        if (center) weatherStore.setMapPointTrigger({ lon: center.lon, lat: center.lat, source: 'map-center' });
    });
}

function toggleWeatherBoardMode() {
    const openingWeather = !isWeatherBoardMode.value;

    if (openingWeather && !shouldLoadWeatherChartPanel.value) {
        shouldLoadWeatherChartPanel.value = true;
    }

    isWeatherBoardMode.value = openingWeather;

    if (openingWeather) {
        // 隐藏所有 3D 图层
        layerStore.threeDLayers.forEach(l => { layerStore.setThreeDLayerVisibility(l.id, false); });
        activeFeature.value = { key: 'weather-board', label: '天气看板' };
        // 读取当前屏幕中心经纬度并触发天气查询
        nextTick(() => {
            const center = mapContainerRef.value?.getMapCenter?.();
            if (center) {
                weatherStore.setMapPointTrigger({ lon: center.lon, lat: center.lat, source: 'map-center' });
            }
        });
    } else {
        activeFeature.value = { key: 'map', label: '地图视图' };
    }
}

/** 自动加载 Cesium 3D 引擎（首次触发时懒加载），等待组件挂载完成。 */
async function ensureCesiumLoaded() {
    if (isCesiumLoaded.value || isCesiumLoading.value) {
        // 已经在加载或已加载，等待组件 ref 可用
        if (isCesiumLoaded.value && !cesiumContainerRef.value) {
            await nextTick();
        }
        return;
    }
    isCesiumLoading.value = true;
    try {
        const module = await import('../components/Cesium/CesiumContainer.vue');
        CesiumContainer.value = module.default;
        isCesiumLoaded.value = true;
        await nextTick();  // 等待 Vue 挂载 <component> 并设置 ref
    } catch (error) {
        message.error('3D 引擎加载失败', error);
    } finally {
        isCesiumLoading.value = false;
    }
}

/** 监听 3D 图层可见性变化，自动切换 2D/3D 视角并飞行 */
watch(() => is3DMode.value, (entering3D) => {
    if (entering3D && !last3DMode) {
        // 进入 3D：确保引擎加载，切换视角
        ensureCesiumLoaded();
    }
    // 相机飞行由 CesiumContainer 内部 watch 处理
    last3DMode = !!entering3D;
});

/** 开启特定魔法特效 */
function handleActivateMagic(effectName) {
    if (effectName === 'off') {
        isMagicMode.value = false;
        magicEffectData.value = '';
    } else {
        isMagicMode.value = true;
        magicEffectData.value = effectName;
    }
}

/** 处理文件上传 */
async function handleUploadData(data) {
    showLoading('正在导入 GIS 数据资源...');
    try {
        await Promise.resolve(mapContainerRef.value?.addUserDataLayer(data));
    } finally {
        hideLoading();
    }
}

/** 处理地图交互工具 */
function handleInteraction(type) {
    mapContainerRef.value?.activateInteraction(type);
}

function isThreeDLayer(layerId) {
    return typeof layerId === 'string' && layerId.startsWith('3d_');
}

function handleToggleLayerVisibility({ layerId, visible }) {
    if (isThreeDLayer(layerId)) {
        cesiumContainerRef.value?.setThreeDLayerVisibility?.(layerId, visible);
        return;
    }
    if (isDistrictLayer(layerId)) {
        handleDistrictLayerVisibility(layerId, visible);
        return;
    }
    mapContainerRef.value?.setUserLayerVisibility(layerId, visible);
}

function handleChangeLayerOpacity({ layerId, opacity }) {
    mapContainerRef.value?.setUserLayerOpacity(layerId, opacity);
}

function handleSetBaseLayer(layerId) {
    mapContainerRef.value?.setBaseLayerActive(layerId);
}

function handleToggleBaseLayerVisibility({ layerId, visible }) {
    mapContainerRef.value?.setLayerVisibility(layerId, visible);
}

function handleZoomLayer(layerId) {
    if (isThreeDLayer(layerId)) {
        cesiumContainerRef.value?.zoomToThreeDLayer?.(layerId);
        return;
    }
    if (focusDistrictLayer(layerId)) return;
    mapContainerRef.value?.zoomToUserLayer(layerId);
}

function handleViewLayer(layerId) {
    if (isThreeDLayer(layerId)) {
        cesiumContainerRef.value?.zoomToThreeDLayer?.(layerId);
        return;
    }
    if (focusDistrictLayer(layerId)) return;
    mapContainerRef.value?.viewUserLayer(layerId);
}

function handleRemoveLayer(layerId) {
    if (isThreeDLayer(layerId)) {
        cesiumContainerRef.value?.removeThreeDLayer?.(layerId);
        return;
    }
    if (handleDistrictLayerRemove(layerId)) return;
    mapContainerRef.value?.removeUserLayer(layerId);
}

function handleReorderUserLayers(payload) {
    mapContainerRef.value?.reorderUserLayers(payload);
}

function handleSoloLayer(layerId) {
    mapContainerRef.value?.soloUserLayer(layerId);
    syncDistrictLayerVisibility(layerId);
}

function handleApplyStyleTemplate(payload) {
    mapContainerRef.value?.applyStyleTemplate(payload);
}

function handleUpdateDrawStyle(styleConfig) {
    mapContainerRef.value?.setDrawStyle(styleConfig);
}

function handleUpdateLayerStyle(payload) {
    mapContainerRef.value?.setUserLayerStyle(payload);
}

function handleHighlightAttributeFeature(payload) {
    mapContainerRef.value?.highlightManagedFeature?.(payload);
}

function handleZoomAttributeFeature(payload) {
    mapContainerRef.value?.zoomToManagedFeature?.(payload);
}

function handleToggleLayerLabelVisibility(payload) {
    mapContainerRef.value?.setUserLayerLabelVisibility(payload);
}

function handleSetLayerLabelField(payload) {
    mapContainerRef.value?.setUserLayerLabelField(payload);
}

/**
 * 处理用户输入坐标绘制点位
 */
function handleDrawPointByCoordinates(payload) {
    mapContainerRef.value?.drawPointByCoordinatesInput(payload);
}

/**
 * 处理用户手动粘贴高德详情 JSON 并绘制 AOI
 */
function handleDrawAmapAoiFromJson(payload) {
    try {
        mapContainerRef.value?.drawAmapAoiByDetailJsonInput?.(payload);
    } catch (error) {
        const detail = error instanceof Error ? error.message : 'AOI 解析失败';
        message.warning(`AOI 解析失败：${detail}`);
    }
}

/**
 * 处理搜索结果图层的坐标系切换
 */
function handleToggleLayerCRS(payload) {
    mapContainerRef.value?.toggleLayerCRS?.(payload);
}

/**
 * 导出图层坐标数据（CSV/TXT）
 */
function handleExportLayerData(payload) {
    mapContainerRef.value?.exportLayerCoordinates?.(payload);
}

// ── 3D 上传事件转发到 CesiumContainer ──
async function handleUploadShp3D(config) {
    await ensureCesiumLoaded();
    await nextTick();
    await nextTick();
    if (isSidePanelCollapsed.value) toggleSidePanel();
    cesiumContainerRef.value?.handleShpTo3D?.(config);
}
async function handleUpload3DTilesZip({ file }) {
    await ensureCesiumLoaded();
    await nextTick();
    await nextTick();
    if (isSidePanelCollapsed.value) toggleSidePanel();
    cesiumContainerRef.value?.handle3DTilesUpload?.({ target: { files: [file] } });
}
async function handleLoad3DTilesUrl({ url }) {
    await ensureCesiumLoaded();
    await nextTick();
    await nextTick();
    if (isSidePanelCollapsed.value) toggleSidePanel();
    cesiumContainerRef.value?.load3DTilesUrl?.(url, { name: url.split('/').pop()?.replace('.json', '') || '3D模型' });
}

function handleUserLayersChange(layers) {
    userLayers.value = layers || [];
    attrStore.syncLayers(userLayers.value);
}

function handleGraphicsOverview(data) {
    toolboxOverview.value = data || { drawCount: 0, uploadCount: 0, layers: [] };
}

function handleBaseLayersChange(layers) {
    baseLayers.value = layers || [];
}

let uploadDoneTimer = null;
function handleUploadProgressChange(progress) {
    clearTimeout(uploadDoneTimer);
    uploadProgress.value = progress || { phase: 'idle' };
    if (uploadProgress.value.phase === 'done') {
        uploadDoneTimer = setTimeout(() => {
            uploadProgress.value = { phase: 'idle' };
        }, 2500);
    }
}

const uploadProgressView = computed(() => {
    const raw = uploadProgress.value || {};
    return {
        phase: String(raw.phase || 'idle'),
        total: Math.max(0, Number(raw.total) || 0),
        current: Math.max(0, Number(raw.current) || 0),
        success: Math.max(0, Number(raw.success) || 0),
        failed: Math.max(0, Number(raw.failed) || 0),
    };
});

const showUploadProgressBar = computed(() => {
    return uploadProgressView.value.phase !== 'idle' && uploadProgressView.value.phase !== 'done';
});

const uploadProgressPercent = computed(() => {
    const { total, current, phase } = uploadProgressView.value;
    if (phase === 'done') return 100;
    if (!total) return 8;
    return Math.max(4, Math.min(100, Math.round((current / total) * 100)));
});

const uploadProgressLabelText = computed(() => {
    const map = { validating: '校验文件中', dispatching: '解析文件中', importing: '导入数据中', done: '导入完成', error: '导入出错' };
    return map[uploadProgressView.value.phase] || '处理中';
});

function handleSearchPoiSelected(poiPayload) {
    const service = String(poiPayload?.service || '').trim().toLowerCase();
    if (service && service !== 'amap') return;
    const poiid = String(poiPayload?.poiid || '').trim();

    latestSearchPoi.value = {
        ...poiPayload,
        poiid,
        _syncAt: Date.now()
    };
}

function closeQueryPanel() {
    showQueryPanel.value = false;
}

/** 处理图层被选中事件 */
function handleLayerSelected(layerId) {
    if (focusDistrictLayer(layerId)) return;
    mapContainerRef.value?.highlightUserLayer?.(layerId);
}

/** 处理要素选中事件 */
function handleFeatureSelected(properties) {
    if (!properties) return;
    featureQueryResult.value = properties;
    showQueryPanel.value = true;
}

async function buildVisitLogPayload() {
    const payload = {
        geo_permission: 'unknown',
        gps_lng: null,
        gps_lat: null,
        gps_accuracy: null,
        gps_timestamp: '',
        gps_error: ''
    };

    if (typeof window === 'undefined' || typeof navigator === 'undefined') {
        return payload;
    }

    if (!navigator.geolocation) {
        payload.geo_permission = 'unsupported';
        payload.gps_error = 'geolocation-not-supported';
        return payload;
    }

    try {
        if (navigator.permissions && typeof navigator.permissions.query === 'function') {
            const permissionStatus = await navigator.permissions.query({ name: 'geolocation' });
            payload.geo_permission = String(permissionStatus?.state || 'unknown');
        }
    } catch {
        // ignore permission API read errors
    }

    const shouldTryGps = (
        payload.geo_permission === 'granted'
        || payload.geo_permission === 'prompt'
        || payload.geo_permission === 'unknown'
    );

    if (!shouldTryGps) {
        return payload;
    }

    try {
        const position = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 3500,
                maximumAge: 60000
            });
        });

        payload.geo_permission = 'granted';
        payload.gps_lng = Number(position?.coords?.longitude);
        payload.gps_lat = Number(position?.coords?.latitude);
        payload.gps_accuracy = Number(position?.coords?.accuracy);
        payload.gps_timestamp = new Date(position?.timestamp || Date.now()).toISOString();
    } catch (error) {
        const code = Number(error?.code || 0);
        if (code === 1) {
            payload.geo_permission = 'denied';
        }
        payload.gps_error = String(error?.message || `geolocation-error-${code}`).slice(0, 250);
    }

    return payload;
}

function syncVisitPosCodeToUrl(encodedPos) {
    if (typeof window === 'undefined') return;

    const normalizedCode = String(encodedPos || '').trim() || '0';

    try {
        const hash = String(window.location.hash || '#/home');
        const hashWithoutSharp = hash.startsWith('#') ? hash.slice(1) : hash;
        const [hashPathRaw, hashQueryRaw = ''] = hashWithoutSharp.split('?');
        const hashPath = hashPathRaw || '/home';
        const normalizedHashPath = hashPath.startsWith('/') ? hashPath : `/${hashPath}`;
        const params = new URLSearchParams(hashQueryRaw);

        params.set('p', normalizedCode);

        if (normalizedCode !== '0' && String(params.get('loc') || '').trim() === '') {
            params.set('loc', '1');
        }

        const nextHashQuery = params.toString();
        const nextHash = nextHashQuery
            ? `#${normalizedHashPath}?${nextHashQuery}`
            : `#${normalizedHashPath}`;

        const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;
        window.history.replaceState(window.history.state, '', nextUrl);
    } catch {
        // URL 写入失败时不阻断主流程
    }
}

onUnmounted(() => {
    settleMapCoreLoading();

    if (typeof window === 'undefined') return;

    if (sidePanelWarmupIdleId !== null && typeof window.cancelIdleCallback === 'function') {
        window.cancelIdleCallback(sidePanelWarmupIdleId);
        sidePanelWarmupIdleId = null;
    }

    if (sidePanelWarmupTimer !== null) {
        window.clearTimeout(sidePanelWarmupTimer);
        sidePanelWarmupTimer = null;
    }

    // 注意：visitLog 可能在组件卸载后才执行
    // 这是可接受的，因为它是非关键任务，只是记录访问信息
});

onMounted(async () => {
    applyColorTheme(readInitialTheme());
    // ========== 访问记录已延迟到 handleMapCoreReady 执行 ==========
    // 原理：访问记录（buildVisitLogPayload + apiLogVisit）包含地理定位和 HTTP 请求
    // 如果在这里执行，会与底图加载竞争网络资源和事件循环
    // 现在改为在底图核心就绪后执行，确保底图有绝对优先级
    // visitLog 调用已移到 handleMapCoreReady() 中的 executeVisitLogAsync()
});
</script>

<template>
    <div class="home-container">
        <!-- 特效光标遮罩 -->
        <MagicCursor :active="isMagicMode" :effect-name="magicEffectData" @toggle-active="(val) => isMagicMode = val" />

        <!-- 顶部控制栏 -->
        <div class="top-section">
            <TopBar :is-weather-board-mode="isWeatherBoardMode" :theme="colorTheme" @activate-magic="handleActivateMagic"
                @open-chat="openChat" @open-toolbox="openToolbox" @open-compass="openCompassPanel"
                @open-bus="openBusPlanner" @open-drive="openDrivePlanner" @toggle-weather-board="toggleWeatherBoardMode"
                @open-weather="openWeatherPanel"
                @activate-feature="handleActivateFeature"
                @toggle-account-center="handleToggleAccountPanel" @toggle-theme="toggleColorTheme" />
        </div>

        <!-- 用户公告栏 -->
        <PersistentAnnouncementBar />

        <div class="content-section">
            <!-- 侧边控制栏（左）-->
            <div class="Control-panel">
                <ControlsPanel @open-tab="handleControlsOpenTab" @map-interaction="handleControlsMapInteraction"
                    @show-analysis="handleControlsShowAnalysis" @district-select="handleControlsDistrictSelect"
                    @enable-basemap-swipe="handleEnableBasemapSwipe" />
            </div>


            <!-- 地图2D、3D、天气面板容器 -->
            <div class="map-wrapper"
                :class="{ 'weather-mode': isWeatherBoardMode, 'account-fullscreen': isAccountPanelFullscreen }">
                <!-- 
                    将用户中心面板移动到 MapContainer 内部/同级，并通过 CSS 设置其位于顶部，避免被底部控件遮挡
                -->
                <FloatingAccountPanel class="home-account-panel" v-model:open="isAccountPanelOpen" :show-fab="false"
                    @fullscreen-change="handleAccountPanelFullscreenChange" />
                <!-- 
                  优化点：
                  1. MapContainer 使用 v-show。2D地图是核心，需优先加载且切换3D时不销毁(保持状态)。
                  2. CesiumContainer 使用 v-if。3D地图很重，只有需要时才渲染 DOM。
                -->
                <Suspense>
                    <template #default>
                        <MapContainer ref="mapContainerRef"
                            v-show="!is3DMode && !isWeatherBoardMode && !isAccountPanelFullscreen"
                            @map-core-ready="handleMapCoreReady" @map-core-failed="handleMapCoreFailed"
                            @location-change="handleLocationChange" @search-poi-selected="handleSearchPoiSelected"
                            @map-click="handleMapClick" @update-news-image="handleUpdateNewsImage"
                            @feature-selected="handleFeatureSelected" @user-layers-change="handleUserLayersChange"
                            @graphics-overview="handleGraphicsOverview"
                            @upload-progress-change="handleUploadProgressChange"
                            @base-layers-change="handleBaseLayersChange" />
                    </template>
                    <template #fallback>
                        <div v-show="!is3DMode && !isWeatherBoardMode && !isAccountPanelFullscreen"
                            class="map-runtime-loading">
                            地图核心资源加载中...
                        </div>
                    </template>
                </Suspense>

                <component :is="WeatherChartPanel"
                    v-if="isWeatherBoardMode && shouldLoadWeatherChartPanel && !isAccountPanelFullscreen"
                    class="weather-board-surface" />

                <!-- <transition name="query-panel-fade">
                    <div v-if="showQueryPanel && !is3DMode && !isWeatherBoardMode && !isAccountPanelFullscreen" class="query-panel">
                        <div class="query-panel-header">
                            <div>
                                <div class="query-title">属性查询结果</div>
                                <div class="query-subtitle">
                                    绘制 {{ toolboxOverview.drawCount }} | 上传 {{ toolboxOverview.uploadCount }}
                                </div>
                            </div>
                            <button class="query-close" @click="closeQueryPanel">×</button>
                        </div>
                        <div class="query-panel-body">
                            <div
                                v-for="([key, value], idx) in Object.entries(featureQueryResult || {})"
                                :key="`${key}_${idx}`"
                                class="query-row"
                            >
                                <span class="query-key">{{ key }}</span>
                                <span class="query-val">{{ value }}</span>
                            </div>
                            <div v-if="Object.keys(featureQueryResult || {}).length === 0" class="query-empty">
                                当前要素没有可展示属性
                            </div>
                        </div>
                    </div>
                </transition> -->
                <transition name="query-panel-fade">
                    <div v-if="showQueryPanel && !is3DMode && !isWeatherBoardMode && !isAccountPanelFullscreen"
                        class="eco-query-panel">
                        <!-- 头部：使用你顶栏那样的鲜艳绿 -->
                        <div class="eco-header">
                            <div class="header-content">
                                <info-icon :size="18" :stroke-width="2" class="eco-header-icon" />
                                <span class="eco-title">属性信息</span>
                            </div>
                            <button class="eco-close" @click="closeQueryPanel" title="关闭属性信息">
                                <x-icon :size="16" :stroke-width="2" />
                            </button>
                        </div>

                        <div class="eco-body">
                            <!-- 统计小标签：模仿你用户面板的浅绿色调 -->
                            <div class="eco-stats">
                                <span class="eco-tag">绘制: {{ toolboxOverview.drawCount }}</span>
                                <span class="eco-tag">上传: {{ toolboxOverview.uploadCount }}</span>
                            </div>

                            <div class="eco-list-container">
                                <div v-for="([key, value], idx) in Object.entries(featureQueryResult || {})"
                                    :key="`${key}_${idx}`" class="eco-item">
                                    <div class="eco-key">{{ key }}</div>
                                    <div class="eco-val">{{ value }}</div>
                                </div>

                                <!-- 空状态 -->
                                <div v-if="Object.keys(featureQueryResult || {}).length === 0" class="eco-empty">
                                    未发现属性数据
                                </div>
                            </div>
                        </div>
                    </div>
                </transition>

                <!-- 3D 图层自动触发的 Cesium 视图（首次使用懒加载） -->
                <div v-if="isCesiumLoaded" v-show="is3DMode && !isAccountPanelFullscreen" class="cesium-wrapper"
                    style="position: absolute; width: 100%; height: 100%; inset: 0; z-index: 5;">
                    <component :is="CesiumContainer" ref="cesiumContainerRef" />
                </div>
                <div v-if="isCesiumLoading && !isAccountPanelFullscreen" class="cesium-loading">
                    <div class="cesium-loading-spinner"></div>
                    <span>加载 3D 引擎...</span>
                </div>
            </div>

            <!-- 侧边容器栏（右）-->
            <div class="side-panel-wrapper"
                :class="{ 'collapsed': isSidePanelCollapsed, 'weather-mode': isWeatherBoardMode }">
                <!-- 使用v-if延迟加载SidePanel，避免初始化时加载大量图片资源 -->
                <SidePanel v-if="shouldLoadSidePanel" :locationInfo="locationInfo" :selectedImage="selectedImage"
                    :isCollapsed="isSidePanelCollapsed" :activeTab="activeSidePanelTab" :activeFeature="activeFeature"
                    :userLayers="userLayers" :baseLayers="baseLayers" :toolboxOverview="toolboxOverview"
                    :uploadProgress="uploadProgress" :latest-search-poi="latestSearchPoi"
                    :get-user-location="getMapUserLocation" :start-bus-point-pick="startBusPointPick"
                    :draw-route-on-map="drawRouteOnMap" :zoom-to-bus-route-step="zoomToBusRouteStep"
                    :preview-bus-route-step="previewBusRouteStep"
                    :clear-bus-route-step-preview="clearBusRouteStepPreview"
                    :draw-drive-route-on-map="drawDriveRouteOnMap" :zoom-to-drive-route-step="zoomToDriveRouteStep"
                    :preview-drive-route-step="previewDriveRouteStep"
                    :clear-drive-route-step-preview="clearDriveRouteStepPreview" @upload-data="handleUploadData"
                    @interaction="handleInteraction" @toggle-layer-visibility="handleToggleLayerVisibility"
                    @change-layer-opacity="handleChangeLayerOpacity" @set-base-layer="handleSetBaseLayer"
                    @toggle-base-layer-visibility="handleToggleBaseLayerVisibility"
                    @toggle-layer-label-visibility="handleToggleLayerLabelVisibility" @set-layer-label-field="handleSetLayerLabelField" @zoom-layer="handleZoomLayer"
                    @view-layer="handleViewLayer" @remove-layer="handleRemoveLayer"
                    @reorder-user-layers="handleReorderUserLayers" @solo-layer="handleSoloLayer"
                    @apply-style-template="handleApplyStyleTemplate" @update-draw-style="handleUpdateDrawStyle"
                    @update-layer-style="handleUpdateLayerStyle"
                    @highlight-attribute-feature="handleHighlightAttributeFeature"
                    @zoom-attribute-feature="handleZoomAttributeFeature" @layer-selected="handleLayerSelected"
                    @draw-point-by-coordinates="handleDrawPointByCoordinates"
                    @draw-amap-aoi-from-json="handleDrawAmapAoiFromJson" @toggle-layer-crs="handleToggleLayerCRS"
                    @export-layer-data="handleExportLayerData" @switch-tab="handleSwitchSidePanelTab"
                    @news-changed="handleNewsChanged" @toggle-panel="toggleSidePanel" @close-chat="handleCloseChat"
                    @upload-shp-3d="handleUploadShp3D" @upload-3dtiles-zip="handleUpload3DTilesZip"
                    @load-3dtiles-url="handleLoad3DTilesUrl">
                    <template v-slot:extra-content>
                        <div class="extra-info">
                            <h3>提示</h3>
                            <p>缩放地图以查看更多细节</p>
                        </div>
                    </template>
                </SidePanel>
                <!-- 未加载时显示展开提示 -->
                <div v-else class="panel-placeholder" @click="toggleSidePanel">
                    <div class="placeholder-content">
                        <svg class="placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
                        </svg>
                        <span class="placeholder-text">展开</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- 全局上传进度条 -->
    <Teleport to="body">
        <transition name="upload-progress-fade">
            <div v-if="showUploadProgressBar" class="global-upload-progress">
                <div class="global-upload-inner">
                    <div class="global-upload-icon">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M12 16V5"></path><path d="m8 9 4-4 4 4"></path>
                            <path d="M20 16.5a3.5 3.5 0 0 1-3.5 3.5h-9A3.5 3.5 0 0 1 4 16.5"></path>
                        </svg>
                    </div>
                    <div class="global-upload-text">
                        <span class="global-upload-label">{{ uploadProgressLabelText }}</span>
                        <span class="global-upload-count">{{ uploadProgressView.current }}/{{ uploadProgressView.total || 1 }}</span>
                    </div>
                    <div class="global-upload-bar-wrap">
                        <div class="global-upload-bar">
                            <div class="global-upload-fill" :class="`phase-${uploadProgressView.phase}`" :style="{ width: uploadProgressPercent + '%' }"></div>
                        </div>
                    </div>
                    <div class="global-upload-summary">
                        <span class="stat-ok">
                            <check-icon :size="13" :stroke-width="2.4" />
                            {{ uploadProgressView.success }}
                        </span>
                        <span v-if="uploadProgressView.failed" class="stat-fail">
                            <triangle-alert-icon :size="13" :stroke-width="2.2" />
                            {{ uploadProgressView.failed }}
                        </span>
                    </div>
                </div>
            </div>
        </transition>
    </Teleport>
</template>

<style scoped>
/* 
   CSS 样式 
*/
.home-container {
    display: flex;
    flex-direction: column;
    height: 100%;
    width: 100%;
    box-sizing: border-box;
    background: var(--deep-0);
    overflow: clip;
}

:root[data-theme="light"] .home-container {
    background:
        radial-gradient(circle at 18% 12%, rgba(255, 255, 255, 0.92), transparent 26%),
        radial-gradient(circle at 88% 8%, rgba(226, 173, 66, 0.14), transparent 28%),
        linear-gradient(135deg, #e8f4eb 0%, #f9fbf2 52%, #dcebe2 100%);
}

.top-section {
    height: 56px;
    flex-shrink: 0;
    width: 100%;
    z-index: 50;
}

.content-section {
    display: flex;
    flex: 1;
    width: 100%;
    min-height: 0;
    gap: 8px;
    padding: 8px 10px 10px 0;
    box-sizing: border-box;
    overflow: clip;
    background:
        linear-gradient(90deg, rgba(255, 255, 255, 0.025), transparent 36%),
        var(--deep-0);
}

.Control-panel {
    width: 64px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0;
    background: transparent;
    box-shadow: none;
}

.map-wrapper {
    flex: 1;
    background: var(--deep-1);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    position: relative;
    isolation: isolate;
    overflow: hidden;
    display: flex;
    min-width: 0;
    margin: 0;
    z-index: 1;
    box-shadow: var(--shadow-panel);
}

:root[data-theme="light"] .map-wrapper {
    background:
        linear-gradient(135deg, rgba(54, 74, 70, 0.08), rgba(255, 255, 255, 0.18)),
        var(--deep-1);
}

.map-runtime-loading {
    position: absolute;
    inset: 0;
    z-index: 4;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--glass-bg-heavy);
    color: var(--neon-cyan);
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.3px;
}

.weather-board-surface {
    width: 100%;
    height: 100%;
}

/* 用户中心面板 (由 HomeView 配置覆盖位置) */
:deep(.home-account-panel) {
    position: absolute !important;
    top: 12px !important;
    left: 224px !important;
    /* 位于鹰眼(左侧, 宽200px)的右侧 */
    bottom: auto !important;
    z-index: 2200 !important;
    /* 高于地图和其他组件 */
    flex-direction: column !important;
    /* 调整流向为向下展开 */
}

/* 设置向下展开的动画源点及过渡方向 */
:deep(.home-account-panel .account-panel) {
    transform-origin: top left !important;
}

:deep(.home-account-panel .account-panel-transition-enter-from),
:deep(.home-account-panel .account-panel-transition-leave-to) {
    transform: translateY(-14px) scale(0.96) !important;
}

:deep(.home-account-panel.is-fullscreen) {
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    z-index: 5000 !important;
    /* 在 map-wrapper 内封顶 */
    gap: 0 !important;
}

:deep(.home-account-panel.is-fullscreen .account-panel) {
    position: absolute !important;
    inset: 0 !important;
    width: 100% !important;
    height: 100% !important;
    z-index: 5001 !important;
    border-radius: var(--radius-lg) !important;
    clip-path: none !important;
}

@media (max-width: 768px) {
    :deep(.home-account-panel) {
        top: 8px !important;
        left: 8px !important;
        right: 8px !important;
        width: auto !important;
        max-width: none !important;
        /* Mobile follows the map area width and sits just under the top bar */
    }

    /* 隐藏控制面板 */
    .Control-panel {
        display: none;
    }
}

/* 如果覆盖地图默认放大缩小控件，将其推开 */
:deep(.ol-zoom) {
    top: 96px !important;
    left: 18px !important;
}

:deep(.cesium-viewer-toolbar) {
    top: 80px !important;
}

.cesium-loading {
    position: absolute;
    inset: 0;
    z-index: 20;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-md);
    background: var(--glass-bg-heavy);
    backdrop-filter: blur(8px);
    color: var(--neon-cyan);
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    letter-spacing: 0.1em;
}
.cesium-loading-spinner {
    width: 32px;
    height: 32px;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--neon-cyan);
    border-radius: 50%;
    animation: cesium-spin 0.8s linear infinite;
}
@keyframes cesium-spin {
    to { transform: rotate(360deg); }
}

.weather-loading-state {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    gap: 10px;
    background: var(--glass-bg-heavy);
    color: var(--text-secondary);
    z-index: 4;
}

/* 面板主体 */
.eco-query-panel {
    position: absolute;
    left: 18px;
    bottom: 18px;
    width: 320px;
    background: var(--glass-bg-heavy);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-elevated);
    overflow: hidden;
    border: 1px solid var(--glass-border);
    z-index: 2000;
    color: var(--text-primary);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
}

.eco-header {
    background: linear-gradient(135deg, var(--neon-cyan-dim), var(--neon-green-dim));
    padding: 12px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--text-primary);
}

.eco-header-icon {
    color: var(--neon-cyan);
    flex-shrink: 0;
}

.eco-title {
    font-weight: 600;
    font-size: 15px;
    letter-spacing: 1px;
}

.header-content {
    display: flex;
    align-items: center;
    gap: 8px;
}

.eco-close {
    background: var(--surface-1);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    width: 36px;
    height: 36px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition:
        background-color var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
}

.eco-close:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
    color: var(--neon-cyan);
    transform: scale(1.04);
}

/* 内容区 */
.eco-body {
    padding: 16px;
}

/* 统计标签：对标你的 user_1 绿色胶囊样式 */
.eco-stats {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
}

.eco-tag {
    background: var(--neon-green-dim);
    color: var(--neon-green);
    padding: 4px 12px;
    border-radius: var(--radius-full);
    font-size: 11px;
    font-weight: bold;
    border: 1px solid rgba(139, 209, 124, 0.24);
}

/* 属性列表 */
.eco-list-container {
    max-height: 260px;
    overflow-y: auto;
    padding-right: 4px;
}

/* 自定义滚动条 */
.eco-list-container::-webkit-scrollbar {
    width: 4px;
}

.eco-list-container::-webkit-scrollbar-thumb {
    background: var(--neon-cyan);
    border-radius: 10px;
}

/* 属性单项 */
.eco-item {
    padding: 10px 0;
    border-bottom: 1px dashed var(--border-subtle);
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.eco-item:last-child {
    border-bottom: none;
}

.eco-key {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    font-weight: bold;
}

.eco-val {
    font-size: 13px;
    color: var(--text-secondary);
    font-weight: 500;
    word-break: break-all;
}

/* 空状态 */
.eco-empty {
    text-align: center;
    color: var(--text-muted);
    font-size: 12px;
    padding: 20px 0;
}

/* 动画 */
.query-panel-fade-enter-active,
.query-panel-fade-leave-active {
    transition:
        opacity var(--duration-panel) var(--ease-spatial),
        transform var(--duration-panel) var(--ease-spring-subtle);
}

.query-panel-fade-enter-from,
.query-panel-fade-leave-to {
    opacity: 0;
    transform: translateY(20px) scale(0.95);
}

.side-panel-wrapper {
    width: 408px;
    flex-shrink: 0;
    background: transparent;
    border-radius: 0;
    overflow: visible !important;
    position: relative;
    display: flex;
    flex-direction: column;
    transition:
        width var(--duration-panel) var(--ease-spring-subtle),
        height var(--duration-panel) var(--ease-spring-subtle);
    z-index: 2;
}

.side-panel-wrapper.collapsed {
    width: 0px;
}

/* 侧边栏占位符样式 */
.panel-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    background: var(--glass-bg-heavy);
    border-left: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
    transition:
        background-color var(--duration-normal) var(--ease-spatial),
        border-color var(--duration-normal) var(--ease-spatial),
        box-shadow var(--duration-normal) var(--ease-spatial),
        transform var(--duration-normal) var(--ease-spatial);
    position: relative;
    overflow: hidden;
}

.panel-placeholder::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(71, 215, 198, 0.2), transparent);
    transition: left var(--duration-slow) var(--ease-panel);
}

.panel-placeholder:hover {
    background: var(--surface-hover);
    border-left-color: var(--border-active);
    box-shadow: inset 0 0 20px var(--neon-cyan-dim);
}

.panel-placeholder:hover::before {
    left: 100%;
}

.panel-placeholder:active {
    transform: scale(0.98);
}

.placeholder-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 12px 6px;
}

.placeholder-icon {
    width: 28px;
    height: 28px;
    color: var(--neon-cyan);
    transition:
        color var(--duration-normal) var(--ease-spatial),
        filter var(--duration-normal) var(--ease-spatial),
        transform var(--duration-normal) var(--ease-spatial);
    filter: drop-shadow(0 2px 4px rgba(71, 215, 198, 0.22));
}

.panel-placeholder:hover .placeholder-icon {
    color: var(--text-primary);
    transform: translateX(-3px);
    filter: drop-shadow(0 3px 6px rgba(71, 215, 198, 0.38));
}

.placeholder-text {
    writing-mode: vertical-rl;
    font-size: 13px;
    font-weight: 600;
    color: var(--neon-cyan);
    letter-spacing: 0;
    text-shadow: 0 1px 2px rgba(71, 215, 198, 0.16);
    transition:
        color var(--duration-normal) var(--ease-spatial),
        text-shadow var(--duration-normal) var(--ease-spatial);
}

.panel-placeholder:hover .placeholder-text {
    color: var(--text-primary);
    text-shadow: 0 2px 4px rgba(71, 215, 198, 0.22);
}

.sidepanel-loading-state {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    background: var(--glass-bg-heavy);
}

.sidepanel-loading-spinner {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid var(--border-subtle);
    border-top-color: var(--neon-cyan);
    animation: sidepanel-spin 0.8s linear infinite;
}

.sidepanel-loading-text {
    font-size: 12px;
    color: var(--neon-cyan);
    font-weight: 600;
}

@keyframes sidepanel-spin {
    from {
        transform: rotate(0deg);
    }

    to {
        transform: rotate(360deg);
    }
}

/* Mobile Responsiveness */
@media (max-width: 768px) {
    .content-section {
        flex-direction: column;
        padding: 0px;
        gap: 0px;
    }

    .map-wrapper {
        flex: 1;
        /* Map takes available space */
        min-height: 50vh;
        /* Ensure map has height */
        margin: 2px;
        border-radius: var(--radius-md);
    }

    .map-wrapper.weather-mode {
        min-height: 58vh;
    }

    .query-panel {
        width: calc(100% - 20px);
        left: 10px;
        bottom: 10px;
        max-height: 36vh;
    }

    .query-row {
        grid-template-columns: 90px 1fr;
    }

    .side-panel-wrapper {
        width: 100%;
        height: 40vh;
        /* Fixed height for bottom panel on mobile */
        flex: none;
    }

    .side-panel-wrapper.weather-mode {
        height: 32vh;
    }

    .side-panel-wrapper.collapsed {
        height: 0px;
        width: 100%;
    }

    /* 移动端占位符横向布局 */
    .placeholder-content {
        flex-direction: row;
        padding: 8px 16px;
        justify-content: center;
    }

    .placeholder-icon {
        width: 24px;
        height: 24px;
        transform: rotate(90deg);
    }

    .panel-placeholder:hover .placeholder-icon {
        transform: rotate(90deg) translateY(-3px);
    }

    .placeholder-text {
        writing-mode: horizontal-tb;
        font-size: 14px;
        letter-spacing: 1px;
    }
}

.extra-info {
    padding: 10px;
    background: var(--surface-1);
    border-radius: var(--radius-md);
    margin-top: 10px;
}

/* ========== 全局上传进度条 ========== */
.global-upload-progress {
    position: fixed;
    bottom: 5vh;
    left: 50%;
    transform: translateX(-50%);
    z-index: 9999;
    min-width: 360px;
    max-width: 520px;
    background: var(--glass-bg-heavy);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    padding: 14px 18px;
    color: var(--text-primary);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
    font-family: "Noto Sans SC", sans-serif;
}
.global-upload-inner {
    display: flex;
    align-items: center;
    gap: 12px;
}
.global-upload-icon {
    flex-shrink: 0;
    color: var(--neon-green);
    opacity: 0.9;
}
.global-upload-text {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 80px;
}
.global-upload-label {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.global-upload-count {
    font-size: 10px;
    opacity: 0.55;
    font-family: "IBM Plex Mono", monospace;
}
.global-upload-bar-wrap {
    flex: 1;
    min-width: 100px;
}
.global-upload-bar {
    height: 6px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    overflow: hidden;
}
.global-upload-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-green));
    transition: width var(--duration-slow) var(--ease-panel);
}
.global-upload-fill.phase-error {
    background: linear-gradient(90deg, var(--accent-rose), #c7525c);
}
.global-upload-fill.phase-done {
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-green));
}
.global-upload-summary {
    flex-shrink: 0;
    display: flex;
    gap: 8px;
    font-size: 11px;
}
.stat-ok {
    color: var(--neon-green);
    display: inline-flex;
    align-items: center;
    gap: 4px;
}
.stat-fail {
    color: var(--accent-rose);
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

/* 入场/离场动效 */
.upload-progress-fade-enter-active {
    transition:
        opacity var(--duration-panel) var(--ease-spatial),
        transform var(--duration-panel) var(--ease-spring-subtle);
}
.upload-progress-fade-leave-active {
    transition:
        opacity var(--duration-normal) var(--ease-spatial),
        transform var(--duration-normal) var(--ease-spatial);
}
.upload-progress-fade-enter-from {
    opacity: 0;
    transform: translateX(-50%) translateY(18px);
}
.upload-progress-fade-leave-to {
    opacity: 0;
    transform: translateX(-50%) translateY(12px);
}
</style>
