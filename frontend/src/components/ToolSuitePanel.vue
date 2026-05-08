<template>
  <div class="tool-suite-panel">
    <div class="tool-suite-tabs">
      <button
        v-for="tab in toolTabs"
        :key="tab.id"
        type="button"
        class="tool-suite-tab"
        :class="{ active: activeTab === tab.id }"
        @click="$emit('switch-tab', tab.id)"
      >
        <component :is="tab.icon" :size="15" :stroke-width="2.2" />
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <div class="tool-suite-body">
      <ChatPanelContent v-show="activeTab === 'chat'" @close-chat="$emit('close-chat')" />

      <BusPlannerPanel
        v-show="activeTab === 'bus'"
        :token="tiandituToken"
        :start-bus-point-pick="startBusPointPick"
        :draw-route-on-map="drawRouteOnMap"
        :zoom-to-bus-route-step="zoomToBusRouteStep"
        :preview-bus-route-step="previewBusRouteStep"
        :clear-bus-route-step-preview="clearBusRouteStepPreview"
        @close="$emit('close')"
      />

      <DrivingPlannerPanel
        v-show="activeTab === 'drive'"
        :token="tiandituToken"
        :start-map-point-pick="startBusPointPick"
        :draw-drive-route-on-map="drawDriveRouteOnMap"
        :zoom-to-drive-route-step="zoomToDriveRouteStep"
        :preview-drive-route-step="previewDriveRouteStep"
        :clear-drive-route-step-preview="clearDriveRouteStepPreview"
        @close="$emit('close')"
      />

      <FengshuiAnalysisPanel
        v-show="activeTab === 'fengshui'"
        :active="activeTab === 'fengshui'"
        :get-map-center="getMapCenter"
        :start-study-area-draw="startStudyAreaDraw"
      />
    </div>
  </div>
</template>

<script setup>
import {
  Bot as BotIcon,
  Bus as BusIcon,
  Car as CarIcon,
  MountainSnow as MountainSnowIcon
} from 'lucide-vue-next';
import ChatPanelContent from './ChatPanelContent.vue';
import BusPlannerPanel from './BusPlannerPanel.vue';
import DrivingPlannerPanel from './DrivingPlannerPanel.vue';
import FengshuiAnalysisPanel from './FengshuiAnalysisPanel.vue';

defineProps({
  activeTab: {
    type: String,
    default: 'chat',
    validator: (value) => ['chat', 'bus', 'drive', 'fengshui'].includes(value)
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
  },
  getMapCenter: {
    type: Function,
    default: null
  },
  startStudyAreaDraw: {
    type: Function,
    default: null
  }
});

defineEmits(['switch-tab', 'close-chat', 'close']);

const tiandituToken = import.meta.env.VITE_TIANDITU_TK;
const toolTabs = [
  { id: 'chat', label: 'AI', icon: BotIcon },
  { id: 'bus', label: '公交', icon: BusIcon },
  { id: 'drive', label: '驾车', icon: CarIcon },
  { id: 'fengshui', label: '风水', icon: MountainSnowIcon }
];
</script>

<style scoped>
.tool-suite-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  color: var(--text-primary);
  background: transparent;
}

.tool-suite-tabs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  padding: 8px;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}

.tool-suite-tab {
  min-width: 0;
  min-height: 36px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.045);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    color var(--duration-fast) var(--ease-spatial);
}

.tool-suite-tab:hover,
.tool-suite-tab.active {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  background: var(--neon-cyan-dim);
}

.tool-suite-tab span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-suite-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

@container (max-width: 360px) {
  .tool-suite-tabs {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
