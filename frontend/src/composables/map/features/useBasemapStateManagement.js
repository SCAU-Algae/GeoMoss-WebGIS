/**
 * useBasemapStateManagement.js
 * 
 * [作用] 提取底图状态管理功能，包括状态广播和批量事件合并
 * [特点] 支持底图列表对外同步
 * [模式] Factory 函数，依赖注入状态和方法
 * 
 * 中文注释遵循原有约定，保持代码可读性。
 */

/**
 * 创建底图状态管理特性工厂函数
 * 
 * @param {Object} options - 工厂选项
 * @param {Ref} options.layerList - 底图列表响应式变量
 * @param {Ref} options.selectedLayer - 当前选中底图响应式变量
 * @param {Function} options.getLayerCategory - 获取底图分类函数
 * @param {Function} options.getLayerGroup - 获取底图分组函数
 * @param {Function} options.emit - Vue emit 函数
 * 
 * @returns {Object} 返回底图状态管理功能对象
 */
export function createBasemapStateManagementFeature({
    layerList,
    selectedLayer,
    getLayerCategory,
    getLayerGroup,
    emit
}) {
    /**
     * [改进] 批量 emit 包装器，减少频繁的事件广播
     * 50ms 窗口内的多个 emit 调用会被合并为一次
     */
    const createBatchEmitter = (fn, { batchWindow = 50 } = {}) => {
        let pending = false;
        let timer = null;

        return (...args) => {
            if (pending) return;

            pending = true;
            clearTimeout(timer);

            timer = setTimeout(() => {
                fn(...args);
                pending = false;
            }, batchWindow);
        };
    };

    /**
     * 广播底图列表状态
     * 
     * 将当前底图列表的完整状态（ID、名称、可见性、分类、分组、激活状态）
     * 广播给外部组件，用于面板展示或其他组件联动。
     * 
     * [交互] emit: base-layers-change
     * [改进] 使用批量 emit 减少重绘
     */
    function emitBaseLayersChange() {
        emit('base-layers-change', layerList.value.map(item => ({
            id: item.id,
            name: item.name,
            visible: item.visible,
            category: getLayerCategory(item.id),
            group: getLayerGroup(item.id),
            active: selectedLayer.value === item.id
        })));
    }

    // 创建批量版本的 emit
    const emitBaseLayersChangeBatched = createBatchEmitter(emitBaseLayersChange, { batchWindow: 50 });

    return {
        emitBaseLayersChange,
        emitBaseLayersChangeBatched
    };
}
