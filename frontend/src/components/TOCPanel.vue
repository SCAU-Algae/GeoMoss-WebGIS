<template>
    <div class="toolbox-panel">
        <input ref="fileInputRef" type="file" multiple class="hidden-input" accept=".geojson,.json,.kml,.kmz,.zip,.shp,.dbf,.shx,.prj,.cpg,.tif,.tiff" @change="handleFileUpload" />
        <input ref="folderInputRef" type="file" multiple webkitdirectory directory class="hidden-input" @change="handleDirectoryUpload" />

        <div class="header">
            <div>
                <div class="title">工具箱</div>
                <div class="subtitle">图层组织、绘制、样式和数据导入</div>
            </div>
            <button class="ghost-btn" @click="emit('close')">关闭</button>
        </div>

        <div class="workflow-strip">
            <button class="workflow-step" :class="{ active: activeTab === 'layers' }" @click="activeTab = 'layers'">
                <span class="step-index">1</span>
                <span>管理</span>
            </button>
            <button class="workflow-step" :class="{ active: activeTab === 'draw' }" @click="activeTab = 'draw'">
                <span class="step-index">2</span>
                <span>采集</span>
            </button>
            <button class="workflow-step" :class="{ active: activeTab === 'style' }" @click="activeTab = 'style'">
                <span class="step-index">3</span>
                <span>表达</span>
            </button>
            <button class="workflow-step" :class="{ active: activeTab === 'upload' }" @click="activeTab = 'upload'">
                <span class="step-index">4</span>
                <span>导入</span>
            </button>
        </div>

        <div class="tabs">
            <button class="tab" :class="{ active: activeTab === 'layers' }" @click="activeTab = 'layers'">图层</button>
            <button class="tab" :class="{ active: activeTab === 'draw' }" @click="activeTab = 'draw'">绘制</button>
            <button class="tab" :class="{ active: activeTab === 'style' }" @click="activeTab = 'style'">样式</button>
            <button class="tab" :class="{ active: activeTab === 'upload' }" @click="activeTab = 'upload'">导入</button>
        </div>

        <div v-if="activeTab === 'layers'" class="panel-scroll">
            <LayerPanel
                :draw-layers="drawLayers"
                :route-layers="routeLayers"
                :search-layers="searchLayers"
                :upload-layers="uploadLayers"
                :selected-layer-ids="multiSelectedLayerIds"
                :has-draw-card="hasDrawCard"
                :overview="overview"
                :is-raster-layer="isRasterLayer"
                @action="handleLayerTreeAction"
            />

            <AmapAoiInjectDialog
                :visible="manualAoiDialogVisible"
                :poi-id="manualAoiPoiId"
                :json-text="manualAoiJsonText"
                :detail-url="manualAoiDetailUrl"
                :source-layer-name="manualAoiSourceLayerName"
                :error-message="manualAoiError"
                @update:poi-id="manualAoiPoiId = $event"
                @update:json-text="manualAoiJsonText = $event"
                @open-detail="openManualAoiDetailLink"
                @submit="drawAmapAoiFromManualJson"
                @close="closeManualAoiDialog"
            />
        </div>

<div v-else-if="activeTab === 'draw'" class="eco-panel-scroll">
    <!-- 1. 核心绘图工具区 -->
    <div class="eco-section">
        <div class="section-header">
            <span class="section-dot"></span>
            <span class="section-title">基础绘图</span>
        </div>
        <div class="eco-draw-grid">
            <button
                v-for="tool in drawTools"
                :key="tool.value"
                class="eco-tool-pill"
                :class="{ active: selectedDrawTool === tool.value }"
                @click="activateDrawTool(tool.value)"
            >
                {{ tool.label }}
            </button>
        </div>
        <div class="eco-actions-flex">
            <button class="eco-btn-op primary" @click="emit('interaction', 'ZoomToGraphics')">全幅显示</button>
            <button class="eco-btn-op warning" @click="emit('interaction', 'Clear')">清空画布</button>
        </div>
    </div>

    <!-- 2. 精确坐标定位区 (合并了经纬度和 P 参数) -->
    <div class="eco-section alt-bg">
        <div class="section-header">
            <span class="section-dot"></span>
            <span class="section-title">坐标定位</span>
        </div>
        
        <!-- 经纬度输入 -->
        <div class="eco-input-group">
            <div class="input-row">
                <input v-model.trim="coordInputLon" class="eco-input" placeholder="经度" />
                <input v-model.trim="coordInputLat" class="eco-input" placeholder="纬度" />
            </div>
            <div class="input-row compact">
                <select v-model="coordInputCRS" class="eco-select">
                    <option value="wgs84">WGS-84</option>
                    <option value="gcj02">GCJ-02</option>
                </select>
                <button class="eco-btn-sm" @click="drawPointByCoordinates">绘制</button>
            </div>
        </div>

        <div class="eco-divider"><span>OR</span></div>

        <!-- P 参数输入 -->
        <div class="eco-input-group">
            <div class="input-row">
                <input v-model.trim="coordInputP" class="eco-input" placeholder="请输入 P 参数" />
                <button class="eco-btn-sm" :disabled="isDecodePBusy" @click="drawPointByPositionCode">
                    {{ isDecodePBusy ? '...' : '解析' }}
                </button>
            </div>
        </div>
        <div v-if="coordInputError || coordInputPError" class="eco-error-msg">
            {{ coordInputError || coordInputPError }}
        </div>
    </div>

    <!-- 3. 地理编码工具 -->
    <div class="eco-section">
        <div class="section-header">
            <span class="section-dot"></span>
            <span class="section-title">地理编码</span>
        </div>
        <div class="eco-input-group">
            <input v-model.trim="geocodeAddressInput" class="eco-input full" placeholder="输入地址..." />
            <div class="input-row compact mt-8">
                <input v-model.trim="geocodeCityInput" class="eco-input" placeholder="限定城市(可选)" />
                <button class="eco-btn-sm" :disabled="isGeocodeBusy" @click="drawPointByGeocodeAddress">编码</button>
            </div>
        </div>
        
        <button class="eco-btn-reverse mt-12" @click="startReverseGeocodePick">
            <span class="icon">📍</span> 地图点选逆编码
        </button>
    </div>

    <!-- 4. 底部操作提示 (改用气泡感设计) -->
    <div class="eco-hint-box">
        <div class="hint-item"><span>左键</span> 选中要素</div>
        <div class="hint-item"><span>右键</span> 独立显示</div>
        <div class="hint-item"><span>地图右键</span> 属性查询</div>
    </div>
