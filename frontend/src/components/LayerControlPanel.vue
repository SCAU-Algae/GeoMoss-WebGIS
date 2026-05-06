<template>
    <div class="layer-switcher">
        <LocationSearch :fetcher="fetchLocationResults" :services="serviceOptions"
            storageKey="map_search_selected_service" @select-result="handleSearchJump" />

        <div class="layer-label">选择底图</div>
        <select class="layer-select" :value="selectedLayer" @change="handleLayerChange">
            <option v-for="option in BASEMAP_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
            </option>
        </select>

        <button ref="layerManageButtonRef" class="layer-manage-btn" @click="toggleLayerManager" title="图层管理">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path
                    d="M12 2L2 7l10 5 10-5-10-5zm0 9l2.5-1.25L12 8 9.5 9.25 12 11zm0 2.5l-5-2.5-2 1L12 15.5l7-3.5-2-1-5 2.5zm0 5l-5-2.5-2 1L12 21l7-3.5-2-1-5 2.5z" />
            </svg>
        </button>

        <button class="graticule-btn" :class="{ active: activeGraticule }" @click="emit('toggle-graticule')"
            title="经纬度分割线">
            经纬线
        </button>

        <button v-if="basemapCircuitOpen" class="basemap-reset-btn" @click="emit('reset-basemap-chain')"
            title="当前网络异常，点击重置底图链路">
            重置链路
        </button>

        <div v-if="selectedLayer === 'custom'" class="custom-url-wrapper">
            <input v-model="customUrlInput" class="custom-url-input" placeholder="支持 XYZ / WMS / WMTS 服务 URL" />
            <button class="custom-url-btn" @click="submitCustomUrl" title="加载">ok</button>
            <div v-if="detectedServiceInfo" class="detected-format-hint">
                ✓ 已识别: {{ detectedServiceInfo.name }}
            </div>
        </div>

        <Teleport to="body">
            <div v-if="showLayerManager" class="layer-manager-panel" :style="layerManagerPanelStyle">
                <div class="panel-header">
                    <span>图层排序与显示</span>
                    <span class="close-panel-btn" @click="showLayerManager = false">×</span>
                </div>
                <div class="layer-list">
                    <div v-for="(layer, index) in layerList" :key="layer.id" class="layer-item"
                        :draggable="!isTouchDevice" @dragstart="onDragStart($event, index)" @dragend="onDragEnd"
                        @dragover.prevent @drop="onDrop($event, index)"
                        @contextmenu.prevent="onLayerContextMenu(layer, index, $event)"
                        @touchstart="onLayerTouchStart(layer, index, $event)" @touchmove="onLayerTouchMove"
                        @touchend="onLayerTouchEnd" :class="{ dragging: draggingIndex === index }">
                        <div class="drag-handle" v-if="!isTouchDevice">⋮⋮</div>
                        <div class="drag-handle mobile-hint" v-if="isTouchDevice">⋯</div>
                        <input type="checkbox" :checked="layer.visible" @change="updateLayerVisibility(layer, $event)">
                        <span class="layer-name">{{ layer.name }}</span>
                    </div>
                </div>
            </div>
        </Teleport>

        <Teleport to="body">
            <div v-if="showLayerContextMenu" class="layer-context-menu" :style="layerContextMenuStyle"
                @contextmenu.prevent>
                <div class="context-menu-item context-has-submenu" @mouseenter="showUrlSubmenu = true"
                    @mouseleave="showUrlSubmenu = false">
                    <span>URL 操作</span>
                    <span class="submenu-arrow">▶</span>
                    <div v-if="showUrlSubmenu" class="context-submenu" :style="layerContextSubmenuStyle">
                        <button class="context-menu-item" @click="triggerLayerContextAction('copy-url')">复制 URL</button>
                        <button class="context-menu-item" @click="triggerLayerContextAction('view-url')">查看 URL</button>
                    </div>
                </div>

                <!-- 透明度控制 -->
                <div class="context-menu-item context-opacity-control">
                    <span class="opacity-label">透明度</span>
                    <input type="range" min="0" max="100"
                        :value="Math.round((layerOpacityMap.get(contextMenuLayer?.id) ?? 1) * 100)"
                        @input="updateLayerOpacity($event)" class="opacity-slider" title="调整图层透明度" />
                    <span class="opacity-value">{{ Math.round((layerOpacityMap.get(contextMenuLayer?.id) ?? 1) * 100)
                        }}%</span>
                </div>

                <button class="context-menu-item" @click="moveContextLayerToTop">图层置顶</button>
                <button class="context-menu-item" @click="moveContextLayerToBottom">图层置底</button>
            </div>
        </Teleport>
    </div>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { toLonLat } from 'ol/proj';
