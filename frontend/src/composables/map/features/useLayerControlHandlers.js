/**
 * 图层控制面板事件处理库（Phase 21）
 *
 * 功能：
 * - 处理底图切换
 * - 处理图层排序、显隐、透明度更新
 */

export function createLayerControlHandlers({
    selectedLayerRef,
    layerListRef,
    refreshLayersState
}) {
    /**
     * [改进] 删除第一层防抖，让 watch 防抖处理
     * 响应延迟从 600ms → 300ms
     */
    function applyBasemapSelection(layerId) {
        const normalizedLayerId = String(layerId || '').trim();
        if (!normalizedLayerId || !selectedLayerRef) return;
        
        // 相同底图不重复设置，避免触发多余的 watch
        if (selectedLayerRef.value === normalizedLayerId) {
            return;
        }
        
        selectedLayerRef.value = normalizedLayerId;
    }

    /**
     * 统一接收图层切换。
     * [改进] 直接设置 ref，让 watch 处理防抖
     */
    function handleLayerChange(payload = {}) {
        const nextLayerId = String(payload.layerId || '').trim();
        if (nextLayerId) {
            // 直接设置，不防抖（防抖由 watch 处理）
            applyBasemapSelection(nextLayerId);
        }
    }

    /**
     * 处理图层排序、可见性和透明度更新。
     */
    function handleLayerOrderUpdate(payload = {}) {
        const list = layerListRef?.value;
        if (!Array.isArray(list)) return;

        if (payload.type === 'reorder') {
            const dragIndex = Number(payload.dragIndex);
            const dropIndex = Number(payload.dropIndex);
            if (!Number.isInteger(dragIndex) || !Number.isInteger(dropIndex)) return;
            if (dragIndex < 0 || dropIndex < 0) return;
            if (dragIndex >= list.length || dropIndex >= list.length) return;
            if (dragIndex === dropIndex) return;

            const moved = list.splice(dragIndex, 1)[0];
            list.splice(dropIndex, 0, moved);
            refreshLayersState?.();
            return;
        }

        if (payload.type === 'visibility') {
            const target = list.find((item) => item.id === payload.layerId);
            if (!target) return;
            target.visible = !!payload.visible;
            refreshLayersState?.();
            return;
        }

        if (payload.type === 'opacity') {
            const layerId = String(payload.layerId);
            const opacity = Number(payload.opacity);
            if (!Number.isFinite(opacity) || opacity < 0 || opacity > 1) return;

            const target = list.find((item) => item.id === layerId);
            if (!target) return;
            target.opacity = opacity;
            refreshLayersState?.();
        }
    }

    return {
        handleLayerChange,
        handleLayerOrderUpdate
    };
}
