<template>
    <div ref="stageRef" class="floating-panel-stage">
        <button
            v-if="!open"
            class="floating-panel-launcher"
            :class="{ 'is-left-launcher': resolvedLauncherSide === 'left' }"
            :style="launcherStyle"
            type="button"
            :aria-label="`打开${title}`"
            @click="openPanel"
        >
            <component :is="LauncherIcon" :size="21" :stroke-width="2.3" />
            <span class="launcher-label">{{ launcherLabel || title }}</span>
        </button>

        <section
            v-else
            ref="panelRef"
            class="floating-panel-window"
            :class="{
                'is-dragging': isDragging,
                'is-resizing': isResizing,
                'is-docked': state.mode === 'docked',
                'is-left-docked': state.mode === 'docked' && resolvedDockSide === 'left',
                'is-maximized': state.mode === 'maximized'
            }"
            :style="panelStyle"
            role="dialog"
            :aria-label="title"
            @pointerdown="bringToFront"
        >
            <header class="floating-panel-header" @pointerdown="startDrag" @dblclick="toggleMaximize">
                <div class="header-grip" aria-hidden="true">
                    <grip-vertical-icon :size="18" :stroke-width="2.2" />
                </div>
                <div class="header-copy">
                    <strong class="panel-title">{{ title }}</strong>
                    <span v-if="subtitle" class="panel-subtitle">{{ subtitle }}</span>
                </div>
                <div class="header-actions">
                    <button type="button" class="window-action" :aria-label="state.mode === 'maximized' ? '还原窗口' : '最大化窗口'" @click.stop="toggleMaximize">
                        <minimize-2-icon v-if="state.mode === 'maximized'" :size="17" :stroke-width="2.2" />
                        <maximize-2-icon v-else :size="17" :stroke-width="2.2" />
                    </button>
                    <button type="button" class="window-action close-action" aria-label="关闭窗口" @click.stop="closePanel">
                        <x-icon :size="17" :stroke-width="2.3" />
                    </button>
                </div>
            </header>

            <div class="floating-panel-body">
                <slot />
            </div>

            <button
                v-for="handle in resizeHandles"
                :key="handle"
                type="button"
                class="resize-handle"
                :class="`resize-${handle}`"
                :aria-label="`调整${title}窗口大小`"
                @pointerdown.stop.prevent="startResize($event, handle)"
            />
        </section>
    </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';
import {
    GripVertical as GripVerticalIcon,
    Maximize2 as Maximize2Icon,
    Minimize2 as Minimize2Icon,
    PanelLeftOpen as PanelLeftOpenIcon,
    PanelRightOpen as PanelRightOpenIcon,
    X as XIcon
} from 'lucide-vue-next';

const props = defineProps({
    open: { type: Boolean, default: false },
    title: { type: String, default: '浮窗' },
    subtitle: { type: String, default: '' },
    launcherLabel: { type: String, default: '' },
    minWidth: { type: Number, default: 340 },
    minHeight: { type: Number, default: 168 },
    defaultWidth: { type: Number, default: 430 },
    defaultHeight: { type: Number, default: 680 },
    dockGap: { type: Number, default: 10 },
    dockSide: {
        type: String,
        default: 'right',
        validator: (value) => ['left', 'right'].includes(value)
    },
    dockTop: { type: [Number, String], default: null },
    launcherSide: {
        type: String,
        default: 'right',
        validator: (value) => ['left', 'right'].includes(value)
    },
    launcherTop: { type: [Number, String], default: '50%' }
});

const emit = defineEmits(['update:open', 'mode-change']);

const stageRef = ref(null);
const panelRef = ref(null);
const isDragging = ref(false);
const isResizing = ref(false);
const zIndex = ref(2700);

const resizeHandles = ['n', 'e', 's', 'w', 'ne', 'nw', 'se', 'sw'];

const state = reactive({
    x: 0,
    y: 0,
    width: props.defaultWidth,
    height: props.defaultHeight,
    mode: 'docked'
});

const restoreState = reactive({
    x: 0,
    y: 0,
    width: props.defaultWidth,
    height: props.defaultHeight,
    mode: 'floating'
});

let activePointer = null;
let dragStart = null;
let resizeStart = null;
let initialized = false;
let previousMode = state.mode;

const panelStyle = computed(() => ({
    width: `${Math.round(state.width)}px`,
    height: `${Math.round(state.height)}px`,
    transform: `translate3d(${Math.round(state.x)}px, ${Math.round(state.y)}px, 0)`,
    zIndex: zIndex.value
}));

