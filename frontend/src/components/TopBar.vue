<template>
    <div class="top-bar">
        <div class="branding">
            <a href="../index.html" class="logo-link">
                <img :src="`${normalizedBase}images/icon.webp`" alt="GeoMoss" class="logo-icon" />
                <span class="title-text">GeoMoss</span>
            </a>
        </div>

        <div class="controls">
            <div class="menu-host" ref="menuHostRef">
                <button class="nav-btn" @click="toggleToolMenu" title="菜单项">
                    <span class="btn-icon">
                        <list-icon :size="18" :stroke-width="2" />
                    </span>
                    <span class="btn-text">菜单</span>
                </button>
                <div v-if="showToolMenu" class="floating-menu">
                    <button class="menu-item" @click="handleOpenToolbox">
                        <layers-icon :size="16" class="m-icon" /> 图层管理
                    </button>
                    <button class="menu-item" @click="handleOpenBusPlanner">
                        <bus-icon :size="16" class="m-icon" /> 公交规划
                    </button>
                    <button class="menu-item" @click="handleOpenDrivePlanner">
                        <car-icon :size="16" class="m-icon" /> 驾车规划
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item" @click="handleSoup" title="来点鸡汤">
                        <smile-icon :size="16" class="m-icon" /> 鸡汤
                    </button>
                </div>
            </div>

            <button class="nav-btn" @click="handleShareView" title="分享当前视角">
                <span class="btn-icon">
                    <share-2-icon :size="18" :stroke-width="1.8" />
                </span>
                <span class="btn-text">分享</span>
            </button>

            <button class="nav-btn" @click="handleOpenWeather" title="天气看板">
                <span class="btn-icon">
                    <CloudSunIcon :size="18" :stroke-width="2" />
                </span>
                <span class="btn-text">天气</span>
            </button>

            <button class="nav-btn" @click="handleOpenNews" title="热点资讯">
                <span class="btn-icon">
                    <newspaper-icon :size="18" :stroke-width="2" />
                </span>
                <span class="btn-text">资讯</span>
            </button>

            <button class="nav-btn" @click="handleOpenChat" title="AI 助手">
                <span class="btn-icon">
                    <bot-icon :size="20" :stroke-width="2" />
                </span>
                <span class="btn-text">AI 助手</span>
            </button>

            <button class="nav-btn" @click="handleToggleAccountCenter" title="用户中心">
                <span class="btn-icon">
                    <user-icon :size="18" :stroke-width="2" />
                </span>
                <span class="btn-text">用户中心</span>
            </button>

                <button class="nav-btn theme-toggle-btn" @click="handleToggleTheme" :title="themeButtonTitle">
                <span class="theme-toggle-track" aria-hidden="true">
                    <span class="theme-toggle-thumb" :class="{ 'is-light': theme === 'light' }"></span>
                </span>
                <span class="btn-icon">
                    <component :is="theme === 'dark' ? SunIcon : MoonIcon" :size="18" :stroke-width="2" />
                </span>
                <span class="btn-text">{{ theme === 'dark' ? '白色' : '黑色' }}</span>
            </button>

            <div class="menu-host" ref="magicMenuHostRef">
                <button class="nav-btn magic-btn" @click="toggleMagicMenu" title="魔法特效选项">
                    <span class="btn-icon">
                        <sparkles-icon :size="18" :stroke-width="2" />
                    </span>
                    <span class="btn-text">特效</span>
                </button>
                <div v-if="showMagicMenu" class="floating-menu">
                    <button class="menu-item" @click="handleActivateMagic('fluid')">
                        <wind-icon :size="16" class="m-icon" /> 流体烟雾
                    </button>
                    <button class="menu-item" @click="handleActivateMagic('gravity')">
                        <orbit-icon :size="16" class="m-icon" /> 引力场
                    </button>
                    <button class="menu-item" @click="handleActivateMagic('void')">
                        <aperture-icon :size="16" class="m-icon" /> 维度塌陷
                    </button>
                    <button class="menu-item" @click="handleActivateMagic('wave')">
                        <waves-icon :size="16" class="m-icon" /> 量子波
                    </button>
                    <button class="menu-item highlight-magic" @click="handleActivateMagic('singularity')">
                        <circle-dot-icon :size="16" class="m-icon" /> 黑洞引力
                    </button>
                    <div class="menu-divider"></div>
                    <button class="menu-item magic-close-btn" @click="handleActivateMagic('off')">
                        <circle-x-icon :size="16" class="m-icon" /> 关闭特效
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useMessage } from '../composables/useMessage';
import { DEFAULT_BASEMAP_LAYER_INDEX } from '../constants';
// import { hideLoading, showLoading } from '@/utils';
import {
    List as ListIcon,
    Layers as LayersIcon,
    Bus as BusIcon,
    Car as CarIcon,
    Smile as SmileIcon,
    Share2 as Share2Icon,
    Bot as BotIcon,
    Sparkles as SparklesIcon,
    Wind as WindIcon,
    Orbit as OrbitIcon,
    Aperture as ApertureIcon,
    Waves as WavesIcon,
    CircleDot as CircleDotIcon,
    CircleX as CircleXIcon,
    User as UserIcon,
    Moon as MoonIcon,
    Sun as SunIcon,
    CloudSun as CloudSunIcon,
    Newspaper as NewspaperIcon
} from 'lucide-vue-next';

