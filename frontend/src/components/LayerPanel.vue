<template>
    <div class="layer-panel-container">
        <!-- 图层目录 -->
        <div class="layer-tree-wrap card">
            <div class="card-title">图层目录</div>
            <div v-if="layerTree.length" class="layer-tree-root">
                <TOCTreeItem
                    v-for="node in layerTree"
                    :key="node.id"
                    :node="node"
                    :active-layer-id="activeLayerId"
                    :selected-layer-ids="selectedLayerIds"
                    @action="handleTreeAction"
                />
            </div>
            <div v-else class="empty">暂无图层</div>
        </div>
    </div>
</template>

<script setup>
import { computed, ref } from 'vue';
import { useLayerStore } from '../stores';
import TOCTreeItem from './TOCTreeItem.vue';

defineProps({
    drawLayers: { type: Array, default: () => [] },
    routeLayers: { type: Array, default: () => [] },
    searchLayers: { type: Array, default: () => [] },
    uploadLayers: { type: Array, default: () => [] },
    selectedLayerIds: { type: Array, default: () => [] },
    hasDrawCard: { type: Boolean, default: false },
    overview: { type: Object, default: () => ({ drawCount: 0 }) },
    isRasterLayer: { type: Function, required: true }
});

const emit = defineEmits(['action']);
const layerStore = useLayerStore();

const activeLayerId = ref(null);
const layerTree = computed(() => layerStore.layerTree);

function handleTreeAction(evt) {
    if (!evt?.type) return;

    if (evt.type === 'layer-selected') {
        activeLayerId.value = evt.layerId;
        return;
    }

    if (evt.type === 'toggle-folder-expand') {
        layerStore.setLayerTreeFolderExpanded(evt.nodeId, !!evt.expanded);
        return;
    }

    if (evt.type === 'toggle-folder-visibility') {
        const leaves = layerStore.getLayerLeafNodesByFolder(evt.nodeId);
        leaves.forEach((leaf) => {
            emit('action', {
                type: 'toggle-layer-visibility',
                layerId: leaf.id,
                visible: !!evt.visible
            });
        });
        return;
    }

    emit('action', evt);
}
</script>

<style scoped>
.layer-panel-container {
    display: flex;
    flex-direction: column;
    gap: 0;
}

.layer-tree-wrap {
    padding: 12px;
}

.layer-tree-root {
    display: flex;
    flex-direction: column;
    gap: 3px;
}

.card {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    backdrop-filter: blur(8px);
    box-shadow: var(--shadow-button);
}

.card-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 8px;
    letter-spacing: 0.3px;
}

.empty {
    color: var(--text-muted);
    font-size: 12px;
    padding: 12px 8px;
    text-align: center;
}
</style>
