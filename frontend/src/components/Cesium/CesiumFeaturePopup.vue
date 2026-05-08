<template>
  <div
    v-if="visible"
    class="cesium-feature-popup"
    :style="popupStyle"
  >
    <div class="popup-head">
      <strong>{{ title }}</strong>
      <button type="button" aria-label="关闭属性弹窗" @click="$emit('close')">×</button>
    </div>
    <div class="popup-body">
      <div v-for="row in rows" :key="row.key" class="popup-row">
        <span>{{ row.key }}</span>
        <em>{{ row.value }}</em>
      </div>
      <div v-if="!rows.length" class="popup-empty">暂无属性</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

const props = defineProps({
  feature: { type: Object, default: null }
});

defineEmits(['close']);

const viewport = ref({
  width: typeof window !== 'undefined' ? window.innerWidth : 1280,
  height: typeof window !== 'undefined' ? window.innerHeight : 720
});

function updateViewport() {
  viewport.value = {
    width: window.innerWidth || viewport.value.width,
    height: window.innerHeight || viewport.value.height
  };
}

const visible = computed(() => !!props.feature?.properties);

const title = computed(() => {
  return String(props.feature?.title || '建筑属性');
});

const rows = computed(() => {
  const properties = props.feature?.properties && typeof props.feature.properties === 'object'
    ? props.feature.properties
    : {};
  return Object.entries(properties)
    .filter(([key]) => !String(key).startsWith('_'))
    .slice(0, 10)
    .map(([key, value]) => ({
      key,
      value: typeof value === 'object' ? JSON.stringify(value) : String(value)
    }));
});

const popupStyle = computed(() => {
  const screen = props.feature?.screen || {};
  const x = Math.max(14, Math.min(viewport.value.width - 314, Number(screen.x || 0) + 14));
  const y = Math.max(14, Math.min(viewport.value.height - 334, Number(screen.y || 0) - 12));
  return {
    transform: `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`
  };
});

onMounted(() => {
  window.addEventListener('resize', updateViewport, { passive: true });
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewport);
});
</script>

<style scoped>
.cesium-feature-popup {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 4600;
  width: min(300px, calc(100vw - 28px));
  max-height: min(320px, calc(100vh - 28px));
  border: 1px solid var(--border-active);
  border-radius: var(--radius-md);
  background: rgba(7, 14, 18, 0.9);
  box-shadow: var(--shadow-panel), var(--neon-cyan-glow);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  color: var(--text-primary);
  overflow: hidden;
  pointer-events: auto;
}

.popup-head {
  min-height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 8px 0 12px;
  border-bottom: 1px solid var(--border-subtle);
  background: linear-gradient(90deg, rgba(71, 215, 198, 0.16), transparent);
}

.popup-head strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.popup-head button {
  width: 28px;
  height: 28px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.06);
  color: var(--text-secondary);
  cursor: pointer;
}

.popup-head button:hover {
  color: var(--neon-cyan);
  border-color: var(--border-active);
}

.popup-body {
  max-height: 272px;
  overflow: auto;
  padding: 8px;
}

.popup-row {
  display: grid;
  grid-template-columns: minmax(70px, 0.42fr) minmax(0, 1fr);
  gap: 8px;
  padding: 7px 4px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  font-size: 12px;
}

.popup-row span {
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.popup-row em {
  color: var(--text-primary);
  font-style: normal;
  overflow-wrap: anywhere;
}

.popup-empty {
  padding: 10px;
  color: var(--text-muted);
  font-size: 12px;
}
</style>