const themeButtonTitle = computed(() => props.theme === 'dark' ? '切换白色主题' : '切换黑色主题');

const props = defineProps({
    theme: {
        type: String,
        default: 'dark',
        validator: (value) => ['dark', 'light'].includes(value)
    }
});

const emit = defineEmits([
    'toggle-magic',
    'activate-magic', // 发送特定的魔法特效
    'open-chat',
    'open-toolbox',
    'open-bus',
    'open-drive',
    'activate-feature',
    'toggle-account-center',
    'toggle-theme',
    'open-weather',
    'open-news'
]);

const showToolMenu = ref(false);
const showMagicMenu = ref(false);
const menuHostRef = ref(null);
const magicMenuHostRef = ref(null);

const baseUrl = import.meta.env.BASE_URL || '/';
const normalizedBase = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`;

const message = useMessage();

function handleOpenToolbox() {
    showToolMenu.value = false;
    emit('activate-feature', { key: 'toolbox', label: '工具箱' });
    emit('open-toolbox');
}

function handleOpenBusPlanner() {
    showToolMenu.value = false;
    emit('activate-feature', { key: 'bus', label: '公交规划' });
    emit('open-bus');
}

function handleOpenDrivePlanner() {
    showToolMenu.value = false;
    emit('activate-feature', { key: 'drive', label: '驾车规划' });
    emit('open-drive');
}

function handleOpenChat() {
    emit('activate-feature', { key: 'chat', label: 'AI助手' });
    emit('open-chat');
}

function handleOpenWeather() {
    emit('open-weather');
}

function handleOpenNews() {
    emit('activate-feature', { key: 'info', label: '新闻' });
    emit('open-news');
}

function handleToggleAccountCenter() {
    emit('toggle-account-center');
}

function handleToggleTheme() {
    emit('toggle-theme');
}

function toggleMagicMenu() {
    showMagicMenu.value = !showMagicMenu.value;
    showToolMenu.value = false;
}

function handleActivateMagic(effectName) {
    showMagicMenu.value = false;
    emit('activate-feature', { key: 'magic', label: '特效' });
    emit('activate-magic', effectName);
}

function toggleToolMenu() {
    showToolMenu.value = !showToolMenu.value;
    showMagicMenu.value = false;
}
function handleSoup() {
    showToolMenu.value = false;
    message.soup();
}

function handleDocumentClick(event) {
    if (showToolMenu.value && !menuHostRef.value?.contains(event.target)) {
        showToolMenu.value = false;
    }
    if (showMagicMenu.value && !magicMenuHostRef.value?.contains(event.target)) {
        showMagicMenu.value = false;
    }
}

function canUseNativeShare() {
    if (typeof navigator === 'undefined' || typeof navigator.share !== 'function') return false;
    const ua = navigator.userAgent || '';
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile/i.test(ua);
}

function fallbackCopyViaExecCommand(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);

    const selection = window.getSelection();
    const originalRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;

    textarea.select();

    let succeeded = false;
    try {
        succeeded = document.execCommand('copy');
    } catch (e) {
        succeeded = false;
    }

    document.body.removeChild(textarea);

    if (originalRange && selection) {
        selection.removeAllRanges();
        selection.addRange(originalRange);
    }

    if (!succeeded) {
        throw new Error('execCommand copy failed');
    }
}

function normalizeBinaryFlag(value, fallback = '0') {
    const text = String(value ?? '').trim().toLowerCase();
    if (text === '1' || text === 'true') return '1';
    if (text === '0' || text === 'false') return '0';
    return fallback === '1' ? '1' : '0';
}

function normalizeLayerIndex(value, fallback = DEFAULT_BASEMAP_LAYER_INDEX) {
    const parsed = Number(String(value ?? '').trim());
    if (Number.isInteger(parsed) && parsed >= 0) return String(parsed);

    const fallbackParsed = Number(fallback);
    if (Number.isInteger(fallbackParsed) && fallbackParsed >= 0) return String(fallbackParsed);
    return String(DEFAULT_BASEMAP_LAYER_INDEX);
}

function normalizePositionCode(value, fallback = '0') {
    const text = String(value ?? '').trim();
    if (text) return text;
    return String(fallback ?? '0');
}

function resolvePositionCodeForShare(hashParams, searchParams) {
    const hashCode = normalizePositionCode(hashParams?.get('p'), '');
    if (hashCode) return hashCode;

    const searchCode = normalizePositionCode(searchParams?.get('p'), '');
    if (searchCode) return searchCode;

    return '0';
}

function extractPositionCodeFromText(rawHref) {
    const text = String(rawHref || '');
    const match = text.match(/[?#&]p=([^&#]*)/i);
    if (!match) return '0';

    try {
        return normalizePositionCode(decodeURIComponent(match[1] || ''), '0');
    } catch {
        return normalizePositionCode(match[1] || '', '0');
    }
}

function syncShareFlagInCurrentUrl() {
    if (typeof window === 'undefined') return;

    try {
        const hash = String(window.location.hash || '#/home');
        const hashWithoutSharp = hash.startsWith('#') ? hash.slice(1) : hash;
        const [hashPathRaw, hashQueryRaw = ''] = hashWithoutSharp.split('?');
        const hashPath = hashPathRaw || '/home';
        const hashParams = new URLSearchParams(hashQueryRaw);
        const searchParams = new URLSearchParams(String(window.location.search || '').replace(/^\?/, ''));

        hashParams.delete('from');
        hashParams.delete('shared');
        hashParams.set('s', '1');
        hashParams.set('loc', normalizeBinaryFlag(hashParams.get('loc'), '0'));
        hashParams.set('p', resolvePositionCodeForShare(hashParams, searchParams));
        hashParams.set('l', normalizeLayerIndex(hashParams.get('l') ?? hashParams.get('layer'), DEFAULT_BASEMAP_LAYER_INDEX));
        hashParams.delete('layer');

        const nextHashQuery = hashParams.toString();
        const normalizedHashPath = hashPath.startsWith('/') ? hashPath : `/${hashPath}`;
        const nextHash = nextHashQuery
            ? `#${normalizedHashPath}?${nextHashQuery}`
            : `#${normalizedHashPath}`;
        const nextUrl = `${window.location.pathname}${window.location.search}${nextHash}`;

        window.history.replaceState(window.history.state, '', nextUrl);
    } catch {
        // Ignore URL update failures to keep share flow unaffected.
    }
}

