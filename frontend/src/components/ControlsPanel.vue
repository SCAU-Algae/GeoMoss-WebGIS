<template>
    <div class="sidebar-shell">
        <div class="sidebar-container">
            <div class="sidebar-item" v-for="item in menuItems" :key="item.id" :class="{ active: activeId === item.id }"
                @click="handleSelect(item.id)">

                <div class="icon-wrapper">
                    <component :is="item.icon" :size="20" />
                </div>

                <span class="label">{{ item.label }}</span>
            </div>
        </div>

        <AdministrativeDivisionPanel :visible="districtPanelVisible" @close="districtPanelVisible = false"
            @select="handleDistrictSelect" />

        <!-- Map Swipe 底图选择对话框 -->
        <div v-if="showSwipeDialog" class="swipe-dialog-overlay" @click.self="cancelSwipeDialog">
            <div class="swipe-dialog-box">
                <div class="dialog-header">
                    <h3>卷帘分析 - 选择对比底图</h3>
                    <button class="close-btn" @click="cancelSwipeDialog">×</button>
                </div>

                <div class="dialog-content">
                    <div class="form-group">
                        <label>左侧底图：</label>
                        <select v-model="leftBasemap" class="basemap-select">
                            <option v-for="option in SWIPE_SUPPORTED_BASEMAPS" :key="option.value"
                                :value="option.value">
                                {{ option.label }}
                            </option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>右侧底图：</label>
                        <select v-model="rightBasemap" class="basemap-select">
                            <option v-for="option in SWIPE_SUPPORTED_BASEMAPS" :key="option.value"
                                :value="option.value">
                                {{ option.label }}
                            </option>
                        </select>
                    </div>

                    <div class="form-group">
                        <label>滑动模式：</label>
                        <div class="mode-selector">
                            <button class="mode-btn" :class="{ active: swipeMode === 'horizontal' }"
                                @click="swipeMode = 'horizontal'">
                                <arrow-left-right :size="16" :stroke-width="2" />
                                水平
                            </button>
                            <button class="mode-btn" :class="{ active: swipeMode === 'vertical' }"
                                @click="swipeMode = 'vertical'">
                                <arrow-up-down :size="16" :stroke-width="2" />
                                竖直
                            </button>
                        </div>
                    </div>
                </div>

                <div class="dialog-footer">
                    <button class="cancel-btn" @click="cancelSwipeDialog">取消</button>
                    <button class="confirm-btn" @click="confirmSwipeConfig">启用对比</button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useMessage } from '../composables/useMessage';
import { ref } from 'vue';
import AdministrativeDivisionPanel from './AdministrativeDivisionPanel.vue';
import {
    Map as MapIcon,
    Columns2,
    Layers,
    Pencil,
    Ruler,
    MapPin,
    Boxes,
    LayoutGrid,
    ArrowLeftRight,
    ArrowUpDown
} from 'lucide-vue-next';
import { useLayerStore } from '../stores/useLayerStore';
import { BASEMAP_OPTIONS } from '../constants';

const message = useMessage();
const layerStore = useLayerStore();

// ========== 卷帘分析支持的底图 ==========
// 排除不支持的底图：'custom'（需要customUrl）和'local_tiles_preset'（本地瓦片）
const SWIPE_SUPPORTED_BASEMAPS = BASEMAP_OPTIONS.filter(
    option => option.value !== 'custom' && option.value !== 'local_tiles_preset'
);

// ========== Map Swipe 对话框状态 ==========
const showSwipeDialog = ref(false);
const leftBasemap = ref(SWIPE_SUPPORTED_BASEMAPS[0]?.value || '');
const rightBasemap = ref(SWIPE_SUPPORTED_BASEMAPS[1]?.value || '');
const swipeMode = ref('horizontal');

const emit = defineEmits([
    'open-tab',
    'map-interaction',
    'show-analysis',
    'district-select',
    'enable-basemap-swipe'
]);

const activeId = ref('map');
const districtPanelVisible = ref(false);

const menuItems = [
    { id: 'layers', label: '图层', icon: Layers, action: 'toggleLayers' },
    { id: 'draw', label: '绘制', icon: Pencil, action: 'toggleDraw' },
    { id: 'measure', label: '测量', icon: Ruler, action: 'toggleMeasure' },
    { id: 'mark', label: '标注', icon: MapPin, action: 'toggleMark' },
    { id: 'swipe', label: '对比', icon: Columns2, action: 'toggleMore' },
    { id: 'analyze', label: '分析', icon: Boxes, action: 'toggleAnalyze' },
    { id: 'adcode', label: '区划', icon: LayoutGrid, action: 'toggleAdcode' },
    { id: 'map', label: '信息', icon: MapIcon, action: 'toggleMap' },
];

