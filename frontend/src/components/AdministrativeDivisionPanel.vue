<template>
    <transition name="eco-panel-fade">
        <section v-if="visible" class="eco-district-panel" aria-label="行政区划面板">
            <header class="eco-header">
                <div class="header-left">
                    <span class="header-icon" aria-hidden="true"></span>
                    <h3 class="eco-title">行政区划</h3>
                </div>
                <button class="eco-close-btn" type="button" @click="emit('close')">×</button>
            </header>

            <!-- 搜索区 -->
            <div class="eco-search-section">
                <div class="search-input-wrapper">
                    <input v-model.trim="searchKeyword" class="eco-input" type="text" placeholder="搜索省市区或 adcode..."
                        autocomplete="off" />
                    <span class="search-icon" aria-hidden="true"></span>
                </div>
            </div>

            <!-- 数据统计：浅绿色胶囊 -->
            <div class="eco-meta-bar">
                <div v-if="tocStore.districtTreeLoading" class="eco-status-tag loading">数据加载中...</div>
                <div v-else-if="tocStore.districtTreeError" class="eco-status-tag error">加载失败</div>
                <div v-else class="eco-stats">
                    <span class="stat-item">总数: {{ tocStore.districtTreeTotalNodeCount }}</span>
                    <span class="stat-divider"></span>
                    <span class="stat-item">匹配: {{ matchedNodeCount }}</span>
                </div>
            </div>

            <!-- 树形内容区 -->
            <div class="eco-panel-body">
                <div v-if="tocStore.districtTreeLoading" class="eco-loading">
                    <div class="spinner"></div>
                    <p>正在读取 adcode 树...</p>
                </div>

                <div v-else-if="tocStore.districtTreeError" class="eco-error-box">
                    <p>{{ tocStore.districtTreeError }}</p>
                    <button type="button" class="eco-retry-btn" @click="tocStore.loadDistrictTree(BASE_URL, true)">重试</button>
                </div>

                <template v-else>
                    <ul v-if="filteredTreeData.length" class="eco-tree-root">
                        <AdministrativeDivisionTreeNode v-for="node in filteredTreeData"
                            :key="`${node.value}_${node.label}`" :node="node" :level="0" :auto-expand="autoExpand"
                            :selected-adcode="selectedAdcode" @select="handleNodeSelect" />
                    </ul>
                    <div v-else class="eco-empty-state">没有匹配到行政区节点</div>
                </template>
            </div>
        </section>
    </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useTOCStore } from '@/stores';
import AdministrativeDivisionTreeNode from './AdministrativeDivisionTreeNode.vue';

const props = defineProps({
    visible: {
        type: Boolean,
        default: false
    }
});

const emit = defineEmits(['close', 'select']);

const tocStore = useTOCStore();

const BASE_URL = import.meta.env.BASE_URL || '/';

const searchKeyword = ref('');
const selectedAdcode = ref('');

function filterTreeNodes(nodes = [], keyword = '') {
    const query = String(keyword || '').trim().toLowerCase();
    if (!query) return nodes;

    const result = [];
    nodes.forEach((node) => {
        const label = String(node.label || '').toLowerCase();
        const value = String(node.value || '').toLowerCase();
        const childMatches = filterTreeNodes(node.children || [], query);
        const currentMatch = label.includes(query) || value.includes(query);

        if (currentMatch || childMatches.length > 0) {
            result.push({
                ...node,
                children: childMatches
            });
        }
    });

    return result;
}

function countTreeNodes(nodes = []) {
    let total = 0;
    for (const node of nodes) {
        total += 1;
        if (Array.isArray(node.children) && node.children.length) {
            total += countTreeNodes(node.children);
        }
    }
    return total;
}

const keywordLower = computed(() => String(searchKeyword.value || '').trim().toLowerCase());
const filteredTreeData = computed(() => filterTreeNodes(tocStore.districtTree, keywordLower.value));
const matchedNodeCount = computed(() => countTreeNodes(filteredTreeData.value));
const autoExpand = computed(() => keywordLower.value.length > 0);

function handleNodeSelect(payload) {
    const adcode = String(payload?.value || '').trim();
    if (!adcode) return;

    selectedAdcode.value = adcode;
    emit('select', {
        label: String(payload?.label || '').trim(),
        value: adcode
    });
}