</div>

        <div v-else-if="activeTab === 'upload'" class="panel-scroll upload-tab-scroll">
            <div class="upload-zone-wrap">
                <div
                    class="upload-entry"
                    :class="{ dragging: isUploadDragging }"
                    @dragenter.prevent="handleUploadDragEnter"
                    @dragover.prevent="handleUploadDragOver"
                    @dragleave.prevent="handleUploadDragLeave"
                    @drop.prevent="handleUploadDrop"
                >
                    <div class="card-top">
                        <div class="card-title upload-title">
                            <span class="upload-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M12 16V5"></path><path d="m8 9 4-4 4 4"></path>
                                    <path d="M20 16.5a3.5 3.5 0 0 1-3.5 3.5h-9A3.5 3.5 0 0 1 4 16.5"></path>
                                </svg>
                            </span>
                            上传 2D 图层
                        </div>
                        <div class="upload-btns">
                            <button class="small-btn" @click="triggerFileUpload">上传文件</button>
                            <button class="small-btn ghost" @click="triggerFolderUpload">上传文件夹</button>
                        </div>
                    </div>
                    <div class="upload-tip">支持 GeoJSON / KML / KMZ / TIF / SHP 等格式</div>
                    <div class="upload-crs-tip">
                        <span>文件大小 ≤ {{ MAX_FILE_SIZE_MB }} MB</span>
                        <span>也可拖拽文件到此处</span>
                    </div>
                    <div v-if="shouldShowUploadProgress" class="upload-progress" :class="`phase-${uploadProgressView.phase}`">
                        <div class="upload-progress-head">
                            <span>{{ uploadProgressView.current }}/{{ uploadProgressView.total || 1 }}</span>
                            <span>{{ uploadProgressLabel }}</span>
                        </div>
                        <div class="upload-progress-bar">
                            <div class="upload-progress-fill" :style="{ width: `${uploadProgressPercent}%` }"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div v-else-if="activeTab === 'style'" class="panel-scroll style-scroll">
            <div class="style-panel">
                <div class="card-title">样式模板</div>
                <div class="template-chip-row">
                    <button class="template-chip" v-for="t in styleTemplates" :key="t.id" @click="applyTemplate(t.id)">
                        <span class="chip-dot" :style="{ backgroundColor: t.color }"></span>
                        <span>{{ t.name }}</span>
                    </button>
                </div>

                <div class="style-divider"></div>

                <div class="card-title">样式编辑</div>
                <div class="field">
                    <label>编辑目标</label>
                    <div class="select-wrap">
                        <select v-model="selectedEditLayerId" class="style-select">
                            <option v-for="layer in editableLayers" :key="layer.id" :value="layer.id">{{ layer.name }}</option>
                        </select>
                    </div>
                </div>
                <div class="field-grid">
                    <div class="field">
                        <label>填充色</label>
                        <input type="color" class="style-color" v-model="styleForm.fillColor" />
                    </div>
                    <div class="field">
                        <label>边框色</label>
                        <input type="color" class="style-color" v-model="styleForm.strokeColor" />
                    </div>
                </div>
                <div class="field-grid">
                    <div class="field">
                        <div class="slider-head">
                            <label>填充透明度</label>
                            <span>{{ styleForm.fillOpacityPct }}%</span>
                        </div>
                        <input class="style-slider" type="range" min="0" max="100" v-model.number="styleForm.fillOpacityPct" />
                    </div>
                    <div class="field">
                        <div class="slider-head">
                            <label>边框宽度</label>
                            <span>{{ styleForm.strokeWidth }}</span>
                        </div>
                        <input class="style-slider" type="range" min="1" max="8" step="0.5" v-model.number="styleForm.strokeWidth" />
                    </div>
                </div>
                <button class="small-btn style-apply-btn" @click="applyStyle">应用样式</button>
            </div>
        </div>

    </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useMessage } from '../composables/useMessage';
import { useGisLoader } from '../composables/useGisLoader';
import { usePositionCodeTool } from '../composables/map';
import {
    applyRecursiveSelection,
    applyRecursiveSelectionChunked,
    pruneSelectedLayerIds,
    handleLayerTreeContextAction
} from '../composables/map/toc';
import { useLayerStore, useAttrStore } from '../stores';
import { useStyleEditor } from '../constants';
import {
    COORDINATE_FORMATS,
    DECIMAL_PLACES,
    formatCoordinate,
    generatePointName,
    processCoordinateInput
} from '../utils/biz';
import {
    apiAddressGeocode,
    apiReverseGeocodeWithFallback
} from '../api';
import { listPublishedThreeDLayers, resolveThreeDTilesUrl } from '../api/threed';
import LayerPanel from './LayerPanel.vue';
import AmapAoiInjectDialog from './AmapAoiInjectDialog.vue';


const props = defineProps({
    userLayers: { type: Array, default: () => [] },
    baseLayers: { type: Array, default: () => [] },
    overview: { type: Object, default: () => ({ drawCount: 0, uploadCount: 0, layers: [] }) },
    uploadProgress: { type: Object, default: () => ({ phase: 'idle' }) },
    latestSearchPoi: { type: Object, default: () => ({}) }
});

const emit = defineEmits([
    'close',
    'upload-data',
    'interaction',
    'layer-selected',
    'toggle-layer-visibility',
    'change-layer-opacity',
    'zoom-layer',
    'view-layer',
    'remove-layer',
    'reorder-user-layers',
    'solo-layer',
    'set-base-layer',
    'toggle-base-layer-visibility',
    'toggle-layer-label-visibility',
    'set-layer-label-field',
    'apply-style-template',
    'update-draw-style',
    'update-layer-style',
    'highlight-attribute-feature',
    'zoom-attribute-feature',
    'draw-point-by-coordinates',
    'draw-amap-aoi-from-json',
    'toggle-layer-crs',
    'export-layer-data'
]);

const fileInputRef = ref(null);
const folderInputRef = ref(null);
const message = useMessage();
const gisLoader = useGisLoader();
const layerStore = useLayerStore();
const attrStore = useAttrStore();
const styleEditor = useStyleEditor();
const activeTab = ref('layers');
const isUploadDragging = ref(false);
const coordInputLon = ref('');
const coordInputLat = ref('');
const coordInputCRS = ref('wgs84');
const coordInputError = ref('');
const coordInputP = ref('');
const coordInputPError = ref('');
const geocodeAddressInput = ref('');
const geocodeCityInput = ref('');
const geocodeToolError = ref('');
const manualAoiPoiId = ref('');
const manualAoiJsonText = ref('');
const manualAoiError = ref('');
const manualAoiDialogVisible = ref(false);
const manualAoiSourceLayerName = ref('');
const multiSelectedLayerIds = ref([]);
let recursiveSelectionToken = 0;
const isDecodePBusy = ref(false);
const isGeocodeBusy = ref(false);
const MB = 1024 * 1024;
const MAX_FILE_SIZE_MB = 200;
const TIANDITU_TK = import.meta.env.VITE_TIANDITU_TK || '';