import { apiSearchLocations } from '../api';
import { BASEMAP_OPTIONS } from '../constants';
import { detectCustomTileServiceKind } from '../composables/useTileSourceFactory';

// ========== 异步导入子组件 ==========
/** 地名搜索组件，支持多个服务源（天地图、国际、高德） */
const LocationSearch = defineAsyncComponent(() => import('./LocationSearch.vue'));

// BASEMAP_OPTIONS 已从 useBasemapManager 导入，无需本地重新定义

// ========== 组件 Props 定义 ==========
/**
 * @prop {Object} mapInstance - OpenLayers Map 实例（ShallowRef 包装）
 * @prop {Array} layerList - 当前图层列表，每项含 { id, name, visible }
 * @prop {Boolean} activeGraticule - 经纬网是否激活对象常用
 * @prop {String} selectedLayer - 当前选中底图的 ID
 * @prop {String} customMapUrl - 自定义 XYZ 底图 URL
 * @prop {String} tiandituTk - 天地图 Token
 * @prop {Boolean} isDomestic - 是否国内访问环境（用于服务推荐排序）
 * @prop {Array} services - 启用的地名检索服务列表（如 ['tianditu', 'nominatim']）
 */
const props = defineProps({
    mapInstance: {
        type: Object,
        default: null
    },
    layerList: {
        type: Array,
        default: () => []
    },
    activeGraticule: {
        type: Boolean,
        default: false
    },
    basemapCircuitOpen: {
        type: Boolean,
        default: false
    },
    selectedLayer: {
        type: String,
        default: 'google'
    },
    customMapUrl: {
        type: String,
        default: ''
    },
    tiandituTk: {
        type: String,
        default: ''
    },
    isDomestic: {
        type: Boolean,
        default: true
    },
    services: {
        type: Array,
        default: () => []
    }
});

/**
 * @event change-layer 触发底图切换，payload: { layerId, source, customUrl? }
 * @event update-order 触发图层排序/显隐更新，payload: { type, dragIndex?, dropIndex?, layerId?, visible?, opacity? }
 * @event toggle-graticule 触发经纬网开关
 * @event search-jump 触发搜索结果定位，payload: { lng, lat, zoom, name, raw }
 * @event layer-context-action 触发图层右键菜单动作，payload: { action, layerId, layerName, layerIndex }
 */
const emit = defineEmits([
    'change-layer',
    'update-order',
    'toggle-graticule',
    'search-jump',
    'reset-basemap-chain',
    'layer-context-action'
]);

const layerManageButtonRef = ref(null);
const showLayerManager = ref(false);
const draggingIndex = ref(-1);
const customUrlInput = ref(props.customMapUrl || '');
const layerManagerAnchor = ref({ top: 0, left: 0 });
const detectedServiceInfo = ref(null); // 检测到的服务类型信息
const showLayerContextMenu = ref(false);
const showUrlSubmenu = ref(false);
const contextMenuLayer = ref(null);
const layerContextMenuAnchor = ref({ top: 0, left: 0 });
const layerOpacityMap = ref(new Map()); // 存储图层透明度，key: layerId, value: opacity (0-1)
const isTouchDevice = ref(false); // 是否是触摸设备

// 移动端长按检测
const longPressTimer = ref(null);
const longPressTouchStart = ref({ x: 0, y: 0, target: null });
const LONG_PRESS_DURATION = 500; // 长按时间阈值（毫秒）
const LONG_PRESS_DRIFT = 10; // 移动距离阈值（像素）

const PANEL_WIDTH = 200;
const CONTEXT_MENU_WIDTH = 152;
const CONTEXT_SUBMENU_WIDTH = 136;

const serviceOptions = computed(() => {
    if (Array.isArray(props.services) && props.services.length) return props.services;
    return [
        { value: 'tianditu', label: props.isDomestic ? '天地图（推荐）' : '天地图' },
        { value: 'nominatim', label: props.isDomestic ? '国际（Nominatim）' : '国际（推荐）' },
        { value: 'amap', label: '高德（Amap）' }
    ];
});

