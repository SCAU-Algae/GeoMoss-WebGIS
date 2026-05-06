<template>
    <div class="map-controls-group modern-glass">
        <div class="coordinate-section" ref="coordinateSectionRef">
            <!-- <svg id="map-marker-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" style="margin: 0 10px;">
                <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
            </svg> -->

            <div
                class="coordinate-display"
                :class="{ editing: isCoordinateEditing, invalid: isInputInvalid }"
                @mouseenter="isCoordinateHover = true"
                @mouseleave="isCoordinateHover = false"
                @click="startCoordinateInput"
                title="单击输入经纬度并回车跳转"
            >
                <template v-if="!isCoordinateEditing">
                    <span class="coordinate-text">{{ displayCoordinateText }}</span>
                    <div class="coordinate-actions">
                        <button
                            v-if="isCoordinateHover && canCopyCoordinate"
                            class="copy-coordinate-btn"
                            type="button"
                            title="复制坐标"
                            @click.stop="copyCurrentCoordinate"
                        >
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <rect x="9" y="9" width="11" height="11" rx="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                            <span class="copy-tooltip">{{ copyTooltipText }}</span>
                        </button>
                        <button
                            class="format-config-btn"
                            type="button"
                            title="坐标格式设置"
                            @click.stop="toggleFormatMenu"
                        >
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                <polyline points="9 18 15 12 9 6"></polyline>
                            </svg>
                        </button>
                    </div>
                </template>
                <input
                    v-else
                    ref="coordinateInputRef"
                    v-model="coordinateInputValue"
                    class="coordinate-input"
                    type="text"
                    placeholder="114.302E, 34.814N 或 114°18'08.64&quot;E, 34°48'52.56&quot;N"
                    @click.stop
                    @input="isInputInvalid = false"
                    @keydown.enter.prevent="submitCoordinateInput"
                    @keydown.esc.prevent="cancelCoordinateInput"
                    @blur="cancelCoordinateInput"
                />
            </div>

            <!-- 格式配置菜单 -->
            <div v-if="isFormatMenuVisible" class="format-menu">
                <div class="format-menu-content">
                    <div class="menu-section">
                        <div class="menu-label">显示格式</div>
                        <div class="format-options">
                            <button
                                v-for="fmt in Object.values(COORDINATE_FORMATS)"
                                :key="fmt.id"
                                class="format-option"
                                :class="{ active: currentFormatId === fmt.id }"
                                @click="selectFormat(fmt.id)"
                            >
                                <span class="format-label">{{ fmt.label }}</span>
                                <span class="format-example">{{ fmt.example }}</span>
                            </button>
                        </div>
                    </div>

                    <div class="menu-divider"></div>

                    <div class="menu-section">
                        <div class="menu-label">小数位数</div>
                        <div class="decimal-options">
                            <button
                                v-for="(config, places) in DECIMAL_PLACES"
                                :key="places"
                                class="decimal-option"
                                :class="{ active: currentDecimalPlaces === Number(places) }"
                                @click="selectDecimalPlaces(Number(places))"
                            >
                                {{ config.label }}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="zoom-level-display" title="当前缩放级别">{{ currentZoom }}</div>
        <div class="divider"></div>
        <button
            class="home-btn"
            :class="{ rippling: homeButtonRippling }"
            @click="handleHomeInteract"
            title="单击复位 / 双击定位"
            type="button"
        >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M3 10.5 12 3l9 7.5"></path>
                <path d="M5 9.8V20h14V9.8"></path>
                <path d="M10 20v-6h4v6"></path>
            </svg>
        </button>
    </div>
</template>

<script setup>
/**
 * MapControlsBar 组件
 * 地图底部右侧控制条，显示实时坐标、缩放级别、复制/编辑坐标、主页按钮
 * 功能：
 * - 实时坐标显示和编辑（支持多种格式）
 * - 坐标复制到剪贴板
 * - 缩放级别显示
 * - 主页按钮（单击重置、双击定位用户）
 * - 格式配置菜单（选择显示格式、小数位数）
 * - 完整的生命周期管理和计时器清理
 */