const {
    decodePositionCodeToPointPayload
} = usePositionCodeTool({
    tiandituTk: TIANDITU_TK,
    reverseGeocode: apiReverseGeocodeWithFallback
});

function buildAmapDetailUrl(rawPoiId) {
    const poiId = normalizeManualAoiPoiId(rawPoiId, { keepRawFallback: true });
    return poiId
        ? `https://www.amap.com/detail/get/detail?id=${encodeURIComponent(poiId)}`
    : 'https://www.amap.com/';
}

const manualAoiDetailUrl = computed(() => {
    return buildAmapDetailUrl(manualAoiPoiId.value);
});

const COORD_STORAGE_KEYS = {
    FORMAT_ID: 'gis_coord_format_id',
    DECIMAL_PLACES: 'gis_coord_decimal_places'
};

function getCurrentFormatConfig() {
    const rawFormatId = String(localStorage.getItem(COORD_STORAGE_KEYS.FORMAT_ID) || 'format_6');
    const rawPlaces = Number(localStorage.getItem(COORD_STORAGE_KEYS.DECIMAL_PLACES) || 6);

    const formatId = COORDINATE_FORMATS[rawFormatId] ? rawFormatId : 'format_6';
    const decimalPlaces = DECIMAL_PLACES[rawPlaces] ? rawPlaces : 6;

    return { formatId, decimalPlaces };
}

const styleTemplates = styleEditor.styleTemplates;

const drawTools = [
    { value: 'AttributeQuery', label: '属性查询' },
    { value: 'Point', label: '点' },
    { value: 'LineString', label: '线' },
    { value: 'Polygon', label: '面' },
    { value: 'MeasureDistance', label: '测距' },
    { value: 'MeasureArea', label: '测面' }
];

const styleForm = styleEditor.styleForm;
const selectedDrawTool = computed(() => layerStore.selectedDrawTool);
const selectedEditLayerId = computed({
    get: () => layerStore.selectedEditLayerId,
    set: (value) => {
        layerStore.selectedEditLayerId = value;
    }
});
const drawLayers = computed(() => layerStore.drawLayers);
const uploadLayers = computed(() => layerStore.uploadLayers);
const routeLayers = computed(() => layerStore.routeLayers);
const searchLayers = computed(() => layerStore.searchLayers);
const hasDrawCard = computed(() => layerStore.hasDrawCard);
const editableLayers = computed(() => layerStore.editableLayers);

const uploadProgressView = computed(() => {
    const raw = props.uploadProgress || {};
    return {
        phase: String(raw.phase || 'idle'),
        total: Math.max(0, Number(raw.total) || 0),
        current: Math.max(0, Number(raw.current) || 0),
        success: Math.max(0, Number(raw.success) || 0),
        failed: Math.max(0, Number(raw.failed) || 0),
        warnings: Math.max(0, Number(raw.warnings) || 0),
        errors: Math.max(0, Number(raw.errors) || 0),
        message: String(raw.message || '')
    };
});

const shouldShowUploadProgress = computed(() => uploadProgressView.value.phase !== 'idle');

const uploadProgressPercent = computed(() => {
    const total = uploadProgressView.value.total;
    const current = uploadProgressView.value.current;
    if (!total) {
        if (uploadProgressView.value.phase === 'done') return 100;
        if (uploadProgressView.value.phase === 'error') return 100;
        return 12;
    }
    return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
});

const uploadProgressLabel = computed(() => {
    const phase = uploadProgressView.value.phase;
    if (phase === 'validating') return '文件校验中';
    if (phase === 'dispatching') return '容器解析中';
    if (phase === 'importing') return '数据导入中';
    if (phase === 'done') return '导入已完成';
    if (phase === 'error') return '导入失败';
    return '等待导入';
});

async function refreshPublishedThreeDLayers() {
    try {
        const payload = await listPublishedThreeDLayers();
        const list = Array.isArray(payload?.data) ? payload.data : [];
        const normalized = list
            .map((item) => {
                const id = `3d_pub_${String(item?.id || '').trim()}`;
                const tilesetUrl = resolveThreeDTilesUrl(item?.tileset_url || '');
                if (!item?.id || !tilesetUrl) return null;
                return {
                    id,
                    name: String(item?.name || '3D 图层'),
                    visible: false,
                    tilesetUrl,
                    description: String(item?.description || ''),
                    featureCount: Number(item?.feature_count || 0),
                    metadata: item?.metadata || {}
                };
            })
            .filter(Boolean);

        layerStore.syncPublishedThreeDLayers(normalized);
    } catch {
        layerStore.syncPublishedThreeDLayers([]);
    }
}

const userLayerSyncKey = computed(() => {
    const layerItems = (props.userLayers || []).map((layer) => [
        layer?.id,
        layer?.name,
        layer?.type,
        layer?.sourceType,
        layer?.order,
        layer?.visible,
        layer?.featureCount,
        layer?.featureDigest,
        layer?.opacity,
        layer?.autoLabel,
        layer?.labelVisible,
        layer?.category,
        layer?.crs,
        layer?.longitude,
        layer?.latitude,
        layer?.styleConfig?.fillColor,
        layer?.styleConfig?.strokeColor,
        layer?.styleConfig?.fillOpacity,
        layer?.styleConfig?.strokeWidth,
        layer?.standardTocItem?.id,
        layer?.standardTocItem?.parentId,
        layer?.standardTocItem?.visible,
        layer?.standardTocItem?.opacity,
        layer?.standardTocItem?.featureCount
    ].join(':'));

    return layerItems.join('|');
});

const overviewSyncKey = computed(() => {
    const overview = props.overview || {};
    return [
        Number(overview.drawCount || 0),
        Number(overview.uploadCount || 0),
        (overview.layers || []).map((layer) => [
            layer?.id,
            layer?.visible,
            layer?.featureCount,
            layer?.featureDigest
        ].join(':')).join('|')
    ].join('|');
});