function buildShareMarkedUrl(rawHref) {
    try {
        const url = new URL(rawHref, window.location.origin);
        const hashText = String(url.hash || '');
        const hashWithoutSharp = hashText.startsWith('#') ? hashText.slice(1) : hashText;
        const [hashPathRaw, hashQueryRaw = ''] = hashWithoutSharp.split('?');
        const hashPath = hashPathRaw || '/home';
        const hashParams = new URLSearchParams(hashQueryRaw);

        // 标记该链接来自“分享”入口，供启动流程识别。
        hashParams.delete('from');
        hashParams.delete('shared');
        hashParams.set('s', '1');
        hashParams.set('loc', '0');
        hashParams.set('p', resolvePositionCodeForShare(hashParams, url.searchParams));
        hashParams.set('l', normalizeLayerIndex(hashParams.get('l') ?? hashParams.get('layer'), DEFAULT_BASEMAP_LAYER_INDEX));
        hashParams.delete('layer');

        const nextHashQuery = hashParams.toString();
        const normalizedHashPath = hashPath.startsWith('/') ? hashPath : `/${hashPath}`;
        url.hash = nextHashQuery ? `${normalizedHashPath}?${nextHashQuery}` : normalizedHashPath;
        return url.toString();
    } catch {
        const text = String(rawHref || '');
        const pCode = extractPositionCodeFromText(text);
        return text.includes('?')
            ? `${text}&s=1&loc=0&p=${encodeURIComponent(pCode)}&l=${DEFAULT_BASEMAP_LAYER_INDEX}`
            : `${text}?s=1&loc=0&p=${encodeURIComponent(pCode)}&l=${DEFAULT_BASEMAP_LAYER_INDEX}`;
    }
}