const layerManagerPanelStyle = computed(() => ({
    top: `${layerManagerAnchor.value.top}px`,
    left: `${layerManagerAnchor.value.left}px`
}));

const layerContextMenuStyle = computed(() => ({
    top: `${layerContextMenuAnchor.value.top}px`,
    left: `${layerContextMenuAnchor.value.left}px`
}));

const layerContextSubmenuStyle = computed(() => {
    if (typeof window === 'undefined') {
        return { left: `${CONTEXT_MENU_WIDTH - 4}px`, top: '0px' };
    }

    const availableRight = window.innerWidth - layerContextMenuAnchor.value.left;
    const canOpenRight = availableRight > (CONTEXT_MENU_WIDTH + CONTEXT_SUBMENU_WIDTH + 20);

    return {
        left: canOpenRight ? `${CONTEXT_MENU_WIDTH - 4}px` : `-${CONTEXT_SUBMENU_WIDTH + 4}px`,
        top: '0px'
    };
});

watch(
    () => props.customMapUrl,
    (value) => {
        customUrlInput.value = value || '';
    }
);

/**
 * 监听自定义 URL 输入，实时检测服务类型
 */
watch(customUrlInput, (newUrl) => {
    if (!newUrl || !newUrl.trim()) {
        detectedServiceInfo.value = null;
        return;
    }

    const detected = detectCustomTileServiceKind(newUrl);
    detectedServiceInfo.value = detected.kind === 'unknown' ? null : detected;
});

function handleLayerChange(event) {
    emit('change-layer', {
        layerId: event.target.value,
        source: 'dropdown'
    });
}

/**
 * 获取当前地图范围（SW,NE）用于后端搜索裁剪。
 * @returns {string|undefined} 形如 "minLon,minLat,maxLon,maxLat"
 */
function getCurrentMapBound() {
    try {
        const map = props.mapInstance?.value;
        if (!map) return undefined;
        const view = map.getView?.();
        const size = map.getSize?.();
        if (!view || !size) return undefined;

        const extent = view.calculateExtent(size);
        const sw = toLonLat([extent[0], extent[1]]);
        const ne = toLonLat([extent[2], extent[3]]);
        return `${sw[0].toFixed(6)},${sw[1].toFixed(6)},${ne[0].toFixed(6)},${ne[1].toFixed(6)}`;
    } catch {
        return undefined;
    }
}

/**
 * 面板内部接管地名检索请求，统一接入天地图/高德/Nominatim。
 */
function fetchLocationResults({ service, keywords, page = 1, pageSize = 10 }) {
    return apiSearchLocations({
        service,
        keywords,
        page,
        pageSize,
        tiandituTk: props.tiandituTk,
        mapBound: getCurrentMapBound()
    }).then((response) => response?.data || { items: [], total: 0 });
}

function submitCustomUrl() {
    emit('change-layer', {
        layerId: 'custom',
        source: 'custom-url',
        customUrl: customUrlInput.value
    });
}

function onDragStart(evt, index) {
    // 移动端禁用拖动
    if (isTouchDevice.value) {
        evt.preventDefault();
        return;
    }
    draggingIndex.value = index;
    evt.dataTransfer.effectAllowed = 'move';
}

function onDragEnd() {
    draggingIndex.value = -1;
}

function onDrop(evt, dropIndex) {
    if (isTouchDevice.value) {
        evt.preventDefault();
        return;
    }
    if (draggingIndex.value < 0) return;
    emit('update-order', {
        type: 'reorder',
        dragIndex: draggingIndex.value,
        dropIndex
    });
    draggingIndex.value = -1;
}

function closeLayerContextMenu() {
    showLayerContextMenu.value = false;
    showUrlSubmenu.value = false;
    contextMenuLayer.value = null;
}

function onLayerContextMenu(layer, index, event) {
    if (!layer?.id || !event) return;

    const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 0;
    const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 0;
    const maxLeft = Math.max(8, viewportWidth - CONTEXT_MENU_WIDTH - 8);
    const maxTop = Math.max(8, viewportHeight - 140);

    layerContextMenuAnchor.value = {
        left: Math.min(Math.max(8, event.clientX), maxLeft),
        top: Math.min(Math.max(8, event.clientY), maxTop)
    };

    contextMenuLayer.value = {
        id: String(layer.id),
        name: String(layer.name || layer.id),
        index: Number(index)
    };
    showUrlSubmenu.value = false;
    showLayerContextMenu.value = true;
}