// 复制图层经纬度信息到剪贴板
// 应当识别当前用户选择的格式，进行转化后复制
async function copyLayerCoordinates(layer) {
    if (!(Number.isFinite(layer?.longitude) && Number.isFinite(layer?.latitude))) {
        message.warning('当前图层未提供可复制的经纬度信息');
        return;
    }

    const { formatId, decimalPlaces } = getCurrentFormatConfig();
    const lon = Number(layer.longitude);
    const lat = Number(layer.latitude);
    const text = formatCoordinate(lon, lat, formatId, decimalPlaces);

    if (!text) {
        message.warning('坐标格式化失败，无法复制');
        return;
    }

    try {
        if (navigator?.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
        message.success(`已复制坐标：${text}`);
    } catch {
        message.error('复制失败，请稍后重试');
    }
}

function clearCoordinateInput() {
    coordInputLon.value = '';
    coordInputLat.value = '';
    coordInputError.value = '';
}

function clearPositionCodeInput() {
    coordInputP.value = '';
    coordInputPError.value = '';
}

function clearGeocodeInput() {
    geocodeAddressInput.value = '';
    geocodeCityInput.value = '';
    geocodeToolError.value = '';
}

function normalizeManualAoiPoiId(rawValue, options = {}) {
    const keepRawFallback = options?.keepRawFallback !== false;
    const rawText = String(rawValue || '').trim();
    if (!rawText) return '';

    const unwrapped = rawText.replace(/^\{+|\}+$/g, '').replace(/^['"]+|['"]+$/g, '').trim();
    if (!unwrapped) return '';

    if (/^https?:\/\//i.test(unwrapped)) {
        try {
            const url = new URL(unwrapped);
            const idFromUrl = String(url.searchParams.get('id') || url.searchParams.get('poiid') || '').trim();
            if (idFromUrl) return idFromUrl;
        } catch {
            // noop
        }
    }

    const inlineIdMatch = unwrapped.match(/[?&](?:id|poiid)=([^&#\s]+)/i);
    if (inlineIdMatch?.[1]) {
        return String(decodeURIComponent(inlineIdMatch[1])).trim();
    }

    try {
        const parsed = JSON.parse(unwrapped);
        const idFromJson = String(
            parsed?.data?.base?.poiid
            || parsed?.base?.poiid
            || parsed?.data?.base?.id
            || parsed?.pois?.[0]?.id
            || parsed?.id
            || ''
        ).trim();
        if (idFromJson) return idFromJson;
    } catch {
        // noop
    }

    return keepRawFallback ? unwrapped : '';
}

function closeManualAoiDialog() {
    manualAoiDialogVisible.value = false;
    manualAoiJsonText.value = '';
    manualAoiError.value = '';
    manualAoiSourceLayerName.value = '';
}

function openManualAoiDetailLink() {
    manualAoiError.value = '';
    const poiId = normalizeManualAoiPoiId(manualAoiPoiId.value, { keepRawFallback: true });
    if (poiId) {
        manualAoiPoiId.value = poiId;
    }

    const detailUrl = buildAmapDetailUrl(manualAoiPoiId.value);
    if (typeof window !== 'undefined') {
        const popup = window.open(detailUrl, '_blank', 'noopener,noreferrer');
        if (!popup) {
            message.warning('浏览器拦截了新窗口，请允许弹窗后重试');
        }
    }
}

function openManualAoiDialogByPoi(payload = {}, options = {}) {
    const poiId = normalizeManualAoiPoiId(payload?.poiid, { keepRawFallback: false });
    const layerName = String(payload?.layerName || '').trim();

    manualAoiPoiId.value = poiId || '';
    manualAoiJsonText.value = '';
    manualAoiError.value = '';
    manualAoiSourceLayerName.value = layerName;
    manualAoiDialogVisible.value = true;

    if (!poiId && options?.showMissingIdHint) {
        message.info('该 POI 未返回 ID，请在弹窗中手动填写后继续');
    }

    if (options?.autoOpenDetail) {
        openManualAoiDetailLink();
    }

    return true;
}

// 解析用户输入的高德详情 JSON，尝试从中提取 POI ID，并触发绘制事件
function drawAmapAoiFromManualJson() {
    manualAoiError.value = '';
    const jsonText = String(manualAoiJsonText.value || '').trim();
    if (!jsonText) {
        manualAoiError.value = '请先粘贴高德详情 JSON';
        message.warning(manualAoiError.value);
        return;
    }

    const inputPoiId = normalizeManualAoiPoiId(manualAoiPoiId.value);
    const poiId = inputPoiId || normalizeManualAoiPoiId(jsonText, { keepRawFallback: false });
        if (poiId) {
            manualAoiPoiId.value = poiId;
        }

        emit('draw-amap-aoi-from-json', {
            poiid: poiId,
        jsonText,
            sourceLayerName: manualAoiSourceLayerName.value
        });

        // closeManualAoiDialog();
        // 取消自动关闭，允许用户继续修改 JSON 或 POI ID 以调整绘制结果
}

function buildReverseGeocodeProperties(reverseResult) {
    const formattedAddress = String(reverseResult?.formattedAddress || '').trim();
    const province = String(reverseResult?.province || '').trim();
    const city = String(reverseResult?.city || '').trim();
    const district = String(reverseResult?.district || '').trim();
    const township = String(reverseResult?.township || '').trim();
    const provider = String(reverseResult?.provider || '').trim();
    const businessAreaText = Array.isArray(reverseResult?.businessAreas)
        ? reverseResult.businessAreas
            .map((item) => String(item?.name || '').trim())
            .filter(Boolean)
            .join('、')
        : '';

    return {
        逆地理编码地址: formattedAddress || '未解析',
        逆地理编码省: province || '未知',
        逆地理编码市: city || '未知',
        逆地理编码区县: district || '未知',
        逆地理编码乡镇: township || '未知',
        逆地理编码商圈: businessAreaText || '无',
        逆地理编码服务: provider || 'unknown'
    };
}

function drawPointByCoordinates() {
    coordInputError.value = '';
    const crsType = String(coordInputCRS.value || 'wgs84').toLowerCase();
    const result = processCoordinateInput(coordInputLon.value, coordInputLat.value, crsType);

    if (!result.valid) {
        coordInputError.value = result.message;
        message.warning(result.message);
        return;
    }

    emit('draw-point-by-coordinates', {
        lng: result.lng,
        lat: result.lat,
        crsType,
        displayName: generatePointName(result.lng, result.lat, crsType)
    });

    clearCoordinateInput();
}

async function drawPointByPositionCode() {
    coordInputPError.value = '';
    const code = String(coordInputP.value || '').trim();

    isDecodePBusy.value = true;
    try {
        const decodeResult = await decodePositionCodeToPointPayload(code);
        if (!decodeResult?.ok) {
            coordInputPError.value = String(decodeResult?.error || 'p 参数解码失败，请检查编码内容');
            message.warning(coordInputPError.value);
            return;
        }

        emit('draw-point-by-coordinates', {
            ...decodeResult.payload
        });

        message.success(`已按 p 参数绘制点位：${decodeResult.layerName}`);
        clearPositionCodeInput();
    } finally {
        isDecodePBusy.value = false;
    }
}

async function drawPointByGeocodeAddress() {
    geocodeToolError.value = '';

    const inputAddress = String(geocodeAddressInput.value || '').trim();
    const inputCity = String(geocodeCityInput.value || '').trim();
    if (!inputAddress) {
        geocodeToolError.value = '请输入待编码的地址信息';
        message.warning(geocodeToolError.value);
        return;
    }

    isGeocodeBusy.value = true;
    try {
        const geocodeResponse = await apiAddressGeocode(inputAddress, inputCity, { silent: true });
        const geocodeResult = geocodeResponse?.data || null;
        if (!geocodeResult || !Number.isFinite(geocodeResult.lng) || !Number.isFinite(geocodeResult.lat)) {
            throw new Error('地理编码未返回有效坐标');
        }
        let reverseResult = null;
        try {
            const reverseResponse = await apiReverseGeocodeWithFallback(geocodeResult.lng, geocodeResult.lat, {
                tiandituTk: TIANDITU_TK,
                silent: true
            });
            reverseResult = reverseResponse?.data || null;
        } catch {
            reverseResult = null;
        }

        emit('draw-point-by-coordinates', {
            lng: geocodeResult.lng,
            lat: geocodeResult.lat,
            crsType: 'wgs84',
            displayName: inputAddress,
            label: inputAddress,
            layerName: inputAddress,
            properties: {
                来源: '地理编码',
                输入地址: inputAddress,
                城市限定: inputCity || '无',
                地理编码地址: String(geocodeResult?.formattedAddress || '').trim() || inputAddress,
                地理编码级别: String(geocodeResult?.level || '').trim() || 'unknown',
                地理编码ADCODE: String(geocodeResult?.adcode || '').trim() || 'unknown',
                ...buildReverseGeocodeProperties(reverseResult)
            }
        });

        message.success(`地理编码成功：${inputAddress}`);
    } catch (error) {
        const detail = error instanceof Error ? error.message : '地理编码失败';
        geocodeToolError.value = detail;
        message.error(`地理编码失败：${detail}`);
    } finally {
        isGeocodeBusy.value = false;
    }
}

function startReverseGeocodePick() {
    geocodeToolError.value = '';
    emit('interaction', 'ReverseGeocodePick');
}

function isRasterLayer(layer) {
    return layerStore.isRasterLayer(layer);
}

const availableLayerIds = computed(() => (
    (props.userLayers || [])
        .map((layer) => String(layer?.id || '').trim())
        .filter(Boolean)
));

const layerActionMap = computed(() => {
    const map = new Map();

    const walk = (nodes = []) => {
        (nodes || []).forEach((node) => {
            if (!node) return;

            if (node.type === 'layer') {
                const nodeId = String(node.id || '').trim();
                if (nodeId) {
                    map.set(nodeId, node.actions || {});
                }
            }

            if (Array.isArray(node.children) && node.children.length > 0) {
                walk(node.children);
            }
        });
    };

    walk(layerStore.layerTree || []);
    return map;
});

function resolveLayerActionsById(layerId) {
    const id = String(layerId || '').trim();
    if (!id) return null;
    return layerActionMap.value.get(id) || null;
}

function selectableLayerIds() {
    const ids = new Set(availableLayerIds.value);
    (layerStore.threeDLayers || []).forEach((layer) => {
        if (layer?.disabled) return;
        const id = String(layer?.id || '').trim();
        if (id) ids.add(id);
    });
    return Array.from(ids);
}

function pruneMultiSelectedLayerIds() {
    multiSelectedLayerIds.value = pruneSelectedLayerIds(
        multiSelectedLayerIds.value,
        selectableLayerIds()
    );
}

function setNodeRecursiveSelection(nodeId, checked) {
    multiSelectedLayerIds.value = applyRecursiveSelection({
        selectedLayerIds: multiSelectedLayerIds.value,
        treeNodes: layerStore.layerTree || [],
        targetNodeId: nodeId,
        checked,
        availableLayerIds: selectableLayerIds()
    });
}

function addMultiSelectedLayer(layerId) {
    setNodeRecursiveSelection(layerId, true);
}

function removeMultiSelectedLayer(layerId) {
    setNodeRecursiveSelection(layerId, false);
}

function setFolderRecursiveSelection(nodeId, checked) {
    const currentToken = ++recursiveSelectionToken;
    applyRecursiveSelectionChunked({
        selectedLayerIds: multiSelectedLayerIds.value,
        treeNodes: layerStore.layerTree || [],
        targetNodeId: nodeId,
        checked,
        availableLayerIds: selectableLayerIds(),
        chunkSize: 180,
        shouldCancel: () => currentToken !== recursiveSelectionToken
    }).then((nextSelection) => {
        if (currentToken !== recursiveSelectionToken) return;
        multiSelectedLayerIds.value = nextSelection;
    });
}

function clearMultiSelectedLayers() {
    multiSelectedLayerIds.value = [];
}

watch(
    () => userLayerSyncKey.value,
    () => {
        layerStore.syncLayers(props.userLayers || [], props.overview || {});
        attrStore.syncLayers(props.userLayers || []);
        pruneMultiSelectedLayerIds();
    },
    { immediate: true }
);

watch(
    () => overviewSyncKey.value,
    () => {
        layerStore.syncLayers(props.userLayers || [], props.overview || {});
    },
    { immediate: true }
);

watch(
    () => [
        Number(props.latestSearchPoi?._syncAt || 0),
        String(props.latestSearchPoi?.poiid || props.latestSearchPoi?.id || '').trim(),
        String(props.latestSearchPoi?.service || '').trim().toLowerCase(),
        String(props.latestSearchPoi?.name || '').trim()
    ],
    ([syncAt, nextPoiId, service, poiName]) => {
        if (!syncAt) return;
        if (service && service !== 'amap') return;

        openManualAoiDialogByPoi({
            poiid: nextPoiId,
            layerName: poiName
        }, {
            showMissingIdHint: true
        });
    },
    { immediate: true }
);

onMounted(() => {
    refreshPublishedThreeDLayers();
});

layerStore.bindHandlers({
    onReorder: (payload) => emit('reorder-user-layers', payload),
    onHighlightFeature: (payload) => emit('highlight-attribute-feature', payload),
    onZoomFeature: (payload) => emit('zoom-attribute-feature', payload),
    onViewFeature: (payload) => emit('zoom-attribute-feature', payload)
});

function triggerFileUpload() {
    fileInputRef.value?.click();
}

function triggerFolderUpload() {
    folderInputRef.value?.click();
}

function openAttributeTable(layerId) {
    const targetLayer = (props.userLayers || []).find((item) => item.id === layerId);
    attrStore.openTable(layerId, targetLayer?.name || '未命名图层');
    activeTab.value = 'layers';
}

function handleFileUpload(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    // Check file sizes
    const oversized = files.filter(file => (file.size / MB) > MAX_FILE_SIZE_MB);
    if (oversized.length) {
        message.error(`选中 ${oversized.length} 个文件超过 ${MAX_FILE_SIZE_MB} MB 限制：${oversized.map(f => f.name).join(', ')}`);
        event.target.value = '';
        return;
    }

    emit('upload-data', gisLoader.createUploadPayloadsFromFiles(files));

    event.target.value = '';
}

function handleDirectoryUpload(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;

    const oversized = files.filter(file => (file.size / MB) > MAX_FILE_SIZE_MB);
    if (oversized.length) {
        message.warning(`文件夹中有 ${oversized.length} 个文件超过 ${MAX_FILE_SIZE_MB} MB，将在导入阶段按规则处理。`, { duration: 5200 });
    }

    emit('upload-data', gisLoader.createUploadPayloadFromFolder(files));

    event.target.value = '';
}

function handleUploadDragEnter() {
    isUploadDragging.value = true;
}

function handleUploadDragOver() {
    isUploadDragging.value = true;
}

function handleUploadDragLeave(event) {
    if (event.currentTarget === event.target) {
        isUploadDragging.value = false;
    }
}

function handleUploadDrop(event) {
    isUploadDragging.value = false;
    const items = Array.from(event.dataTransfer?.items || []);

    const entryItems = items
        .map(item => (typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null))
        .filter(Boolean);

    if (entryItems.length) {
        emit('upload-data', gisLoader.createUploadPayloadFromEntries(entryItems));
        return;
    }

    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.length) return;
    emit('upload-data', gisLoader.createUploadPayloadsFromFiles(files));
}

function onDragStart(layerId) {
    layerStore.onDragStart(layerId);
}

function onDrop(targetLayerId) {
    layerStore.onDrop(targetLayerId);
}

function handleLayerTreeAction(evt) {
    const type = evt?.type;
    if (!type) return;

    if (type === 'open-label-field-picker') {
        const fields = evt?.payload?.fields || evt?.fields || [];
        if (!fields.length) { message.info('该图层无可选属性字段'); return; }
        const currentField = evt?.payload?.currentField || evt?.currentField || '';
        const chosen = prompt(
            `选择标注字段（当前: ${currentField || '自动'}）\n可用字段: ${fields.join(', ')}`,
            currentField
        );
        if (chosen !== null) {
            emit('set-layer-label-field', { layerId: evt?.payload?.layerId || evt?.layerId, field: chosen.trim() });
        }
        return;
    }

    const contextHandled = handleLayerTreeContextAction({
        evt,
        selectedLayerIds: multiSelectedLayerIds.value,
        availableLayerIds: availableLayerIds.value,
        addMultiSelectedLayer,
        removeMultiSelectedLayer,
        clearMultiSelectedLayers,
        setFolderRecursiveSelection,
        emit,
        message,
        openAttributeTable,
        setStyleTarget,
        copyLayerCoordinates,
        openManualAoiDialogByPoi,
        onDragStart,
        onDrop,
        resolveLayerActionsById
    });
    if (contextHandled) return;

    if (type === 'layer-selected') {
        // 图层行被选中，可用于高亮地图上的图层等操作
        emit('layer-selected', evt.layerId);
        return;
    }
    if (type === 'toggle-layer-visibility') {
        emit('toggle-layer-visibility', { layerId: evt.layerId, visible: !!evt.visible });
        return;
    }
}

function setStyleTarget(layerId) {
    layerStore.setStyleTarget(layerId);
    activeTab.value = 'style';
}

function activateDrawTool(tool) {
    layerStore.setDrawTool(tool);
    emit('interaction', tool);
}

function applyTemplate(templateId) {
    // 1. 获取当前选中的目标 ID
    const targetId = selectedEditLayerId.value;
    if (!targetId) return; // 如果没有选中任何图层，直接返回

    // 2. 更新本地 styleForm (让界面底部的颜色选择器实时同步变色)
    const targetTemplate = styleTemplates.find(t => t.id === templateId);
    if (targetTemplate) {
        styleForm.value.fillColor = targetTemplate.color;
        // 建议：描边色通常可以设为和填充色一致，或者加深一点
        styleForm.value.strokeColor = targetTemplate.color; 
    }

    // 3. 执行原有的业务 emit (保持与父组件/地图引擎的通信)
    if (targetId === 'draw') {
        emit('apply-style-template', { target: 'draw', templateId });
    } else {
        emit('apply-style-template', { target: 'layer', layerId: targetId, templateId });
    }

    // 4. 【核心修复】关键：立即调用 applyStyle() 触发地图渲染
    // 这样用户点击模板按钮后，地图会立刻变色，不再需要二次点击“应用样式”
    applyStyle();
}

function applyStyle() {
    const payload = styleEditor.buildStylePayload();
    if (selectedEditLayerId.value === 'draw') {
        emit('update-draw-style', payload);
        return;
    }
    if (selectedEditLayerId.value) {
        emit('update-layer-style', { layerId: selectedEditLayerId.value, styleConfig: payload });
    }
}

</script>

<style scoped>
.eco-panel-scroll {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    overflow-y: auto;
}

.eco-section,
.style-panel,
.card,
.upload-entry,
.upload-card {
    background: var(--surface-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-button);
}

.eco-section,
.style-panel {
    padding: 12px;
}

.eco-section.alt-bg {
    background: rgba(17, 28, 25, 0.78);
}

.section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
}

.section-dot {
    width: 4px;
    height: 14px;
    background: var(--neon-cyan);
    border-radius: 4px;
}

.section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
}

.eco-draw-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
}

.eco-tool-pill {
    padding: 8px 4px;
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    border-radius: var(--radius-md);
    font-size: 12px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.eco-tool-pill.active {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border-color: var(--border-active);
    box-shadow: var(--neon-cyan-glow);
}

.eco-input-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.input-row {
    display: flex;
    gap: 8px;
}

.input-row.compact .eco-input { width: 60%; }
.input-row.compact .eco-btn-sm { flex: 1; }

.eco-input {
    background: var(--surface-card-strong);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    font-size: 12px;
    outline: none;
    transition: border-color var(--duration-fast) var(--ease-spatial), box-shadow var(--duration-fast) var(--ease-spatial);
    width: 100%;
    color: var(--text-primary);
}

.eco-input:focus {
    border-color: var(--border-active);
    box-shadow: 0 0 0 3px var(--neon-cyan-dim);
}

.eco-select {
    background: var(--surface-card-strong);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-size: 12px;
    padding: 0 8px;
    color: var(--text-primary);
}

.eco-btn-sm {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border: 1px solid var(--border-active);
    border-radius: var(--radius-md);
    padding: 6px 16px;
    font-size: 12px;
    cursor: pointer;
}

.eco-btn-reverse {
    width: 100%;
    padding: 10px;
    background: var(--neon-green-dim);
    border: 1px dashed rgba(139, 209, 124, 0.35);
    border-radius: var(--radius-md);
    color: var(--neon-green);
    font-size: 13px;
    cursor: pointer;
    font-weight: 500;
}
.eco-actions-flex {
    display: flex;
    gap: 12px;
    margin-top: 12px;
}

.eco-btn-op {
    flex: 1;
    padding: 10px 0;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-spatial);
    display: flex;
    align-items: center;
    justify-content: center;
}

.eco-btn-op.primary {
    background: var(--neon-cyan-dim);
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.eco-btn-op.primary:hover {
    background: rgba(71, 215, 198, 0.22);
    transform: translateY(-1px);
    box-shadow: var(--neon-cyan-glow);
}

.eco-btn-op.warning {
    background: var(--accent-amber-dim);
    border-color: rgba(240, 179, 90, 0.34);
    color: var(--accent-amber);
}

.eco-btn-op.warning:hover {
    background: rgba(240, 179, 90, 0.24);
    transform: translateY(-1px);
    box-shadow: 0 6px 15px rgba(240, 179, 90, 0.18);
}

.eco-btn-op:active {
    transform: translateY(1px);
    box-shadow: 0 2px 5px rgba(0, 0, 0, 0.15);
}

.eco-divider {
    text-align: center;
    margin: 12px 0;
    position: relative;
}
.eco-divider::before {
    content: "";
    position: absolute;
    top: 50%; left: 0; right: 0;
    height: 1px; background: var(--border-subtle);
}
.eco-divider span {
    position: relative;
    background: var(--surface-card);
    padding: 0 10px;
    font-size: 10px;
    color: var(--text-muted);
}

.eco-hint-box {
    background: var(--surface-card);
    border-radius: var(--radius-md);
    padding: 12px;
    border: 1px solid var(--border-subtle);
}

.hint-item {
    font-size: 11px;
    color: var(--text-muted);
    line-height: 20px;
}

.hint-item span {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    padding: 0 4px;
    border-radius: 4px;
    margin-right: 4px;
    font-weight: bold;
}

.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }

.toolbox-panel {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px;
    background: var(--glass-bg-heavy);
    color: var(--text-primary);
}

.hidden-input { display: none; }

.header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-subtle);
    padding-bottom: 8px;
}