import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue';
import {
  COORDINATE_FORMATS,
  DECIMAL_PLACES,
  formatCoordinate,
    parseCoordinate,
    normalizeCoordinate
} from '../utils/biz';
import { useMessage } from '../composables/useMessage';
const message = useMessage();

// ========== 常量定义 ==========
/** 坐标占位符，用于显示无效坐标时的默认文本 */
const COORDINATE_PLACEHOLDER = 'Lon, Lat';

/** 本地存储的键名 */
const STORAGE_KEYS = {
  FORMAT_ID: 'gis_coord_format_id',
  DECIMAL_PLACES: 'gis_coord_decimal_places'
};

// ========== 默认坐标格式配置 ==========
const DEFAULT_FORMAT_ID = 'format_3'; 
const DEFAULT_DECIMAL_PLACES = 6;

// ========== 组件 Props 定义 ==========
/**
 * @prop {String} coordinateText - 当前坐标文本（格式："lng, lat"）
 * @prop {Object|null} coordinate - 原始坐标对象 { lng, lat }，组件内部负责格式化
 * @prop {Number|String} currentZoom - 当前地图缩放级别（0-22）
 */
const props = defineProps({
    coordinate: {
        type: Object,
        default: null
    },
    coordinateText: {
        type: String,
        default: COORDINATE_PLACEHOLDER
    },
    currentZoom: {
        type: [Number, String],
        default: '--'
    }
});

// ========== 组件 Emits 定义 ==========
/**
 * @emit reset-view - 重置地图视图（单击主页按钮）
 * @emit locate-me - 定位到用户位置（双击主页按钮）
 * @emit jump-to - 跳转到指定坐标 { lng, lat }
 */
const emit = defineEmits([
    'reset-view',
    'locate-me',
    'jump-to'
]);

// ========== 状态变量 ==========
const coordinateInputRef = ref(null);                  // 坐标输入框 ref
const coordinateSectionRef = ref(null);                // 坐标区容器 ref，用于关闭浮层
const coordinateInputValue = ref('');                  // 坐标输入框当前值
const isCoordinateHover = ref(false);                  // 坐标区是否 hover
const isCoordinateEditing = ref(false);                // 是否处于坐标编辑模式
const isInputInvalid = ref(false);                     // 坐标输入是否有效
const copyTooltipText = ref('Copy');                   // 复制按钮提示文本
const homeButtonRippling = ref(false);                 // 主页按钮是否显示涟漪效果
const isFormatMenuVisible = ref(false);                // 格式菜单是否显示
const currentFormatId = ref(DEFAULT_FORMAT_ID);        // 当前坐标格式ID
const currentDecimalPlaces = ref(DEFAULT_DECIMAL_PLACES); // 当前小数位数

// ========== 计时器变量 ==========
let homeClickTimer = null;        // 主页按钮点击检测计时器（用于双击检测）
let homeRippleTimer = null;       // 主页按钮涟漪效果计时器
let copyTooltipTimer = null;      // 复制提示文本重置计时器
let handleClickOutside = null;    // 全局点击监听

// ========== 计算属性 ==========
/** 显示的坐标文本（使用选定的格式） */
const displayCoordinateText = computed(() => {
  const lng = Number(props.coordinate?.lng);
  const lat = Number(props.coordinate?.lat);
  if (Number.isFinite(lng) && Number.isFinite(lat)) {
    return formatCoordinate(lng, lat, currentFormatId.value, currentDecimalPlaces.value);
  }

  const text = String(props.coordinateText || '').trim();
  return text || COORDINATE_PLACEHOLDER;
});

