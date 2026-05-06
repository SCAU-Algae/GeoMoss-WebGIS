<template>
    <div class="info-panel" :class="{ 'collapsed': isCollapsed, 'in-dihuan': props.locationInfo.isInDihuan }">
        <!-- 折叠开关 -->
        <div class="toggle-handle" @click="$emit('toggle-panel')" :title="isCollapsed ? '展开面板' : '收起面板'">
            <!-- 只用一个向左的箭头，通过动态 class 控制旋转 -->
            <svg class="handle-icon" :class="{ 'is-flipped': !isCollapsed }" viewBox="0 0 24 24" fill="none"
                stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 19l-7-7 7-7" />
            </svg>
        </div>

        <!-- 面板内容区域 -->
        <div class="panel-content" v-show="!isCollapsed"
            :class="{ 'no-padding': activeTab === 'chat' || activeTab === 'toolbox' || activeTab === 'bus' || activeTab === 'drive' || activeTab === 'compass' }">
            <div class="active-feature-banner" v-if="activeFeature?.label">
                当前激活功能：{{ activeFeature.label }}
            </div>

            <!-- 模式 1: AI 聊天 -->
            <div v-show="activeTab === 'chat'" class="toolbox-content">
                <ChatPanelContent @close-chat="$emit('close-chat')" />
            </div>

            <!-- 模式 2: 工具箱 -->
            <div v-show="activeTab === 'toolbox'" class="toolbox-content">
                <ToolboxPanel :userLayers="userLayers" :baseLayers="baseLayers" :overview="toolboxOverview"
                    :uploadProgress="uploadProgress" :latest-search-poi="latestSearchPoi"
                    @close="$emit('switch-tab', 'info')" @upload-data="$emit('upload-data', $event)"
                    @interaction="$emit('interaction', $event)"
                    @toggle-layer-visibility="$emit('toggle-layer-visibility', $event)"
                    @change-layer-opacity="$emit('change-layer-opacity', $event)"
                    @set-base-layer="$emit('set-base-layer', $event)"
                    @toggle-base-layer-visibility="$emit('toggle-base-layer-visibility', $event)"
                    @toggle-layer-label-visibility="$emit('toggle-layer-label-visibility', $event)"
                    @set-layer-label-field="$emit('set-layer-label-field', $event)"
                    @zoom-layer="$emit('zoom-layer', $event)" @view-layer="$emit('view-layer', $event)"
                    @remove-layer="$emit('remove-layer', $event)"
                    @reorder-user-layers="$emit('reorder-user-layers', $event)"
                    @solo-layer="$emit('solo-layer', $event)"
                    @apply-style-template="$emit('apply-style-template', $event)"
                    @update-draw-style="$emit('update-draw-style', $event)"
                    @update-layer-style="$emit('update-layer-style', $event)"
                    @highlight-attribute-feature="$emit('highlight-attribute-feature', $event)"
                    @zoom-attribute-feature="$emit('zoom-attribute-feature', $event)"
                    @draw-point-by-coordinates="$emit('draw-point-by-coordinates', $event)"
                    @draw-amap-aoi-from-json="$emit('draw-amap-aoi-from-json', $event)"
                    @toggle-layer-crs="$emit('toggle-layer-crs', $event)"
                    @export-layer-data="$emit('export-layer-data', $event)"
                    @upload-shp-3d="$emit('upload-shp-3d', $event)"
                    @upload-3dtiles-zip="$emit('upload-3dtiles-zip', $event)"
                    @load-3dtiles-url="$emit('load-3dtiles-url', $event)" />
            </div>

            <!-- 模式 3: 公交规划 -->
            <div v-show="activeTab === 'bus'" class="toolbox-content">
                <BusPlannerPanel :token="tiandituToken" :start-bus-point-pick="startBusPointPick"
                    :draw-route-on-map="drawRouteOnMap" :zoom-to-bus-route-step="zoomToBusRouteStep"
                    :preview-bus-route-step="previewBusRouteStep"
                    :clear-bus-route-step-preview="clearBusRouteStepPreview" @close="$emit('switch-tab', 'info')" />
            </div>

            <!-- 模式 4: 驾车规划 -->
            <div v-show="activeTab === 'drive'" class="toolbox-content">
                <DrivingPlannerPanel :token="tiandituToken" :start-map-point-pick="startBusPointPick"
                    :draw-drive-route-on-map="drawDriveRouteOnMap" :zoom-to-drive-route-step="zoomToDriveRouteStep"
                    :preview-drive-route-step="previewDriveRouteStep"
                    :clear-drive-route-step-preview="clearDriveRouteStepPreview" @close="$emit('switch-tab', 'info')" />
            </div>

            <!-- 模式 5: 风水罗盘 -->
            <div v-show="activeTab === 'compass'" class="toolbox-content">
                <CompassControlPanel :get-user-location="getUserLocation" @close="$emit('switch-tab', 'info')" />
            </div>

            <!-- 模式 6: 天气看板 -->
            <div v-show="activeTab === 'weather'" class="toolbox-content weather-tab-content">
                <WeatherChartPanel />
            </div>

            <!-- 模式 7: 新闻热点 -->
            <div v-if="activeTab === 'info'" class="info-content news-dashboard">
                <div class="news-header-bar">
                    <span class="news-logo">Hot News</span>
                    <span class="news-subtitle">{{ currentPlatformLabel }} 实时热点</span>
                </div>

                <!-- 平台标签 -->
                <div class="news-platform-tabs">
                    <button
                        v-for="p in newsPlatforms"
                        :key="p.key"
                        class="platform-chip"
                        :class="{ active: currentPlatform === p.key }"
                        @click="switchNewsPlatform(p.key)"
                    >{{ p.label }}</button>
                </div>

                <!-- 加载状态 -->
                <div v-if="newsLoading" class="news-loading">
                    <div class="loading-dot-pulse"></div>
                    <span>获取热点中...</span>
                </div>

                <!-- 新闻列表 -->
                <div v-else class="news-list">
                    <a
                        v-motion
                        :initial="{ opacity: 0, y: 20 }"
                        :enter="{ opacity: 1, y: 0, transition: { delay: idx * 40, duration: 350, ease: [0.16, 1, 0.3, 1] } }"
                        v-for="(item, idx) in newsItems"
                        :key="idx"
                        :href="item.url"
                        target="_blank"
                        class="news-card"
                    >
                        <div class="news-rank" :class="rankClass(idx)">{{ idx + 1 }}</div>
                        <div class="news-body">
                            <div class="news-title">{{ item.title }}</div>
                            <div class="news-meta" v-if="item.desc || item.content">
                                <span class="news-desc">{{ item.desc || item.content }}</span>
                            </div>
                        </div>
                        <div class="news-score" v-if="item.score || item.publish_time">
                            <span class="score-value">{{ item.publish_time ? item.publish_time.slice(-8) : formatScore(item.score) }}</span>
                        </div>
                    </a>
                    <div v-if="!newsItems.length && !newsLoading" class="news-empty">
                        暂无热点数据
                    </div>
                </div>

                <div class="news-footer">
                    <span class="footer-status" :class="{ live: !newsLoading }">
                        <span class="status-dot"></span>
                        {{ newsLoading ? '加载中' : `更新于 ${lastNewsUpdate}` }}
                    </span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