.title { font-size: 18px; font-weight: 700; color: var(--text-primary); letter-spacing: 0; }
.subtitle { font-size: 12px; color: var(--text-muted); }

.workflow-strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 6px;
}

.workflow-step {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-width: 0;
    border: 1px solid var(--border-subtle);
    background: var(--surface-0);
    color: var(--text-muted);
    border-radius: var(--radius-md);
    padding: 7px 4px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.workflow-step.active {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
}

.step-index {
    display: inline-flex;
    width: 16px;
    height: 16px;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-full);
    background: rgba(255, 255, 255, 0.06);
    font-family: var(--font-mono);
    font-size: 10px;
}

.tabs {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    padding: 4px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: rgba(4, 8, 8, 0.2);
    backdrop-filter: blur(10px);
}

.tab {
    border: 1px solid transparent;
    background: transparent;
    border-radius: var(--radius-sm);
    padding: 8px 4px;
    font-size: 12px;
    cursor: pointer;
    color: var(--text-muted);
    transition: transform var(--duration-fast) var(--ease-spatial), background-color var(--duration-fast) var(--ease-spatial), border-color var(--duration-fast) var(--ease-spatial);
}

.tab:hover {
    transform: translateY(-1px);
    background: var(--surface-hover);
    border-color: var(--border-subtle);
}