async function handleShareView() {
    const url = buildShareMarkedUrl(window.location.href);
    // showLoading('正在准备分享链接...');
    try {
        if (canUseNativeShare()) {
            await navigator.share({
                title: 'GeoMoss WebGIS 视角',
                text: '分享当前地图视角链接',
                url
            });
            syncShareFlagInCurrentUrl();
            message.success('已唤起系统分享面板');
            return;
        }
    } catch (error) {
        if (error && (error.name === 'AbortError' || error.name === 'NotAllowedError')) {
            return;
        }
        // 其他错误则回退到剪贴板逻辑
    }

    try {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            await navigator.clipboard.writeText(url);
        } else {
            fallbackCopyViaExecCommand(url);
        }
        syncShareFlagInCurrentUrl();
        message.success('视角链接已复制，快去分享吧！');
    } catch (error) {
        message.error('分享链接复制失败', error);
        message.error('复制失败，请手动从地址栏复制链接');
    }
}

onMounted(() => {
    document.addEventListener('click', handleDocumentClick);
});

onBeforeUnmount(() => {
    document.removeEventListener('click', handleDocumentClick);
});
</script>

<style scoped>
.m-icon { margin-right: 8px; vertical-align: middle; }

.top-bar {
  width: 100%;
  height: 56px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  background: rgba(10, 18, 16, 0.84);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-bottom: 1px solid var(--border-subtle);
  box-shadow: 0 1px 0 var(--border-subtle), 0 10px 28px rgba(0, 0, 0, 0.28);
  z-index: 2000;
  position: relative;
}

:root[data-theme="light"] .top-bar {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.78), rgba(255, 255, 255, 0.58)),
    var(--glass-bg-heavy);
  box-shadow: 0 12px 34px rgba(49, 86, 64, 0.12), inset 0 -1px 0 var(--border-subtle);
}

.branding {
  flex: 0 1 auto;
  min-width: 0;
}

.logo-link {
  display: flex;
  align-items: center;
  text-decoration: none;
  color: var(--text-primary);
  gap: 11px;
  min-width: 0;
}
.logo-link:hover { opacity: 0.9; }

.logo-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
  filter: drop-shadow(0 0 8px rgba(71, 215, 198, 0.28));
  transition: transform var(--duration-normal) var(--ease-spring-subtle);
}
.logo-link:hover .logo-icon {
  transform: rotate(-5deg) scale(1.04);
}

.title-text {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
  background: linear-gradient(135deg, var(--text-primary) 0%, var(--neon-cyan) 100%);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  white-space: nowrap;
}

:root[data-theme="light"] .title-text {
  background: linear-gradient(135deg, #1f332b 0%, #6f9a48 52%, #e2ad42 100%);
  background-clip: text;
  -webkit-background-clip: text;
}

.controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  min-width: 0;
}

.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-text {
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 400;
}

.menu-host { position: relative; }