const handleSelect = (id) => {
    // 1. 更新 UI 选中状态
    activeId.value = id;

    if (id !== 'adcode' && districtPanelVisible.value) {
        districtPanelVisible.value = false;
    }

    // 2. 找到当前点击的对象，以便获取 action
    const currentItem = menuItems.find(item => item.id === id);
    if (!currentItem) return;

    // 3. 执行对应业务逻辑（与现有 HomeView/MapContainer 能力打通）
    switch (currentItem.action) {
        case 'toggleMap':
            emit('open-tab', 'info');
            message.info('已打开地图信息面板');
            break;

        case 'toggleLayers':
            emit('open-tab', 'toolbox');
            break;

        case 'toggleDraw':
            emit('open-tab', 'toolbox');
            emit('map-interaction', 'Polygon');
            message.info('已进入绘制流程，可在工具箱切换点/线/面');
            break;

        case 'toggleMeasure':
            emit('open-tab', 'toolbox');
            emit('map-interaction', 'MeasureDistance');
            message.info('已激活测距工具');
            break;

        case 'toggleMark':
            emit('open-tab', 'toolbox');
            emit('map-interaction', 'ReverseGeocodePick');
            message.info('请在地图单击进行标注与逆地理编码');
            break;

        case 'toggleAnalyze':
            emit('open-tab', 'toolbox');
            emit('show-analysis');
            message.info('分析入口已打开');
            break;

        case 'toggleAdcode':
            districtPanelVisible.value = !districtPanelVisible.value;
            message.info(districtPanelVisible.value ? '行政区划面板已打开' : '行政区划面板已关闭');
            break;

        case 'toggleMore':
            // Map Swipe 双底图对比功能
            if (layerStore.swipeConfig.enabled) {
                // 已启用，关闭
                layerStore.disableSwipe();
                message.success('卷帘分析已关闭');
            } else {
                // 未启用，打开对话框让用户选择左右底图
                showSwipeDialog.value = true;
            }
            break;

        default:
            message.warn("未识别的 Action:", currentItem.action);
            break;
    }
};

const handleDistrictSelect = (payload) => {
    emit('district-select', payload);
};

// ========== Map Swipe 对话框处理 ==========
/**
 * 确认并启用Map Swipe，传递选中的底图
 */
const confirmSwipeConfig = () => {
    if (!leftBasemap.value || !rightBasemap.value) {
        message.warn('请选择左右两个不同的底图');
        return;
    }

    if (leftBasemap.value === rightBasemap.value) {
        message.warn('左右底图不能相同');
        return;
    }

    // 向MapContainer emit事件，请求启用双底图swipe
    emit('enable-basemap-swipe', {
        leftBasemap: leftBasemap.value,
        rightBasemap: rightBasemap.value,
        mode: swipeMode.value
    });

    showSwipeDialog.value = false;
    message.success(`正在加载卷帘对比：${getBasemapLabel(leftBasemap.value)} / ${getBasemapLabel(rightBasemap.value)}`);
};

/**
 * 取消对话框
 */
const cancelSwipeDialog = () => {
    showSwipeDialog.value = false;
    leftBasemap.value = SWIPE_SUPPORTED_BASEMAPS[0]?.value || '';
    rightBasemap.value = SWIPE_SUPPORTED_BASEMAPS[1]?.value || '';
    swipeMode.value = 'horizontal';
};

/**
 * 根据底图ID获取显示名称
 */
const getBasemapLabel = (id) => {
    const option = BASEMAP_OPTIONS.find(opt => opt.value === id);
    return option?.label || id;
};

</script>

<style scoped>
.sidebar-shell {
    position: relative;
    height: 100%;
}

.sidebar-container {
    height: 100%;
    position: relative;
    background:
        linear-gradient(180deg, var(--surface-card-strong), var(--glass-bg-heavy));
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
    border: 1px solid var(--glass-border);
    border-left: none;
    display: flex;
    flex-direction: column;
    padding: 12px 4px 12px 0;
    border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
    gap: 8px;
    box-shadow: var(--shadow-panel);
    z-index: 1000;
}