const resolvedDockSide = computed(() => props.dockSide === 'left' ? 'left' : 'right');
const resolvedLauncherSide = computed(() => props.launcherSide === 'left' ? 'left' : 'right');
const LauncherIcon = computed(() => resolvedLauncherSide.value === 'left' ? PanelLeftOpenIcon : PanelRightOpenIcon);
const launcherStyle = computed(() => {
    const top = formatCssLength(props.launcherTop, '50%');
    return resolvedLauncherSide.value === 'left'
        ? { left: '0', right: 'auto', top }
        : { right: '0', left: 'auto', top };
});

function getBounds() {
    const rect = stageRef.value?.getBoundingClientRect?.();
    return {
        width: Math.max(1, rect?.width || window.innerWidth || 1),
        height: Math.max(1, rect?.height || window.innerHeight || 1)
    };
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function formatCssLength(value, fallback = '0px') {
    if (value === null || value === undefined || value === '') return fallback;
    if (typeof value === 'number') return `${value}px`;
    return String(value);
}

function resolveDockY(bounds) {
    const raw = props.dockTop;
    if (raw === null || raw === undefined || raw === '') return props.dockGap;
    if (typeof raw === 'number') return raw;
    const text = String(raw).trim();
    if (text.endsWith('%')) {
        const percent = Number.parseFloat(text);
        if (Number.isFinite(percent)) return (bounds.height * percent / 100) - (state.height / 2);
    }
    const numeric = Number.parseFloat(text);
    return Number.isFinite(numeric) ? numeric : props.dockGap;
}

function resolveDockX(bounds) {
    return resolvedDockSide.value === 'left'
        ? props.dockGap
        : Math.max(0, bounds.width - state.width - props.dockGap);
}

function clampState() {
    const bounds = getBounds();
    const maxWidth = Math.max(props.minWidth, bounds.width);
    const maxHeight = Math.max(props.minHeight, bounds.height);

    state.width = clamp(state.width, props.minWidth, maxWidth);
    state.height = clamp(state.height, props.minHeight, maxHeight);
    state.x = clamp(state.x, 0, Math.max(0, bounds.width - state.width));
    state.y = clamp(state.y, 0, Math.max(0, bounds.height - state.height));
}

function rememberRestoreState() {
    if (state.mode === 'maximized') return;
    restoreState.x = state.x;
    restoreState.y = state.y;
    restoreState.width = state.width;
    restoreState.height = state.height;
    restoreState.mode = state.mode === 'docked' ? 'floating' : state.mode;
}

function initializePanel() {
    const bounds = getBounds();
    const availableWidth = Math.max(props.minWidth, bounds.width - props.dockGap * 2);
    const availableHeight = Math.max(props.minHeight, bounds.height - props.dockGap * 2);

    state.width = clamp(initialized ? state.width : props.defaultWidth, props.minWidth, availableWidth);
    state.height = clamp(initialized ? state.height : Math.min(props.defaultHeight, availableHeight), props.minHeight, availableHeight);
    state.x = resolveDockX(bounds);
    state.y = clamp(resolveDockY(bounds), props.dockGap, Math.max(props.dockGap, bounds.height - state.height - props.dockGap));
    state.mode = 'docked';
    initialized = true;
    emitModeChange();
}

function emitModeChange() {
    if (previousMode !== state.mode) {
        previousMode = state.mode;
        emit('mode-change', state.mode);
    }
}

function openPanel() {
    emit('update:open', true);
    nextTick(initializePanel);
}

function closePanel() {
    emit('update:open', false);
}

function bringToFront() {
    zIndex.value = 2800;
}

function dockPanel({ preserveSize = true, useConfiguredY = false } = {}) {
    const bounds = getBounds();
    if (!preserveSize) {
        state.height = clamp(bounds.height - props.dockGap * 2, props.minHeight, bounds.height);
    }
    state.width = clamp(state.width, props.minWidth, Math.max(props.minWidth, bounds.width - props.dockGap * 2));
    state.height = clamp(state.height, props.minHeight, Math.max(props.minHeight, bounds.height - props.dockGap * 2));
    state.x = resolveDockX(bounds);
    const nextY = useConfiguredY ? resolveDockY(bounds) : state.y;
    state.y = clamp(nextY, props.dockGap, Math.max(props.dockGap, bounds.height - state.height - props.dockGap));
    state.mode = 'docked';
    emitModeChange();
}

function maximize() {
    rememberRestoreState();
    const bounds = getBounds();
    state.x = 0;
    state.y = 0;
    state.width = bounds.width;
    state.height = bounds.height;
    state.mode = 'maximized';
    emitModeChange();
}

function restoreFromMaximize() {
    state.x = restoreState.x;
    state.y = restoreState.y;
    state.width = restoreState.width;
    state.height = restoreState.height;
    state.mode = restoreState.mode || 'floating';
    clampState();
    emitModeChange();
}

function toggleMaximize() {
    if (state.mode === 'maximized') {
        restoreFromMaximize();
        return;
    }
    maximize();
}

function startDrag(event) {
    if (event.button !== undefined && event.button !== 0) return;
    if (event.target?.closest?.('.window-action')) return;

    bringToFront();
    activePointer = event.pointerId;
    isDragging.value = true;
    if (state.mode === 'maximized') restoreFromMaximize();

    dragStart = {
        pointerX: event.clientX,
        pointerY: event.clientY,
        x: state.x,
        y: state.y
    };

    panelRef.value?.setPointerCapture?.(event.pointerId);
    window.addEventListener('pointermove', onDragMove);
    window.addEventListener('pointerup', stopDrag, { once: true });
}

function onDragMove(event) {
    if (!isDragging.value || event.pointerId !== activePointer || !dragStart) return;
    const bounds = getBounds();
    const nextX = dragStart.x + event.clientX - dragStart.pointerX;
    const nextY = dragStart.y + event.clientY - dragStart.pointerY;

    state.x = clamp(nextX, 0, Math.max(0, bounds.width - state.width));
    state.y = clamp(nextY, 0, Math.max(0, bounds.height - state.height));
    state.mode = 'floating';
}

function stopDrag(event) {
    if (event?.pointerId !== undefined && event.pointerId !== activePointer) return;
    window.removeEventListener('pointermove', onDragMove);
    panelRef.value?.releasePointerCapture?.(activePointer);
    isDragging.value = false;
    activePointer = null;
    dragStart = null;

    const bounds = getBounds();
    const nearDockEdge = resolvedDockSide.value === 'left'
        ? state.x <= 36
        : bounds.width - (state.x + state.width) <= 36;
    if (nearDockEdge) {
        dockPanel({ preserveSize: true });
    } else {
        clampState();
        emitModeChange();
    }
}

function startResize(event, handle) {
    if (event.button !== undefined && event.button !== 0) return;
    bringToFront();
    activePointer = event.pointerId;
    isResizing.value = true;
    if (state.mode === 'maximized') restoreFromMaximize();

    resizeStart = {
        handle,
        pointerX: event.clientX,
        pointerY: event.clientY,
        x: state.x,
        y: state.y,
        width: state.width,
        height: state.height
    };

    panelRef.value?.setPointerCapture?.(event.pointerId);
    window.addEventListener('pointermove', onResizeMove);
    window.addEventListener('pointerup', stopResize, { once: true });
}

function onResizeMove(event) {
    if (!isResizing.value || event.pointerId !== activePointer || !resizeStart) return;
    const bounds = getBounds();
    const dx = event.clientX - resizeStart.pointerX;
    const dy = event.clientY - resizeStart.pointerY;
    const handle = resizeStart.handle;

    let nextX = resizeStart.x;
    let nextY = resizeStart.y;
    let nextWidth = resizeStart.width;
    let nextHeight = resizeStart.height;

    if (handle.includes('e')) {
        nextWidth = resizeStart.width + dx;
    }
    if (handle.includes('s')) {
        nextHeight = resizeStart.height + dy;
    }
    if (handle.includes('w')) {
        nextWidth = resizeStart.width - dx;
        nextX = resizeStart.x + dx;
    }
    if (handle.includes('n')) {
        nextHeight = resizeStart.height - dy;
        nextY = resizeStart.y + dy;
    }

    nextWidth = clamp(nextWidth, props.minWidth, bounds.width);
    nextHeight = clamp(nextHeight, props.minHeight, bounds.height);

    if (handle.includes('w')) {
        nextX = resizeStart.x + resizeStart.width - nextWidth;
    }
    if (handle.includes('n')) {
        nextY = resizeStart.y + resizeStart.height - nextHeight;
    }

    state.x = clamp(nextX, 0, Math.max(0, bounds.width - nextWidth));
    state.y = clamp(nextY, 0, Math.max(0, bounds.height - nextHeight));
    state.width = nextWidth;
    state.height = nextHeight;
    state.mode = 'floating';
}

function stopResize(event) {
    if (event?.pointerId !== undefined && event.pointerId !== activePointer) return;
    window.removeEventListener('pointermove', onResizeMove);
    panelRef.value?.releasePointerCapture?.(activePointer);
    isResizing.value = false;
    activePointer = null;
    resizeStart = null;

    const bounds = getBounds();
    const nearDockEdge = resolvedDockSide.value === 'left'
        ? state.x <= 24
        : bounds.width - (state.x + state.width) <= 24;
    if (nearDockEdge) {
        dockPanel({ preserveSize: true });
    } else {
        clampState();
        emitModeChange();
    }
}

function handleWindowResize() {
    if (!props.open) return;
    if (state.mode === 'maximized') {
        maximize();
    } else if (state.mode === 'docked') {
        dockPanel({ preserveSize: true, useConfiguredY: initialized });
    } else {
        clampState();
    }
}

watch(
    () => props.open,
    (nextOpen) => {
        if (nextOpen) {
            nextTick(initializePanel);
        }
    },
    { immediate: true }
);

if (typeof window !== 'undefined') {
    window.addEventListener('resize', handleWindowResize, { passive: true });
}

onBeforeUnmount(() => {
    window.removeEventListener('pointermove', onDragMove);
    window.removeEventListener('pointermove', onResizeMove);
    window.removeEventListener('resize', handleWindowResize);
});
</script>

<style scoped>
.floating-panel-stage {
    position: absolute;
    inset: 0;
    z-index: 2600;
    pointer-events: none;
    overflow: hidden;
}

.floating-panel-launcher,
.floating-panel-window {
    pointer-events: auto;
}

.floating-panel-launcher {
    position: absolute;
    right: 0;
    top: 50%;
    width: 56px;
    min-height: 136px;
    transform: translateY(-50%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 9px;
    padding: 12px 6px;
    border: 1px solid var(--border-active);
    border-right: 0;
    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
    background: linear-gradient(180deg, var(--surface-card-strong), var(--glass-bg-heavy));
    color: var(--neon-cyan);
    box-shadow: var(--shadow-panel), inset 0 0 18px var(--neon-cyan-dim);
    cursor: pointer;
    touch-action: manipulation;
    transition:
        transform var(--duration-panel) var(--ease-spring-subtle),
        box-shadow var(--duration-normal) var(--ease-spatial),
        border-color var(--duration-normal) var(--ease-spatial),
        color var(--duration-normal) var(--ease-spatial);
    animation: launcherReturn 420ms var(--ease-spring-subtle) both;
}

.floating-panel-launcher:hover {
    color: var(--text-primary);
    border-color: var(--border-glow);
    box-shadow: var(--shadow-panel), var(--neon-cyan-glow);
    transform: translateY(-50%) translateX(-3px) scale(1.02);
}

.floating-panel-launcher:active {
    transform: translateY(-50%) translateX(-3px) scale(0.96);
}

.floating-panel-launcher.is-left-launcher {
    border-right: 1px solid var(--border-active);
    border-left: 0;
    border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
}

.floating-panel-launcher.is-left-launcher:hover {
    transform: translateY(-50%) translateX(3px) scale(1.02);
}

.floating-panel-launcher.is-left-launcher:active {
    transform: translateY(-50%) translateX(3px) scale(0.96);
}

.launcher-label {
    writing-mode: vertical-rl;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: 0;
}

.floating-panel-window {
    position: absolute;
    left: 0;
    top: 0;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border: 1px solid var(--border-active);
    border-radius: var(--radius-lg);
    background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.065), transparent 34%),
        var(--glass-bg-heavy);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    box-shadow:
        0 24px 60px rgba(0, 0, 0, 0.42),
        0 0 0 1px rgba(71, 215, 198, 0.08),
        inset 0 0 26px rgba(71, 215, 198, 0.08);
    overflow: hidden;
    transform-origin: right center;
    animation: panelPop 440ms var(--ease-spring-subtle) both;
    transition:
        transform var(--duration-panel) var(--ease-spring-subtle),
        width var(--duration-panel) var(--ease-spring-subtle),
        height var(--duration-panel) var(--ease-spring-subtle),
        border-radius var(--duration-normal) var(--ease-spatial),
        box-shadow var(--duration-normal) var(--ease-spatial);
    container-type: size;
}