.tab.active {
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    font-weight: 600;
    box-shadow: var(--neon-cyan-glow);
}

.panel-scroll {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.card {
    padding: 11px;
    backdrop-filter: blur(8px);
}

.card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.upload-zone-wrap {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.card-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 6px;
}

.upload-tip {
    margin-bottom: 8px;
    font-size: 11px;
    color: var(--text-muted);
    padding: 0 2px;
}

.upload-crs-tip {
    margin-bottom: 6px;
    font-size: 11px;
    color: var(--accent-blue);
    padding: 6px 8px;
    background: var(--accent-blue-dim);
    border-radius: var(--radius-sm);
    border-left: 3px solid rgba(106, 169, 255, 0.5);
}

.upload-crs-tip span {
    display: block;
    line-height: 1.4;
}


.upload-entry {
    padding: 10px;
    border-style: dashed;
    transition: border-color var(--duration-fast) var(--ease-spatial), background-color var(--duration-fast) var(--ease-spatial), box-shadow var(--duration-fast) var(--ease-spatial);
}

.upload-entry.dragging {
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
    box-shadow: 0 0 0 3px var(--neon-cyan-dim);
}

.upload-title {
    display: flex;
    align-items: center;
    gap: 6px;
}

.upload-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 6px;
    color: var(--neon-cyan);
    background: var(--neon-cyan-dim);
}