/**
 * SidePanel.vue - 可折叠侧边栏组件
 * 
 * 功能：
 * - 新闻展示模式 (info)
 * - AI 聊天模式 (chat)
 * - 支持折叠/展开
 * - 移动端自适应
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import ChatPanelContent from './ChatPanelContent.vue';
import ToolboxPanel from './TOCPanel.vue';
import BusPlannerPanel from './BusPlannerPanel.vue';
import DrivingPlannerPanel from './DrivingPlannerPanel.vue';
import CompassControlPanel from './CompassControlPanel.vue';
import WeatherChartPanel from './WeatherChartPanel.vue';

// ========== 1. 新闻平台配置 ==========
const NEWS_PLATFORMS = [
    { key: 'weibo', label: '微博' },
    { key: 'zhihu', label: '知乎' },
    { key: 'baidu', label: '百度' },
    { key: 'bilibili', label: 'B站' },
    { key: 'tskr', label: '36氪' },
    { key: 'github', label: 'GitHub' },
    { key: 'juejin', label: '掘金' },
    { key: 'hackernews', label: 'HN' },
    { key: 'douyin', label: '抖音' },
    { key: 'vtex', label: 'V2EX' },
    { key: 'tieba', label: '贴吧' },
    { key: 'jinritoutiao', label: '头条' },
];

const NEWS_API_BASE = 'https://orz.ai/api/v1/dailynews';
const NEWS_REFRESH_INTERVAL = 10 * 60 * 1000; // 10 min

function formatScore(raw) {
    const n = Number(raw);
    if (!Number.isFinite(n)) return '';
    if (n >= 10000) return (n / 10000).toFixed(1) + 'w';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
    return String(n);
}

// ========== 2. Props & Emits ==========
const props = defineProps({
    locationInfo: {
        type: Object,
        default: () => ({ isInDihuan: false, lonLat: [0, 0] })
    },
    selectedImage: {
        type: String,
        default: ''
    },
    activeTab: {
        type: String,
        default: 'info' // 'info' | 'chat' | 'toolbox' | 'bus' | 'drive' | 'compass'
    },
    isCollapsed: {
        type: Boolean,
        default: false
    },
    userLayers: {
        type: Array,
        default: () => []
    },
    baseLayers: {
        type: Array,
        default: () => []
    },
    toolboxOverview: {
        type: Object,
        default: () => ({ drawCount: 0, uploadCount: 0, layers: [] })
    },
    uploadProgress: {
        type: Object,
        default: () => ({ phase: 'idle' })
    },
    latestSearchPoi: {
        type: Object,
        default: () => ({})
    },
    activeFeature: {
        type: Object,
        default: () => ({ key: 'info', label: '新闻' })
    },
    getUserLocation: {
        type: Function,
        default: null
    },
    startBusPointPick: {
        type: Function,
        default: null
    },
    drawRouteOnMap: {
        type: Function,
        default: null
    },
    zoomToBusRouteStep: {
        type: Function,
        default: null
    },
    previewBusRouteStep: {
        type: Function,
        default: null
    },
    clearBusRouteStepPreview: {
        type: Function,
        default: null
    },
    drawDriveRouteOnMap: {
        type: Function,
        default: null
    },
    zoomToDriveRouteStep: {
        type: Function,
        default: null
    },
    previewDriveRouteStep: {
        type: Function,
        default: null
    },
    clearDriveRouteStepPreview: {
        type: Function,
        default: null
    }
});

const tiandituToken = import.meta.env.VITE_TIANDITU_TK;

const emit = defineEmits([
    'toggle-panel',
    'close-chat',
    'switch-tab',
    'upload-data',
    'interaction',
    'toggle-layer-visibility',
    'change-layer-opacity',
    'set-base-layer',
    'toggle-base-layer-visibility',
    'toggle-layer-label-visibility',
    'set-layer-label-field',
    'zoom-layer',
    'view-layer',
    'remove-layer',
    'reorder-user-layers',
    'solo-layer',
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

// ========== 3. 新闻状态 ==========
const currentPlatform = ref('weibo');
const newsItems = ref([]);
const newsLoading = ref(false);
const lastNewsUpdate = ref('');
let newsTimer = null;

const newsPlatforms = computed(() => NEWS_PLATFORMS);

const currentPlatformLabel = computed(() => {
    const p = NEWS_PLATFORMS.find((p) => p.key === currentPlatform.value);
    return p?.label || currentPlatform.value;
});

function rankClass(idx) {
    if (idx === 0) return 'rank-top1';
    if (idx === 1) return 'rank-top2';
    if (idx === 2) return 'rank-top3';
    return '';
}

async function fetchNews(platform) {
    newsLoading.value = true;
    try {
        const resp = await fetch(`${NEWS_API_BASE}/?platform=${platform}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const json = await resp.json();
        if (json.status === '200' && Array.isArray(json.data)) {
            newsItems.value = json.data.slice(0, 25);
            const now = new Date();
            lastNewsUpdate.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;
        } else {
            newsItems.value = [];
        }
    } catch {
        newsItems.value = [];
    } finally {
        newsLoading.value = false;
    }
}

function switchNewsPlatform(platform) {
    if (currentPlatform.value === platform) return;
    currentPlatform.value = platform;
    fetchNews(platform);
}

onMounted(() => {
    fetchNews(currentPlatform.value);
    newsTimer = setInterval(() => fetchNews(currentPlatform.value), NEWS_REFRESH_INTERVAL);
});

onUnmounted(() => {
    if (newsTimer) clearInterval(newsTimer);
});
</script>

<style scoped>
/* 布局容器 */
.info-panel {
    display: flex; flex-direction: row; height: 100%;
    background: linear-gradient(180deg, var(--surface-card-strong), var(--glass-bg-heavy));
    backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    overflow: hidden; box-shadow: var(--shadow-panel);
    transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.35s var(--ease-out-expo);
    transition:
        width var(--duration-panel) var(--ease-spring-subtle),
        transform var(--duration-panel) var(--ease-spring-subtle),
        opacity var(--duration-normal) var(--ease-spatial);
    position: relative;
    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
    border: 1px solid var(--border-subtle);
}