/** 是否可以复制坐标（坐标有效时） */
const canCopyCoordinate = computed(() => displayCoordinateText.value !== COORDINATE_PLACEHOLDER);

// ========== 坐标编辑函数 ==========

/**
 * 开始坐标编辑模式 - 显示输入框，自动选中现有坐标
 */
function startCoordinateInput() {
    if (isCoordinateEditing.value) return;
    isInputInvalid.value = false;
    isCoordinateEditing.value = true;
    coordinateInputValue.value = canCopyCoordinate.value ? displayCoordinateText.value : '';
    nextTick(() => {
        coordinateInputRef.value?.focus?.();
        coordinateInputRef.value?.select?.();
    });
}

/**
 * 取消坐标编辑 - 退出编辑模式，清除错误提示
 */
function cancelCoordinateInput() {
    isCoordinateEditing.value = false;
    isInputInvalid.value = false;
}

/**
 * 解析用户输入的坐标字符串
 * 支持多种格式自动识别：
 * - 纯十进制: 114.302, 34.814
 * - 带方向: 114.302E, 34.814N 或 34.814N, 114.302E
 * - 度分秒: 114°18'08.64"E, 34°48'52.56"N
 * - 支持中文逗号分隔
 * 
 * 对于纯十进制格式，按照当前选择的显示格式来判断顺序：
 * - format_1, format_3, format_5：经度在前
 * - format_2, format_4, format_6：纬度在前
 * 
 * @param {String} rawText - 原始输入文本
 * @returns {Object|null} { lng, lat } 或 null（解析失败）
 */
function parseCoordinateInput(rawText) {
  // 传入当前格式 ID，让 parseCoordinate 根据格式判断顺序
  const parsed = parseCoordinate(rawText, currentFormatId.value);
  if (!parsed) return null;

  // 规范化坐标
  const normalized = normalizeCoordinate(parsed.lng, parsed.lat);
  return normalized;
}

/**
 * 提交坐标输入 - 解析坐标并触发跳转事件
 */
function submitCoordinateInput() {
    const parsed = parseCoordinateInput(coordinateInputValue.value);
    if (!parsed) {
        isInputInvalid.value = true;
        return;
    }

    isCoordinateEditing.value = false;
    isInputInvalid.value = false;
    emit('jump-to', parsed);
}

/**
 * 复制当前坐标到剪贴板
 * 优先使用 Clipboard API，回退到 execCommand（兼容老式浏览器或非 HTTPS 环境）
 */
const copyCurrentCoordinate = async () => {
    // 1. 检查是否允许复制以及文本是否存在
    if (!canCopyCoordinate.value || !displayCoordinateText.value) return;
    
    const textToCopy = displayCoordinateText.value;

    try {
        // 只有在支持 navigator.clipboard 且处于安全上下文(HTTPS/Localhost)时才可用
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(textToCopy);
            message.success('坐标已复制到剪贴板');
        } else {
            // 如果不支持 API，手动抛错进入 catch 执行回退逻辑
            throw new Error('Clipboard API unavailable');
        }
    } catch (error) {
        // ========== 回退逻辑 (Fallback) ==========
        const fallbackInput = document.createElement('textarea');
        fallbackInput.value = textToCopy;
        
        // 确保 textarea 在页面上不可见但可操作
        fallbackInput.style.position = 'fixed';
        fallbackInput.style.left = '-9999px';
        fallbackInput.style.top = '0';
        fallbackInput.style.opacity = '0';
        
        document.body.appendChild(fallbackInput);
        fallbackInput.focus();
        fallbackInput.select();
        
        try {
            document.execCommand('copy');
        } catch (err) {
            message.error('无法执行复制命令:', err);
        }
        
        document.body.removeChild(fallbackInput);
    }

    // ========== UI 反馈逻辑 (Tooltip) ==========
    copyTooltipText.value = 'Copied';

    // 清除已有的定时器，防止快速多次点击导致的显示冲突
    if (copyTooltipTimer) {
        clearTimeout(copyTooltipTimer);
    }

    copyTooltipTimer = setTimeout(() => {
        copyTooltipText.value = 'Copy';
        copyTooltipTimer = null;
    }, 900);
};