watch(
    () => props.visible,
    (nextVisible) => {
        if (!nextVisible) return;
        void tocStore.loadDistrictTree(BASE_URL);
    },
    { immediate: true }
);
</script>

<style scoped>
.eco-district-panel {
    position: absolute;
    left: 80px;
    top: 100px;
    bottom: 40px;
    width: 320px;
    background: var(--glass-bg-heavy);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-elevated);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid var(--glass-border);
    z-index: 1060;
    color: var(--text-primary);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
}

.eco-header {
    padding: 14px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: var(--text-primary);
    border-bottom: 1px solid var(--border-subtle);
    background: linear-gradient(135deg, rgba(71, 215, 198, 0.12), rgba(139, 209, 124, 0.08));
}

.header-left {
    display: flex;
    align-items: center;
    gap: 8px;
}

.eco-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    letter-spacing: 0;
}

.header-icon {
    width: 9px;
    height: 9px;
    border-radius: var(--radius-full);
    background: var(--neon-cyan);
    box-shadow: var(--neon-cyan-glow);
}

.eco-close-btn {
    width: 26px;
    height: 26px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: rgba(71, 215, 198, 0.08);
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 18px;
    line-height: 22px;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.eco-close-btn:hover {
    color: var(--neon-cyan);
    background: rgba(71, 215, 198, 0.16);
    border-color: var(--border-active);
}

.eco-search-section {
    padding: 16px 16px 8px;
}

.search-input-wrapper {
    position: relative;
    display: flex;
    align-items: center;
}

.eco-input {
    width: 100%;
    height: 38px;
    background: rgba(5, 11, 10, 0.5);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 0 35px 0 12px;
    color: var(--text-primary);
    font-size: 13px;
    outline: none;
    transition: all var(--duration-fast) var(--ease-spatial);
}

.eco-input:focus {
    background: rgba(5, 11, 10, 0.68);
    border-color: var(--border-active);
    box-shadow: 0 0 0 3px rgba(71, 215, 198, 0.08);
}

.eco-input::placeholder {
    color: var(--text-muted);
}

.search-icon {
    position: absolute;
    right: 12px;
    width: 8px;
    height: 8px;
    border: 1px solid var(--text-muted);
    border-radius: 50%;
    pointer-events: none;
}

.search-icon::after {
    content: '';
    position: absolute;
    width: 5px;
    height: 1px;
    right: -4px;
    bottom: -2px;
    background: var(--text-muted);
    transform: rotate(45deg);
}

.eco-meta-bar {
    padding: 4px 16px 12px;
}

.eco-stats {
    background: var(--surface-0);
    border: 1px solid var(--border-subtle);
    padding: 6px 14px;
    border-radius: var(--radius-full);
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: var(--text-secondary);
    font-size: 11px;
    font-weight: bold;
}

.stat-divider {
    width: 1px;
    height: 10px;
    background: var(--border-subtle);
}

/* 列表主体 */
.eco-panel-body {
    flex: 1;
    overflow-y: auto;
    padding: 0 12px 16px;
}

.eco-panel-body::-webkit-scrollbar {
    width: 4px;
}
.eco-panel-body::-webkit-scrollbar-thumb {
    background: rgba(71, 215, 198, 0.24);
    border-radius: 10px;
}

.eco-tree-root {
    list-style: none;
    margin: 0;
    padding: 0;
}

/* 加载与重试样式 */
.eco-loading {
    padding: 40px 0;
    text-align: center;
    color: var(--text-secondary);
}

.eco-retry-btn {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border: 1px solid var(--border-active);
    padding: 6px 16px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    margin-top: 8px;
}

.eco-empty-state {
    text-align: center;
    color: var(--text-muted);
    padding: 40px 0;
    font-size: 13px;
}

.eco-panel-fade-enter-active,
.eco-panel-fade-leave-active {
    transition: opacity var(--duration-normal) var(--ease-panel),
        transform var(--duration-normal) var(--ease-panel);
}

.eco-panel-fade-enter-from,
.eco-panel-fade-leave-to {
    opacity: 0;
    transform: translateY(20px) scale(0.98);
}

@media (max-width: 900px) {
    .eco-district-panel {
        left: 10px;
        width: calc(100% - 20px);
    }
}
</style>