.toggle-handle {
    width: 28px; height: 56px;
    align-self: center;
    background: var(--surface-1);
    border: 1px solid var(--border-subtle);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer;
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    transition: all var(--duration-fast) var(--ease-spatial);
    z-index: 20;
    position: absolute;
    left: 0; top: 50%;
    transform: translateY(-50%);
}
.toggle-handle:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
    box-shadow: var(--neon-cyan-glow);
    transform: translateY(-50%) translateX(-2px);
}

.handle-icon {
    width: 20px;
    height: 20px;
    color: var(--neon-cyan);
    transition: transform var(--duration-panel) var(--ease-spring-subtle);
}

.handle-icon.is-flipped {
    transform: rotate(180deg);
}

/* 内容区域 */
.panel-content {
    flex: 1;
    /* padding: 20px;  Removed: Moved to .info-content */
    /* overflow-y: auto; Removed: Moved to .info-content */
    display: flex;
    flex-direction: column;
    min-width: 300px;
    height: 100%;
    overflow: hidden;
}

.active-feature-banner {
    padding: 9px 16px;
    background: linear-gradient(90deg, var(--neon-cyan-dim), transparent);
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    border-bottom: 1px solid var(--border-subtle);
}

.toolbox-content {
    flex: 1;
    overflow-y: auto;
    background: transparent;
}