/**
 * 触发主页按钮涟漪效果 - 根据点击位置动态显示
 */
function triggerHomeRipple(event) {
    const target = event?.currentTarget;
    if (target?.style) {
        const rect = target.getBoundingClientRect();
        const x = (event.clientX ?? rect.width / 2) - rect.left;
        const y = (event.clientY ?? rect.height / 2) - rect.top;
        target.style.setProperty('--ripple-x', `${x}px`);
        target.style.setProperty('--ripple-y', `${y}px`);
    }

    homeButtonRippling.value = false;
    if (homeRippleTimer) {
        clearTimeout(homeRippleTimer);
    }

    homeRippleTimer = setTimeout(() => {
        homeButtonRippling.value = true;
        homeRippleTimer = setTimeout(() => {
            homeButtonRippling.value = false;
            homeRippleTimer = null;
        }, 420);
    }, 0);
}

/**
 * 主页按钮交互处理 - 单击/双击检测
 * 单击（280ms）：重置地图视图
 * 双击（280ms内两次）：定位到用户位置
 */
function handleHomeInteract(event) {
    triggerHomeRipple(event);

    if (homeClickTimer) {
        clearTimeout(homeClickTimer);
        homeClickTimer = null;
        emit('locate-me');
        return;
    }

    homeClickTimer = setTimeout(() => {
        emit('reset-view');
        homeClickTimer = null;
    }, 280);
}

/**
 * 从 localStorage 加载坐标格式配置
 */
function loadFormatPreferences() {
  try {
    const savedFormatId = localStorage.getItem(STORAGE_KEYS.FORMAT_ID);
    const savedDecimalPlaces = localStorage.getItem(STORAGE_KEYS.DECIMAL_PLACES);
    
    if (savedFormatId && COORDINATE_FORMATS[savedFormatId]) {
      currentFormatId.value = savedFormatId;
    }
    
    if (savedDecimalPlaces) {
      const places = Number(savedDecimalPlaces);
      if (DECIMAL_PLACES[places]) {
        currentDecimalPlaces.value = places;
      }
    }
  } catch {}
}

/**
 * 保存坐标格式配置到 localStorage
 */
function saveFormatPreferences() {
  try {
    localStorage.setItem(STORAGE_KEYS.FORMAT_ID, currentFormatId.value);
    localStorage.setItem(STORAGE_KEYS.DECIMAL_PLACES, String(currentDecimalPlaces.value));
  } catch {}
}

/**
 * 打开/关闭格式配置菜单
 */
function toggleFormatMenu() {
  isFormatMenuVisible.value = !isFormatMenuVisible.value;
}

/**
 * 关闭格式配置菜单
 */
function closeFormatMenu() {
  isFormatMenuVisible.value = false;
}

/**
 * 选择格式
 */
function selectFormat(formatId) {
  currentFormatId.value = formatId;
  saveFormatPreferences();
  closeFormatMenu();
}

/**
 * 选择小数位数
 */
function selectDecimalPlaces(places) {
  currentDecimalPlaces.value = places;
  saveFormatPreferences();
}

/**
 * 组件挂载时加载保存的配置
 */
onMounted(() => {
  loadFormatPreferences();

  handleClickOutside = (event) => {
    if (!isFormatMenuVisible.value) return;
    const target = event?.target;
    if (target instanceof Node && coordinateSectionRef.value?.contains(target)) return;
    closeFormatMenu();
  };

  document.addEventListener('click', handleClickOutside);
});

/**
 * 组件卸载时清理所有计时器 - 防止内存泄漏
 */