.floating-panel-window.is-dragging,
.floating-panel-window.is-resizing {
    transition: none;
    user-select: none;
}

.floating-panel-window.is-docked {
    border-radius: var(--radius-lg) 0 0 var(--radius-lg);
}

.floating-panel-window.is-left-docked {
    border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
}

.floating-panel-window.is-maximized {
    border-radius: var(--radius-lg);
}

.floating-panel-header {
    flex: 0 0 48px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 10px 0 12px;
    border-bottom: 1px solid var(--border-subtle);
    background: linear-gradient(90deg, rgba(71, 215, 198, 0.16), rgba(139, 209, 124, 0.08), transparent);
    cursor: grab;
    touch-action: none;
}

.floating-panel-header:active {
    cursor: grabbing;
}

.header-grip {
    width: 24px;
    height: 32px;
    display: grid;
    place-items: center;
    color: var(--neon-cyan);
    opacity: 0.78;
}

.header-copy {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
}

.panel-title,
.panel-subtitle {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.panel-title {
    color: var(--text-primary);
    font-size: 14px;
    font-weight: 800;
}

.panel-subtitle {
    color: var(--text-muted);
    font-size: 11px;
    font-family: var(--font-mono);
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

.window-action {
    width: 32px;
    height: 32px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    background: rgba(5, 11, 10, 0.4);
    color: var(--text-secondary);
    display: inline-grid;
    place-items: center;
    cursor: pointer;
    transition:
        transform var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        background-color var(--duration-fast) var(--ease-spatial);
}

.window-action:hover {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
    transform: translateY(-1px);
}

.close-action:hover {
    color: #ff8a8a;
    border-color: rgba(255, 138, 138, 0.45);
    background: rgba(255, 91, 91, 0.12);
}

.floating-panel-body {
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
    container-type: size;
}

.resize-handle {
    position: absolute;
    z-index: 3;
    border: 0;
    padding: 0;
    background: transparent;
    opacity: 0;
    touch-action: none;
}

.resize-n,
.resize-s {
    left: 14px;
    right: 14px;
    height: 10px;
    cursor: ns-resize;
}

.resize-n { top: -3px; }
.resize-s { bottom: -3px; }

.resize-e,
.resize-w {
    top: 14px;
    bottom: 14px;
    width: 10px;
    cursor: ew-resize;
}

.resize-e { right: -3px; }
.resize-w { left: -3px; }

.resize-ne,
.resize-nw,
.resize-se,
.resize-sw {
    width: 18px;
    height: 18px;
}

.resize-ne { right: -4px; top: -4px; cursor: nesw-resize; }
.resize-nw { left: -4px; top: -4px; cursor: nwse-resize; }
.resize-se { right: -4px; bottom: -4px; cursor: nwse-resize; }
.resize-sw { left: -4px; bottom: -4px; cursor: nesw-resize; }

@keyframes panelPop {
    0% {
        opacity: 0;
        transform: translate3d(var(--start-x, 0), var(--start-y, 0), 0) scale(0.72);
    }
    62% {
        opacity: 1;
        filter: saturate(1.12);
    }
    100% {
        opacity: 1;
    }
}

@keyframes launcherReturn {
    0% {
        opacity: 0;
        transform: translateY(-50%) scale(0.82);
    }
    100% {
        opacity: 1;
        transform: translateY(-50%) translateX(0) scale(1);
    }
}

@container (max-width: 420px), (max-height: 260px) {
    .floating-panel-header {
        flex-basis: 44px;
        padding-inline: 8px;
    }

    .panel-subtitle,
    .header-grip {
        display: none;
    }

    .window-action {
        width: 30px;
        height: 30px;
    }
}

@media (max-width: 768px) {
    .floating-panel-launcher {
        right: 12px;
        left: auto !important;
        top: auto;
        bottom: 12px;
        width: min(260px, calc(100% - 24px));
        min-height: 50px;
        flex-direction: row;
        border-radius: var(--radius-full);
        border-right: 1px solid var(--border-active);
        transform: none;
    }

    .floating-panel-launcher:hover,
    .floating-panel-launcher:active,
    .floating-panel-launcher.is-left-launcher:hover,
    .floating-panel-launcher.is-left-launcher:active {
        transform: scale(0.98);
    }

    .launcher-label {
        writing-mode: horizontal-tb;
    }
}

@media (prefers-reduced-motion: reduce) {
    .floating-panel-launcher,
    .floating-panel-window,
    .window-action {
        animation: none !important;
        transition: none !important;
    }
}
</style>