function triggerLayerContextAction(action) {
    const layer = contextMenuLayer.value;
    if (!layer?.id) return;

    emit('layer-context-action', {
        action,
        layerId: layer.id,
        layerName: layer.name,
        layerIndex: layer.index
    });
    closeLayerContextMenu();
}

/**
 * 清除长按计时器
 */
function clearLongPressTimer() {
    if (longPressTimer.value) {
        clearTimeout(longPressTimer.value);
        longPressTimer.value = null;
    }
}

/**
 * 处理 touchstart 事件，启动长按计时
 */
function onLayerTouchStart(layer, index, event) {
    if (!isTouchDevice.value) return;

    const touches = event.touches;
    if (touches.length !== 1) {
        clearLongPressTimer();
        return;
    }

    longPressTouchStart.value = {
        x: touches[0].clientX,
        y: touches[0].clientY,
        target: event.currentTarget
    };

    clearLongPressTimer();
    longPressTimer.value = setTimeout(() => {
        // 长按时间到达，显示右键菜单
        const touch = event.touches[0];
        onLayerContextMenu(layer, index, {
            clientX: touch.clientX,
            clientY: touch.clientY,
            preventDefault: () => { }
        });
    }, LONG_PRESS_DURATION);
}

/**
 * 处理 touchmove 事件，如果移动距离过大则取消长按
 */
function onLayerTouchMove(event) {
    if (!isTouchDevice.value || !longPressTimer.value) return;

    const touches = event.touches;
    if (touches.length !== 1) {
        clearLongPressTimer();
        return;
    }

    const dx = touches[0].clientX - longPressTouchStart.value.x;
    const dy = touches[0].clientY - longPressTouchStart.value.y;
    const distance = Math.sqrt(dx * dx + dy * dy);

    if (distance > LONG_PRESS_DRIFT) {
        clearLongPressTimer();
    }
}

/**
 * 处理 touchend 事件，清除长按计时
 */
function onLayerTouchEnd() {
    clearLongPressTimer();
}

/**
 * 更新图层透明度
 */
function updateLayerOpacity(event) {
    const opacity = Number(event.target.value) / 100;
    const layer = contextMenuLayer.value;
    if (!layer?.id) return;

    layerOpacityMap.value.set(layer.id, opacity);
    emit('update-order', {
        type: 'opacity',
        layerId: layer.id,
        opacity
    });
}

function moveContextLayerToTop() {
    const index = Number(contextMenuLayer.value?.index);
    if (!Number.isInteger(index)) return;
    if (index <= 0) {
        closeLayerContextMenu();
        return;
    }

    emit('update-order', {
        type: 'reorder',
        dragIndex: index,
        dropIndex: 0
    });
    closeLayerContextMenu();
}

function moveContextLayerToBottom() {
    const index = Number(contextMenuLayer.value?.index);
    const lastIndex = props.layerList.length - 1;
    if (!Number.isInteger(index) || lastIndex < 0) return;
    if (index >= lastIndex) {
        closeLayerContextMenu();
        return;
    }

    emit('update-order', {
        type: 'reorder',
        dragIndex: index,
        dropIndex: lastIndex
    });
    closeLayerContextMenu();
}

function handleGlobalPointerDown(event) {
    if (!showLayerContextMenu.value) return;
    const target = event?.target;
    if (target instanceof Element && target.closest('.layer-context-menu')) return;
    closeLayerContextMenu();
}

function updateLayerVisibility(layer, event) {
    emit('update-order', {
        type: 'visibility',
        layerId: layer.id,
        visible: !!event?.target?.checked
    });
}

/**
 * 将 LocationSearch 原始结果解析成标准地图定位载荷。
 * 支持 lon/lat、x/y、lng/lat、lonlat 字符串等多来源字段。
 */
function handleSearchJump(payload) {
    const lonVal = payload?.lon ?? payload?.x ?? payload?.lng ?? payload?.lonlat?.split?.(',')?.[0];
    const latVal = payload?.lat ?? payload?.y ?? payload?.latit ?? payload?.lonlat?.split?.(',')?.[1];
    const sourceService = String(payload?._service || (payload?.id ? 'amap' : '')).trim().toLowerCase();

    const lng = lonVal != null ? Number.parseFloat(lonVal) : NaN;
    const lat = latVal != null ? Number.parseFloat(latVal) : NaN;

    emit('search-jump', {
        lng,
        lat,
        zoom: 16,
        name: String(payload?.display_name || payload?.name || '').trim(),
        service: sourceService,
        poiid: payload?.id ? String(payload.id).trim() : '',
        raw: payload
    });
}