onUnmounted(() => {
    if (handleClickOutside) {
        document.removeEventListener('click', handleClickOutside);
        handleClickOutside = null;
    }
    if (homeClickTimer) {
        clearTimeout(homeClickTimer);
        homeClickTimer = null;
    }
    if (homeRippleTimer) {
        clearTimeout(homeRippleTimer);
        homeRippleTimer = null;
    }
    if (copyTooltipTimer) {
        clearTimeout(copyTooltipTimer);
        copyTooltipTimer = null;
    }
    closeFormatMenu();
});
</script>

<style scoped>
.map-controls-group {
    --glass-text: var(--text-primary);
    --glass-chip-bg: rgba(71, 215, 198, 0.12);
    --recessed-bg: rgba(5, 11, 10, 0.44);
    --glass-divider: var(--border-subtle);
    --trans-curve: var(--ease-spatial);
    
    position: absolute;
    right: 8px;
    bottom: 8px;
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: 10px;
    /* padding: 8px 10px; */
    border-radius: 9999px;
    color: var(--glass-text);
    white-space: nowrap;
    transition: transform var(--duration-normal) var(--ease-panel),
        border-color var(--duration-fast) var(--ease-spatial),
        background var(--duration-normal) var(--ease-spatial),
        box-shadow var(--duration-normal) var(--ease-spatial);
    
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    box-shadow: var(--shadow-panel);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
}

.modern-glass {
    /* Kept for compatibility if still conditionally used, but merged above */
}

.coordinate-display {
    min-width: 260px;
    height: 38px;
    padding: 0 10px 0 14px;
    border-radius: 9999px;
    border: 1px solid transparent;
    background: var(--recessed-bg);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    cursor: text;
    transition: all var(--duration-normal) var(--trans-curve);
}

.coordinate-display:hover {
    background: rgba(71, 215, 198, 0.1);
    border-color: var(--border-active);
}

.coordinate-display.editing {
    background: rgba(5, 11, 10, 0.82);
    border: 1px solid var(--border-glow);
    box-shadow: 0 0 0 3px rgba(71, 215, 198, 0.11);
}

.coordinate-display.invalid {
    box-shadow: inset 0 0 0 1px rgba(254, 202, 202, 0.85);
    border-color: rgba(254, 202, 202, 0.85);
}

.coordinate-section {
    position: relative;
    display: flex;
    align-items: center;
}

.coordinate-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

.coordinate-text {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: 0;
    text-shadow: 0 0 8px rgba(71, 215, 198, 0.14);
}

.coordinate-display.editing .coordinate-input {
    color: var(--text-primary);
}

.copy-coordinate-btn {
    height: 24px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid var(--border-subtle);
    background: rgba(71, 215, 198, 0.08);
    color: var(--glass-text);
    border-radius: 9999px;
    padding: 0 8px;
    font-size: 11px;
    cursor: pointer;
    transition: all var(--duration-fast) var(--trans-curve);
}

.copy-coordinate-btn:hover {
    transform: translateY(-1px);
    border-color: var(--border-active);
    background: rgba(71, 215, 198, 0.16);
}

.copy-tooltip {
    line-height: 1;
}

.format-config-btn {
    height: 22px;
    width: 20px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: rgba(71, 215, 198, 0.08);
    color: var(--glass-text);
    border-radius: 50%;
    padding: 0;
    cursor: pointer;
    transition: all var(--duration-fast) var(--trans-curve);
    flex-shrink: 0;
}

.format-config-btn:hover {
    background: rgba(71, 215, 198, 0.16);
    color: var(--neon-cyan);
    transform: translateY(-1px);
}

.format-menu {
    position: absolute;
    bottom: 100%;
    left: 0;
    margin-bottom: 8px;
    z-index: 2000;
    background: var(--glass-bg-heavy);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-elevated);
    backdrop-filter: blur(var(--glass-blur));
    -webkit-backdrop-filter: blur(var(--glass-blur));
    overflow: hidden;
    animation: slideUp var(--duration-normal) var(--ease-panel);
}

