
<!--
  WebGIS Platform — 2D/3D 地理信息系统
  组件架构：TopBar / MapContainer / SidePanel
  技术栈：Vue 3 + OpenLayers + Cesium + FastAPI
-->
<script setup>
import { RouterView } from 'vue-router'
import GlobalLoading from './components/GlobalLoading.vue'
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route" mode="out-in">
      <component :is="Component" />
    </Transition>
  </RouterView>
  <GlobalLoading />
</template>

<style>
.route-enter-active {
  transition: opacity 0.25s cubic-bezier(0.16, 1, 0.3, 1), transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.route-leave-active {
  transition: opacity 0.15s ease, transform 0.2s ease;
}
.route-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.route-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Global Styles */
html, body {
    margin: 0;
    padding: 0;
    font-size: 15px;
    color: var(--text-primary);
    background: var(--deep-0);
    height: 100%;
    width: 100%;
    overflow: hidden;
}

#app {
    height: 100%;
    width: 100%;
}
</style>