.panel-content.no-padding {
    padding: 0;
}

.info-content {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
}

/* 头部 */
.panel-header {
    display: flex;
    align-items: center;
    border-bottom: 1px solid var(--border-subtle);
    padding: 0 0 14px;
}

.logo {
    width: 46px;
    height: 46px;
    object-fit: contain;
    margin-right: 14px;
}

.main-title {
    font-family: var(--font-display);
    font-size: 18px;
    color: var(--text-primary);
    text-decoration: none;
    font-weight: 700;
}

/* 新闻标题 */
.news-header {
    font-size: 17px;
    margin: 0;
    font-weight: 700;
    line-height: 1.4;
    min-height: 48px;
    /* 保持高度稳定，防止跳动 */
}

.news-header a {
    color: var(--neon-cyan);
    text-decoration: none;
    transition: color var(--duration-fast) var(--ease-spatial);
}

.news-header a:hover {
    color: var(--text-primary);
    text-decoration: underline;
}

/* 图片 */
.image-container {
    width: 100%;
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: var(--shadow-button);
    margin-bottom: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface-card);
    border: 1px solid var(--border-subtle);
    aspect-ratio: 16 / 10;
}

.news-image {
    width: 100%;
    height: 100%;
    /* 始终完整显示（不裁剪） */
    object-fit: contain;
    display: block;
    transition: transform var(--duration-normal) var(--ease-spatial), max-height var(--duration-normal) var(--ease-spatial);
    max-height: 52vh;
}

.news-image:hover {
    transform: scale(1.01);
}

/* 文本 */
.text-content {
    font-size: 14px;
    color: var(--text-secondary);
    line-height: 1.6;
    margin-bottom: 0;
    flex-grow: 1;
}

/* 按钮 */
.action-button {
    background: linear-gradient(135deg, var(--neon-cyan-dim), var(--neon-green-dim));
    color: var(--text-primary);
    border: 1px solid var(--border-active);
    min-height: 44px;
    padding: 12px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    border-radius: var(--radius-md);
    transition:
        transform var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        background-color var(--duration-fast) var(--ease-spatial);
    box-shadow: var(--shadow-button);
}

.action-button:hover {
    border-color: var(--border-glow);
    box-shadow: var(--neon-cyan-glow);
}

.action-button:active {
    transform: translateY(1px) scale(0.99);
}

/* 底部 */
.panel-footer {
    margin-top: auto;
    text-align: center;
    padding-top: 14px;
    border-top: 1px solid var(--border-subtle);
    font-size: 12px;
}

.panel-footer a {
    color: var(--text-muted);
    text-decoration: none;
    transition: color var(--duration-fast) var(--ease-spatial);
}

.panel-footer a:hover {
    color: var(--neon-cyan);
}