@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.format-menu-content {
    padding: 12px;
    min-width: 280px;
    max-height: 420px;
    overflow-y: auto;
}

.menu-section {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.menu-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 0 4px;
}

.format-options {
    display: flex;
    flex-direction: column;
    gap: 6px;
}

.format-option {
    padding: 6px 8px;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    background: transparent;
    cursor: pointer;
    text-align: left;
    transition: all var(--duration-fast) var(--trans-curve);
}

.format-option:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
}

.format-option.active {
    background: var(--neon-cyan-dim);
    border-color: var(--border-glow);
    box-shadow: var(--neon-cyan-glow);
}

.format-label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: var(--neon-cyan);
    margin-bottom: 2px;
}

.format-example {
    display: block;
    font-size: 11px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.menu-divider {
    height: 1px;
    background: var(--border-subtle);
    margin: 8px 0;
}

.decimal-options {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
}

.decimal-option {
    padding: 8px 12px;
    border: 1px solid var(--border-subtle);
    border-radius: 8px;
    background: transparent;
    cursor: pointer;
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    transition: all var(--duration-fast) var(--trans-curve);
}

.decimal-option:hover {
    background: var(--surface-hover);
    border-color: var(--border-active);
}

.decimal-option.active {
    background: var(--neon-cyan-dim);
    border-color: var(--border-glow);
    color: var(--neon-cyan);
    box-shadow: var(--neon-cyan-glow);
}

.coordinate-input {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    color: var(--glass-text);
    font-family: var(--font-mono);
    font-size: 13px;
}

.coordinate-input::placeholder {
    color: var(--text-muted);
}

.zoom-level-display {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: var(--glass-chip-bg);
    color: var(--neon-cyan);
    font-family: var(--font-mono);
    font-size: 15px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.3s var(--trans-curve);
}

.divider {
    width: 2px;
    height: 20px;
    background-color: var(--glass-divider);
    flex-shrink: 0;
}

.home-btn {
    --ripple-x: 50%;
    --ripple-y: 50%;
    width: 38px;
    height: 38px;
    position: relative;
    overflow: hidden;
    border-radius: 50%;
    background: transparent;
    border: none;
    color: var(--text-primary);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all var(--duration-fast) var(--trans-curve);
}

.home-btn::after {
    content: '';
    position: absolute;
    left: var(--ripple-x);
    top: var(--ripple-y);
    width: 10px;
    height: 10px;
    border-radius: 50%;
    transform: translate(-50%, -50%) scale(0);
    background: rgba(71, 215, 198, 0.32);
    opacity: 0;
    pointer-events: none;
}

.home-btn.rippling::after {
    animation: home-button-ripple 0.45s ease-out;
}

.home-btn:hover {
    background: rgba(71, 215, 198, 0.12);
    color: var(--neon-cyan);
}

.home-btn:active {
    transform: scale(0.95);
}

@keyframes home-button-ripple {
    0% {
        opacity: 0.5;
        transform: translate(-50%, -50%) scale(0);
    }
    100% {
        opacity: 0;
        transform: translate(-50%, -50%) scale(10);
    }
}

@media (max-width: 768px) {
    .map-controls-group {
        left: 12px;
        right: 12px;
        bottom: 35px;
        padding: 8px;
        gap: 8px;
    }

    .coordinate-display {
        min-width: 0;
        flex: 1;
    }

    .copy-tooltip {
        display: none;
    }

    .format-menu {
        position: fixed;
        left: 12px;
        right: 12px;
        bottom: 62px;  /* 控制条高度 54px + 间距 8px，菜单显示在上方 */
        top: auto;
        max-width: none;
        max-height: 50vh;
    }

    .format-menu-content {
        min-width: unset;
    }

    .decimal-options {
        grid-template-columns: 1fr 1fr 1fr;
    }
}
</style>