.sidebar-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 56px;
    min-height: 56px;
    cursor: pointer;
    transition:
        background-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial);
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    color: var(--text-secondary);
    border: 1px solid transparent;
    position: relative;
}

.icon-wrapper {
    margin-bottom: 4px;
    display: inline-flex;
    transition: transform var(--duration-fast) var(--ease-spatial);
}

.label {
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0;
}

/* 悬停效果 */
.sidebar-item:hover {
    background: var(--surface-hover);
    color: var(--text-primary);
    border-color: var(--border-subtle);
    transform: translateX(2px);
}

.sidebar-item.active {
    background: linear-gradient(135deg, var(--neon-cyan-dim), var(--neon-green-dim));
    color: var(--neon-cyan);
    border-color: var(--border-active);
    box-shadow: inset 3px 0 0 var(--neon-cyan), 0 8px 18px rgba(0, 0, 0, 0.18);
}

.sidebar-item.active .icon-wrapper {
    transform: translateY(-1px) scale(1.05);
}

/* ========== Map Swipe 对话框样式 ========== */
.swipe-dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--scrim-bg);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    backdrop-filter: blur(8px);
}

.swipe-dialog-box {
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-elevated);
    min-width: 380px;
    max-width: min(92vw, 440px);
    overflow: hidden;
    animation: dialogSlideIn var(--duration-panel) var(--ease-spring-subtle);
    color: var(--text-primary);
}

@keyframes dialogSlideIn {
    from {
        opacity: 0;
        transform: scale(0.96) translateY(-14px);
    }

    to {
        opacity: 1;
        transform: scale(1) translateY(0);
    }
}

.dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 18px;
    border-bottom: 1px solid var(--border-subtle);
    background: linear-gradient(135deg, rgba(71, 215, 198, 0.16), rgba(139, 209, 124, 0.12));
    color: var(--text-primary);
}

.dialog-header h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
}

.close-btn {
    background: var(--surface-1);
    border: 1px solid var(--border-subtle);
    font-size: 22px;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition:
        transform var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        background-color var(--duration-fast) var(--ease-spatial);
}

.close-btn:hover {
    transform: scale(1.04);
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--surface-hover);
}

.dialog-content {
    padding: 24px;
}

.form-group {
    margin-bottom: 20px;
}

.form-group:last-child {
    margin-bottom: 0;
}

.form-group label {
    display: block;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--text-secondary);
    font-size: 14px;
}

.basemap-select {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border-subtle);
    min-height: 44px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    background: var(--surface-card);
    color: var(--text-primary);
    cursor: pointer;
    transition:
        border-color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        background-color var(--duration-fast) var(--ease-spatial);
}

.basemap-select:hover {
    border-color: var(--border-active);
}

.basemap-select:focus {
    outline: none;
    border-color: var(--neon-cyan);
    box-shadow: 0 0 0 3px var(--neon-cyan-dim);
}

.mode-selector {
    display: flex;
    gap: 12px;
}

.mode-btn {
    flex: 1;
    min-height: 44px;
    padding: 10px 16px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--surface-card);
    color: var(--text-secondary);
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition:
        background-color var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
}

.mode-btn:hover {
    border-color: var(--border-active);
    color: var(--text-primary);
}

.mode-btn.active {
    background: var(--neon-cyan-dim);
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.dialog-footer {
    display: flex;
    gap: 12px;
    padding: 16px 24px;
    border-top: 1px solid var(--border-subtle);
    background: rgba(7, 14, 13, 0.42);
}

.cancel-btn,
.confirm-btn {
    flex: 1;
    padding: 12px 20px;
    border: 1px solid var(--border-subtle);
    min-height: 44px;
    border-radius: var(--radius-sm);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition:
        background-color var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
}

.cancel-btn {
    background: var(--surface-card);
    color: var(--text-secondary);
}

.cancel-btn:hover {
    border-color: var(--border-active);
    background: var(--surface-hover);
}

.confirm-btn {
    background: linear-gradient(135deg, rgba(71, 215, 198, 0.28), rgba(139, 209, 124, 0.22));
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.confirm-btn:hover {
    transform: translateY(-2px);
    box-shadow: var(--neon-cyan-glow);
}

.confirm-btn:active {
    transform: translateY(0);
}
</style>
