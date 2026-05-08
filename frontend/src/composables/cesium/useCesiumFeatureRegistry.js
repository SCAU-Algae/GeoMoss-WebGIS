import { reactive } from 'vue';

export function createCesiumFeatureRegistry(context = {}) {
  const tools = reactive(new Map());
  const state = reactive({
    activeToolId: '',
    activeCategory: 'measure',
    statusText: '工具待命',
    measurements: [],
    sketches: [],
    bookmarks: [],
    selectedFeature: null,
    loading: {}
  });

  const disposers = [];

  function getViewer() {
    return context.getViewer?.() || null;
  }

  function getCesium() {
    return context.getCesium?.() || window.Cesium || null;
  }

  function notify(message, level = 'info') {
    const api = context.message;
    if (api?.[level]) {
      api[level](message);
      return;
    }
    if (api?.info) api.info(message);
  }

  function registerTool(tool) {
    const id = String(tool?.id || '').trim();
    if (!id) return null;
    tools.set(id, {
      id,
      label: String(tool?.label || id),
      category: String(tool?.category || 'general'),
      activate: typeof tool?.activate === 'function' ? tool.activate : null,
      deactivate: typeof tool?.deactivate === 'function' ? tool.deactivate : null,
      destroy: typeof tool?.destroy === 'function' ? tool.destroy : null,
      metadata: tool?.metadata || {}
    });
    return tools.get(id);
  }

  function deactivateActiveTool() {
    const current = tools.get(state.activeToolId);
    if (current?.deactivate) {
      current.deactivate({ state, getViewer, getCesium, notify });
    }
    state.activeToolId = '';
  }

  function activateTool(id) {
    const nextId = String(id || '').trim();
    const tool = tools.get(nextId);
    if (!tool) {
      notify('工具暂不可用', 'warning');
      return false;
    }
    if (state.activeToolId === nextId) {
      deactivateActiveTool();
      state.statusText = '工具已关闭';
      return true;
    }
    deactivateActiveTool();
    state.activeToolId = nextId;
    state.activeCategory = tool.category || state.activeCategory;
    if (tool.activate) {
      tool.activate({ state, getViewer, getCesium, notify });
    }
    return true;
  }

  function addDisposer(disposer) {
    if (typeof disposer === 'function') disposers.push(disposer);
  }

  function destroy() {
    deactivateActiveTool();
    tools.forEach((tool) => {
      try { tool.destroy?.({ state, getViewer, getCesium, notify }); } catch (_) {}
    });
    while (disposers.length) {
      try { disposers.pop()?.(); } catch (_) {}
    }
    tools.clear();
  }

  return {
    state,
    tools,
    registerTool,
    activateTool,
    deactivateActiveTool,
    addDisposer,
    destroy,
    getViewer,
    getCesium,
    notify
  };
}