.upload-progress {
    border: 1px solid var(--border-subtle);
    background: var(--surface-card-strong);
    border-radius: var(--radius-md);
    padding: 7px;
}

.upload-progress.phase-error {
    border-color: rgba(239, 127, 138, 0.34);
    background: var(--accent-rose-dim);
}

.upload-progress.phase-done {
    border-color: rgba(139, 209, 124, 0.32);
    background: var(--neon-green-dim);
}

.upload-progress-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 5px;
}

.upload-progress-bar {
    height: 8px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    overflow: hidden;
}

.upload-progress-fill {
    height: 100%;
    width: 0;
    background: linear-gradient(90deg, var(--neon-cyan), var(--neon-green));
    transition: width var(--duration-normal) var(--ease-panel);
}

.upload-progress.phase-error .upload-progress-fill {
    background: linear-gradient(90deg, var(--accent-rose), #c7525c);
}

.upload-progress-meta {
    margin-top: 5px;
    font-size: 10px;
    color: var(--text-muted);
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.upload-progress-message {
    margin-top: 3px;
    font-size: 10px;
    color: var(--text-muted);
    word-break: break-word;
}

.row-label {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
}

.layer-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.layer-item {
    border-bottom: 1px solid var(--border-subtle);
    padding: 8px 4px;
    background: transparent;
    cursor: pointer;
    transition: background-color var(--duration-fast) var(--ease-spatial);
}

.layer-item:hover {
    background: var(--surface-hover);
}

.layer-main {
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 8px;
}

.layer-title-wrap {
    min-width: 0;
    flex: 1;
}

.name {
    display: inline-block;
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.feature-badge {
    flex-shrink: 0;
    font-size: 10px;
    color: var(--text-muted);
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    border-radius: 999px;
    padding: 1px 7px;
    line-height: 1.5;
}

.layer-actions {
    margin-left: auto;
}

.icon-row {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

.action-icon-btn {
    position: relative;
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: var(--radius-sm);
    width: 24px;
    height: 24px;
    padding: 0;
    font-size: 12px;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}

.action-icon-btn:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.action-icon-btn.danger {
    border-color: rgba(239, 127, 138, 0.28);
    background: var(--accent-rose-dim);
    color: var(--accent-rose);
}

.action-icon-btn.danger:hover {
    border-color: rgba(239, 127, 138, 0.46);
    background: rgba(239, 127, 138, 0.2);
    color: var(--accent-rose);
}

.action-icon-btn[data-tip]:hover::after {
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    font-size: 10px;
    color: var(--text-primary);
    background: var(--glass-bg-heavy);
    padding: 3px 6px;
    border-radius: 6px;
    white-space: nowrap;
    pointer-events: none;
    z-index: 3;
}

.draw-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
}

.actions-row{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 20px;
}

.coord-input-panel {
    margin-top: 12px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 10px;
    background: var(--surface-card);
}

.coord-input-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
}

.coord-input-field {
    width: 100%;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 8px 10px;
    font-size: 12px;
    color: var(--text-primary);
    background: var(--surface-card-strong);
    box-sizing: border-box;
}

.coord-input-field:focus {
    outline: none;
    border-color: var(--border-active);
    box-shadow: 0 0 0 2px var(--neon-cyan-dim);
}

.coord-divider {
    height: 1px;
    margin: 10px 0;
    background: var(--border-subtle);
}

.coord-crs-row {
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.coord-crs-label {
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
}

.coord-crs-select {
    flex: 1;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 6px 8px;
    background: var(--surface-card-strong);
    color: var(--text-primary);
}

.coord-input-actions {
    margin-top: 10px;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.coord-input-actions.single-action {
    grid-template-columns: 1fr;
}

.geocode-tool-panel {
    margin-top: 10px;
}

.geocode-subtitle {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 6px;
}

.geocode-tip {
    margin-top: 8px;
    font-size: 11px;
    line-height: 1.45;
    color: var(--text-muted);
}

.coord-input-error {
    margin-top: 8px;
    color: var(--accent-rose);
    font-size: 12px;
    line-height: 1.4;
    word-break: break-word;
}

.template-row,
.field-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
}

.field select,
.field input[type='range'],
.field input[type='color'] {
    width: 100%;
}

.upload-btns {
    display: inline-flex;
    gap: 6px;
}

.ghost-btn,
.small-btn,
.template {
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: var(--radius-md);
    padding: 6px 8px;
    font-size: 12px;
    cursor: pointer;
}

.draw-tool-btn {
    min-height: 34px;
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: var(--radius-md);
    padding: 6px 8px;
    font-size: 12px;
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.draw-tool-btn:hover {
    background: var(--surface-hover);
}

.draw-tool-btn.active {
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    font-weight: 600;
}

.draw-op-btn {
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    min-height: 34px;
    background: var(--surface-1);
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
}

.draw-op-primary {
    border-color: rgba(106, 169, 255, 0.34);
    background: var(--accent-blue-dim);
    color: var(--accent-blue);
}

.btn-accent {
    border-color: rgba(139, 209, 124, 0.34);
    background: var(--neon-green-dim);
    color: var(--neon-green);
}

.draw-op-warning {
    border-color: rgba(240, 179, 90, 0.34);
    background: var(--accent-amber-dim);
    color: var(--accent-amber);
}

.btn-danger {
    border-color: rgba(239, 127, 138, 0.34);
    background: var(--accent-rose-dim);
    color: var(--accent-rose);
}

.ghost-btn:hover,
.small-btn:hover,
.template:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.small-btn:disabled {
    opacity: 0.62;
    cursor: not-allowed;
}

.small-btn.ghost {
    background: var(--surface-card);
    border-color: var(--border-subtle);
    color: var(--text-secondary);
}

.style-scroll {
    padding-top: 2px;
}

.style-panel {
    padding: 2px 2px 4px;
}

.template-chip-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.template-chip {
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    color: var(--text-secondary);
    border-radius: var(--radius-md);
    padding: 7px 9px;
    font-size: 12px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
}

.template-chip:hover {
    border-color: var(--border-active);
    background: var(--surface-hover);
}

.chip-dot {
    width: 9px;
    height: 9px;
    border-radius: 999px;
    flex-shrink: 0;
}

.style-divider {
    height: 1px;
    background: var(--border-subtle);
    margin: 12px 0;
}

.select-wrap {
    position: relative;
}

.select-wrap::after {
    content: '▾';
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
    pointer-events: none;
    font-size: 11px;
}

.style-select {
    width: 100%;
    appearance: none;
    border: 1px solid var(--border-subtle);
    background: var(--surface-card-strong);
    color: var(--text-primary);
    border-radius: var(--radius-md);
    padding: 8px 30px 8px 10px;
}

.style-color {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 2px;
    background: var(--surface-card-strong);
    height: 34px;
}

.slider-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    color: var(--text-secondary);
}

.style-slider {
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: linear-gradient(to right, var(--surface-1), var(--neon-cyan));
    outline: none;
}

.style-slider {
    accent-color: var(--neon-cyan);
}

.style-apply-btn {
    margin-top: 8px;
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
}

.hint {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.9;
    padding: 2px 2px 0;
}

.draw-hint {
    border: none;
    background: transparent;
}

.empty {
    color: var(--text-muted);
    font-size: 12px;
}

@media (max-width: 768px) {
    .toolbox-panel {
        padding: 10px;
    }

    .draw-grid {
        grid-template-columns: 1fr 1fr;
    }

    .actions-row,
    .coord-input-actions,
    .field-grid {
        grid-template-columns: 1fr;
    }

    .template-chip-row {
        grid-template-columns: 1fr;
    }

    .name {
        max-width: 120px;
    }

    .feature-badge {
        padding: 1px 6px;
    }

    .action-icon-btn {
        width: 22px;
        height: 22px;
        font-size: 11px;
    }
}

/* ── Upload Tab Styles ── */
.upload-tab-scroll {
    padding: var(--space-md);
}
</style>