function updateLayerManagerAnchor() {
    const buttonEl = layerManageButtonRef.value;
    if (!buttonEl) return;
    const rect = buttonEl.getBoundingClientRect();
    layerManagerAnchor.value = {
        top: Math.round(rect.bottom + 6),
        left: Math.round(Math.max(8, rect.right - PANEL_WIDTH))
    };
}

function toggleLayerManager() {
    showLayerManager.value = !showLayerManager.value;
}

function bindAnchorListeners() {
    window.addEventListener('resize', updateLayerManagerAnchor);
    window.addEventListener('scroll', updateLayerManagerAnchor, true);
}

function unbindAnchorListeners() {
    window.removeEventListener('resize', updateLayerManagerAnchor);
    window.removeEventListener('scroll', updateLayerManagerAnchor, true);
}

watch(showLayerManager, async (visible) => {
    if (!visible) {
        unbindAnchorListeners();
        draggingIndex.value = -1;
        closeLayerContextMenu();
        return;
    }

    await nextTick();
    updateLayerManagerAnchor();
    bindAnchorListeners();
});

onMounted(() => {
    window.addEventListener('pointerdown', handleGlobalPointerDown);

    // 检测是否为触摸设备
    isTouchDevice.value = (('ontouchstart' in window) ||
        (navigator.maxTouchPoints > 0) ||
        (navigator.msMaxTouchPoints > 0));
});

onBeforeUnmount(() => {
    unbindAnchorListeners();
    clearLongPressTimer();
    window.removeEventListener('pointerdown', handleGlobalPointerDown);
});
</script>

<style scoped>
.layer-switcher {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    background: var(--glass-bg-heavy);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
    border: 1px solid var(--glass-border);
    padding: 6px;
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-panel);
    z-index: 10;
    transition: transform var(--duration-normal) var(--ease-panel),
        border-color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-normal) var(--ease-spatial);
}

@media (max-width: 768px) {
    .layer-switcher {
        right: 5px;
        /* 移动端靠右边距减小 */
        top: 10px;
        /* 可选：通常顶部也会相应调小一点点 */
    }
}