.floating-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 10px);
  min-width: 210px;
  background:
    linear-gradient(180deg, var(--surface-card-strong), var(--glass-bg-heavy));
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-elevated);
  border: 1px solid var(--border-subtle);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  padding: 6px;
  z-index: 2200;
  overflow: hidden;
  animation: menuIn var(--duration-panel) var(--ease-spring-subtle);
  transform-origin: top right;
}
@keyframes menuIn {
  from { opacity: 0; transform: translateY(-10px) scale(0.94); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

.menu-divider {
  height: 1px;
  margin: var(--space-xs) var(--space-sm);
  background: var(--border-subtle);
}

.menu-group-title {
  padding: var(--space-xs) 12px var(--space-xs);
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0;
}

.menu-item {
  width: 100%;
  border: none;
  text-align: left;
  background: transparent;
  border-radius: var(--radius-sm);
  min-height: 40px;
  padding: 9px 12px;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 400;
  display: flex;
  align-items: center;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    color var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
}
.menu-item:hover {
  background: var(--neon-cyan-dim);
  color: var(--text-primary);
  transform: translateX(2px);
}

.menu-item-icon { opacity: 0.85; }
.menu-item-label { min-width: 0; }

.nav-btn {
  background: var(--surface-1);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  min-height: 40px;
  padding: 8px 14px;
  border-radius: var(--radius-full);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: var(--font-size-sm);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
  white-space: nowrap;
  backdrop-filter: blur(8px);
}
.nav-btn:hover {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  box-shadow: var(--neon-cyan-glow);
  background: var(--surface-hover);
}
.nav-btn:active { transform: scale(0.97); }

.magic-btn:hover {
    background: var(--accent-amber-dim);
    border-color: rgba(240, 179, 90, 0.38);
    color: var(--accent-amber);
}

.theme-toggle-btn {
    min-width: 112px;
    padding-left: 8px;
    justify-content: center;
    background: linear-gradient(135deg, var(--surface-1), var(--surface-0));
}

.theme-toggle-track {
    position: relative;
    width: 30px;
    height: 18px;
    border-radius: var(--radius-full);
    background: var(--surface-card-strong);
    border: 1px solid var(--border-subtle);
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.28);
}

.theme-toggle-thumb {
    position: absolute;
    left: 3px;
    top: 3px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent-amber);
    box-shadow: 0 0 8px rgba(240, 179, 90, 0.48);
    transition: transform var(--duration-normal) var(--ease-spring-subtle), background-color var(--duration-fast) var(--ease-spatial);
}

.theme-toggle-thumb.is-light {
    transform: translateX(12px);
    background: var(--neon-cyan);
    box-shadow: 0 0 8px rgba(47, 143, 127, 0.38);
}

.theme-toggle-btn:hover {
    color: var(--accent-amber);
    border-color: rgba(240, 179, 90, 0.42);
    background: var(--accent-amber-dim);
}

:root[data-theme="light"] .theme-toggle-btn:hover {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
}

.account-btn {
    background: var(--surface-1);
    border-color: var(--border-subtle);
}

.account-btn:hover {
    background: var(--neon-green-dim);
    border-color: rgba(139, 209, 124, 0.42);
    color: var(--neon-green);
}

.highlight-magic {
    color: var(--accent-amber);
    font-weight: bold;
}

.highlight-magic:hover {
    background: var(--accent-amber-dim) !important;
}

.magic-close-btn {
    color: var(--accent-rose);
}

.magic-close-btn:hover {
    background: var(--accent-rose-dim) !important;
}

@media (max-width: 768px) {
    .logo-icon {
        height: 30px;
        width: 30px;
    }

    .top-bar {
        padding: 0 10px;
        gap: 8px;
    }

    .title-text {
        font-size: 15px;
        max-width: 38vw;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .controls {
        gap: 6px;
    }

    .nav-btn {
        padding: 7px;
        min-width: 40px;
        justify-content: center;
    }

    .theme-toggle-btn {
        min-width: 40px;
    }

    .theme-toggle-track {
        display: none;
    }

    .btn-text {
        display: none;
    }

    .btn-icon {
        font-size: 17px;
    }
}
</style>