/* 移动端适配 */
@media (max-width: 768px) {
    .info-panel {
        display: flex;
        /* 确保父容器是 Flex 布局 */
        flex-direction: column;
        /* 垂直排列 */
        width: 100% !important;

        /* 1. 设置面板高度为视口高度的 60% */
        height: 60vh;

        transition: transform var(--duration-slow) var(--ease-panel);
        overflow: visible;
        /* 允许按钮溢出显示 */

        /* 定位基准，确保收起动画逻辑清晰 */
        position: fixed;
        bottom: 0;
        left: 0;
    }

    /* 收起状态下的处理：将整个面板向下推 */
    .info-panel.collapsed {
        /* 向上平移 100% 负方向减去按钮高度，或者直接推下去 */
        transform: translateY(100%);
        /* 注意：如果完全推下去，按钮也会看不见。
           通常配合 transition 使用，或者只推 60vh 的高度 */
    }

    .toggle-handle {
        width: 88px;
        height: 34px;
        align-self: center;
        border-radius: var(--radius-full) var(--radius-full) 0 0;

        /* 核心修改 */
        position: static;
        /* 恢复默认，不再需要 relative */
        margin-top: -34px;
        /* 用负外边距向上拉 */
        margin-bottom: 0;

        transform: translateX(0%);
        /* 保持你的水平偏移 */
    }

    .handle-icon {
        /* 旋转箭头方向 */
        transition: transform var(--duration-normal) var(--ease-panel);
        transform: rotate(90deg);
        width: 20px;
        /* 建议给 SVG 设置明确大小 */
        height: 20px;
    }

    .handle-icon.is-flipped {
        transform: rotate(-90deg);
    }

    .info-content {
        /* 5. 确保内容区自动填充剩余空间 */
        flex: 1;
        padding: 15px;
        overflow-y: auto;
        /* 内容过多时可滚动 */
        background: var(--glass-bg-heavy);
    }
}

/* ── News Dashboard Styles ── */
.news-dashboard {
    display: flex;
    flex-direction: column;
    height: 100%;
    gap: 0;
    padding: 0 !important;
}

.news-header-bar {
    padding: var(--space-lg) var(--space-lg) var(--space-sm);
    flex-shrink: 0;
}
.news-logo {
    font-family: var(--font-display);
    font-size: var(--font-size-xl);
    font-weight: 700;
    background: linear-gradient(135deg, var(--neon-cyan), var(--neon-green));
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    display: block;
    line-height: 1.2;
}
.news-subtitle {
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

.news-platform-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 0 var(--space-lg) var(--space-md);
    flex-shrink: 0;
}
.platform-chip {
    padding: 5px 12px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out-expo);
}
.platform-chip:hover {
    border-color: var(--border-active);
    color: var(--text-secondary);
}
.platform-chip.active {
    background: var(--neon-cyan-dim);
    border-color: var(--border-active);
    color: var(--neon-cyan);
}

.news-loading {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-md);
    padding: var(--space-2xl);
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
}
.loading-dot-pulse {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--neon-cyan);
    animation: dotPulse 1.2s var(--ease-out-expo) infinite;
}
@keyframes dotPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(71, 215, 198, 0.6); }
    50% { box-shadow: 0 0 0 12px rgba(71, 215, 198, 0); }
}

.news-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 var(--space-md);
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.news-card {
    display: flex;
    align-items: flex-start;
    gap: var(--space-md);
    padding: 10px var(--space-sm);
    border-radius: var(--radius-sm);
    text-decoration: none;
    color: inherit;
    transition: background var(--duration-fast) var(--ease-out-expo);
    animation: cardIn var(--duration-slow) var(--ease-out-expo) both;
}
@keyframes cardIn {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: translateY(0); }
}
.news-card:hover {
    background: var(--surface-0);
}
.news-rank {
    flex-shrink: 0;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--text-muted);
    border-radius: var(--radius-sm);
    background: rgba(0, 0, 0, 0.2);
}
.rank-top1 { color: #f0b35a; background: rgba(240, 179, 90, 0.12); }
.rank-top2 { color: #a0b8c8; background: rgba(160, 184, 200, 0.1); }
.rank-top3 { color: #c89070; background: rgba(200, 144, 112, 0.1); }

.news-body {
    flex: 1;
    min-width: 0;
}
.news-title {
    font-family: var(--font-body);
    font-size: var(--font-size-sm);
    font-weight: 500;
    color: var(--text-primary);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    transition: color var(--duration-fast);
}
.news-card:hover .news-title {
    color: var(--neon-cyan);
}
.news-desc {
    font-family: var(--font-body);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    line-height: 1.4;
    margin-top: 2px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.news-score {
    flex-shrink: 0;
}
.score-value {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-muted);
    background: rgba(0, 0, 0, 0.25);
    padding: 2px 8px;
    border-radius: var(--radius-full);
}
.news-empty {
    padding: var(--space-2xl);
    text-align: center;
    color: var(--text-muted);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
}

.news-footer {
    padding: var(--space-md) var(--space-lg);
    border-top: 1px solid var(--border-subtle);
    flex-shrink: 0;
}
.footer-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--text-muted);
}
.footer-status.live { color: var(--neon-green); }
.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}
.footer-status.live .status-dot {
    animation: dotPulse 2s var(--ease-out-expo) infinite;
}
</style>