.layer-select {
    height: 32px;
    padding: 0 28px 0 10px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    outline: none;
    display: inline-block;
    margin: 0;
    vertical-align: middle;
    background: rgba(5, 11, 10, 0.54);
    color: var(--text-primary);
    font-size: var(--font-size-sm);
    font-family: var(--font-body);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.layer-select:hover,
.layer-select:focus {
    border-color: var(--border-active);
    box-shadow: 0 0 0 3px rgba(71, 215, 198, 0.08);
}

.layer-select option {
    background: var(--deep-2);
    color: var(--text-primary);
}

.layer-label {
    color: var(--text-secondary);
    font-size: var(--font-size-xs);
    font-weight: 600;
    display: inline-block;
    margin: 0;
    vertical-align: middle;
    white-space: nowrap;
}

.custom-url-wrapper {
    flex-basis: 100%;
    margin-top: 2px;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
}

.custom-url-input {
    flex: 1;
    min-width: 220px;
    height: 30px;
    padding: 0 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    font-size: var(--font-size-xs);
    background: rgba(5, 11, 10, 0.54);
    color: var(--text-primary);
    outline: none;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.custom-url-input:focus {
    border-color: var(--border-active);
    box-shadow: 0 0 0 3px rgba(71, 215, 198, 0.08);
}

.custom-url-input::placeholder {
    color: var(--text-muted);
}

.custom-url-btn {
    height: 30px;
    padding: 0 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-active);
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    cursor: pointer;
    font-size: var(--font-size-xs);
    font-weight: 700;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.custom-url-btn:hover {
    background: rgba(71, 215, 198, 0.22);
    box-shadow: var(--neon-cyan-glow);
}

.detected-format-hint {
    margin-top: 0;
    padding: 5px 8px;
    background: var(--neon-green-dim);
    border: 1px solid rgba(139, 209, 124, 0.24);
    border-radius: var(--radius-sm);
    color: var(--neon-green);
    font-size: var(--font-size-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.layer-manage-btn {
    width: 32px;
    height: 32px;
    background: rgba(71, 215, 198, 0.08);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    margin-left: 0;
    vertical-align: middle;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.layer-manage-btn:hover {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: rgba(71, 215, 198, 0.16);
}

.graticule-btn {
    height: 32px;
    background: rgba(71, 215, 198, 0.08);
    border: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    cursor: pointer;
    padding: 0 10px;
    margin-left: 0;
    font-size: var(--font-size-xs);
    vertical-align: middle;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.graticule-btn:hover {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: rgba(71, 215, 198, 0.16);
}

.graticule-btn.active {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border-color: var(--border-glow);
    font-weight: 700;
    box-shadow: var(--neon-cyan-glow);
}

.basemap-reset-btn {
    background: rgba(254, 226, 226, 0.2);
    border: 1px solid rgba(254, 202, 202, 0.55);
    color: #fee2e2;
    border-radius: var(--radius-sm);
    cursor: pointer;
    padding: 3px 8px;
    margin-left: 0;
    font-size: var(--font-size-xs);
    vertical-align: middle;
}

.basemap-reset-btn:hover {
    background: rgba(254, 226, 226, 0.34);
}

.layer-manager-panel {
    position: fixed;
    width: 200px;
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-elevated);
    padding: 0;
    max-height: 300px;
    overflow-y: auto;
    z-index: 2000;
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
}

.panel-header {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 9px 10px;
    background: rgba(71, 215, 198, 0.08);
    border-bottom: 1px solid var(--border-subtle);
    border-radius: var(--radius-md) var(--radius-md) 0 0;
    font-size: var(--font-size-sm);
    font-weight: bold;
    color: var(--text-primary);
}

.close-panel-btn {
    cursor: pointer;
    font-size: 16px;
    color: var(--text-muted);
    line-height: 1;
}

.close-panel-btn:hover {
    color: var(--accent-rose);
}

.layer-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px;
}

.layer-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px;
    background: var(--surface-0);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    cursor: move;
    font-size: var(--font-size-sm);
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    color: var(--text-secondary);
    transition: all var(--duration-fast) var(--ease-spatial);
}

.layer-item:hover {
    background: var(--surface-hover);
    color: var(--text-primary);
    border-color: var(--border-active);
}

.layer-item.dragging {
    opacity: 0.5;
    background: var(--neon-cyan-dim);
}

.drag-handle {
    cursor: grab;
    color: var(--text-muted);
    font-weight: bold;
    padding-right: 4px;
}

.drag-handle.mobile-hint {
    cursor: pointer;
    color: var(--neon-cyan);
    font-weight: bold;
    padding-right: 4px;
    font-size: 16px;
}

.layer-name {
    flex: 1;
}

.layer-context-menu {
    position: fixed;
    min-width: 152px;
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-elevated);
    padding: 4px;
    z-index: 2100;
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
}

.context-menu-item {
    width: 100%;
    border: none;
    background: transparent;
    text-align: left;
    font-size: 12px;
    color: var(--text-secondary);
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.context-menu-item:hover {
    background: var(--surface-hover);
    color: var(--neon-cyan);
}

.context-has-submenu {
    position: relative;
}

.context-opacity-control {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    background: rgba(5, 11, 10, 0.34);
}

.opacity-label {
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
    flex-shrink: 0;
}

.opacity-slider {
    flex: 1;
    min-width: 80px;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: rgba(71, 215, 198, 0.18);
    border-radius: 2px;
    outline: none;
    cursor: pointer;
}

.opacity-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--neon-cyan);
    cursor: pointer;
    border: 2px solid var(--deep-1);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.opacity-slider::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--neon-cyan);
    cursor: pointer;
    border: 2px solid var(--deep-1);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

.opacity-value {
    font-size: 11px;
    color: var(--text-primary);
    min-width: 30px;
    text-align: right;
    font-weight: 600;
    flex-shrink: 0;
}

.context-submenu {
    position: absolute;
    min-width: 136px;
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-elevated);
    padding: 4px;
    z-index: 2110;
}

.submenu-arrow {
    color: var(--text-muted);
    font-size: 10px;
}

@media (max-width: 768px) {
    .layer-switcher {
        top: 5px;
        right: 3px;
    }
}
</style>
