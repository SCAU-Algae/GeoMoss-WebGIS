<template>
    <div ref="panelRef" class="weather-panel" :class="{ 'wx-fullscreen': wxExpanded }">
        <div class="weather-toolbar">
            <div class="weather-toolbar-left">
                <h2 class="weather-title">GeoMoss 天气看板</h2>
                <p class="weather-subtitle">Open-Meteo 免费天气 · 点击地图任意位置即查</p>
            </div>
            <div class="weather-toolbar-right">
                <button class="toolbar-btn" :disabled="isBusy" @click="refreshWeather">
                    {{ isBusy ? '刷新中...' : '刷新天气' }}
                </button>
                <button class="wx-max-btn" @click="wxExpanded = !wxExpanded" :title="wxExpanded ? '收起为侧边栏' : '全屏展开'">
                    {{ wxExpanded ? '⊠' : '⊞' }}
                </button>
            </div>
        </div>

        <div class="live-cards">
            <div class="live-main-card">
                <div class="live-main-icon">{{ weatherIcon }}</div>
                <div class="live-main-content">
                    <div class="live-city">{{ liveCityLabel }}</div>
                    <div class="live-weather-text">{{ liveWeatherText }}</div>
                    <div class="live-report-time">{{ liveReportTimeText }}</div>
                </div>
                <div class="live-temp">{{ liveTemperatureText }}</div>
            </div>

            <div class="live-mini-card">
                <span class="mini-label">湿度</span>
                <span class="mini-value">{{ liveHumidityText }}</span>
            </div>
            <div class="live-mini-card">
                <span class="mini-label">风向</span>
                <span class="mini-value">{{ liveWindDirectionText }}</span>
            </div>
            <div class="live-mini-card">
                <span class="mini-label">风力</span>
                <span class="mini-value">{{ liveWindPowerText }}</span>
            </div>
            <div class="live-mini-card">
                <span class="mini-label">体感</span>
                <span class="mini-value">{{ liveWeather?._apparentTemp != null ? liveWeather._apparentTemp + '°C' : '--' }}</span>
            </div>
        </div>

        <div class="rain-focus-panel" :class="{ 'has-rain': rainFocus.hasRain, 'unknown': rainFocus.level === 'unknown' }">
            <div class="rain-focus-left">
                <div class="rain-focus-icon">{{ rainFocus.icon }}</div>
                <div class="rain-focus-text">
                    <div class="rain-focus-title">{{ rainFocus.title }}</div>
                    <div class="rain-focus-subtitle">{{ rainFocus.subtitle }}</div>
                </div>
            </div>
            <div class="rain-focus-right">
                <span class="rain-badge">{{ rainFocus.badge }}</span>
                <div class="rain-hit-list">
                    <span v-if="!rainFocus.hits.length" class="rain-hit empty">未来 4 天白天/夜间均未识别到“雨”关键词</span>
                    <span
                        v-for="(hit, idx) in rainFocus.hits"
                        :key="`${hit.date}_${hit.period}_${idx}`"
                        class="rain-hit"
                    >
                        {{ hit.date }} {{ hit.period }} {{ hit.icon }} {{ hit.weather }}
                    </span>
                </div>
            </div>
        </div>

        <div class="charts-layout">
            <div class="chart-panel trend-panel">
                <div class="chart-title">未来 4 天气温趋势</div>
                <div ref="trendChartRef" class="chart-canvas"></div>
            </div>

            <div class="chart-panel side-panel">
                <div class="chart-title">风力仪表 + 预报风级</div>
                <div ref="windChartRef" class="chart-canvas"></div>
            </div>
        </div>

    </div>
</template>

<script setup>
// TODO:
// 天气api查询中，需要按照adcode进行查询，该数据已经本地化为json数据，在ControlsPanel中已经实现了前端的查询和可视化的功能，直接复用即可；
// 天气面板中当前实现的逻辑是请求两次高德api（第一次用api查询adcode，第二次用adcode查询天气，浪费了一次api，没有复用前端的adcode.json文件），需要接入该adcode.json进行，可以节省一次api并提高查询响应速度；
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useMessage } from '../composables/useMessage';
import { fetchOpenMeteo } from '../api/weatherOpenMeteo';
import { amapReverseGeocode } from '../api/amapDirect';
import {
    getGlobalUserLocationContext,
    USER_LOCATION_CONTEXT_CHANGE_EVENT
} from '../utils/userLocationContext';
import { useWeatherStore } from '../stores';

const message = useMessage();
const weatherStore = useWeatherStore();

const adcodeInput = ref(weatherStore.currentAdcode || '410202');
const isBusy = ref(false);
const liveWeather = ref(null);
const forecastWeather = ref(null);
const geoInfo = ref({ district: '', city: '', province: '' });
const lastWeatherCoords = ref(null);  // {lon, lat}
const wxExpanded = ref(false);  // fullscreen toggle
const viewportWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1366);

const isMobile = computed(() => viewportWidth.value <= 768);
const isCompact = computed(() => viewportWidth.value <= 1100);

const trendChartRef = ref(null);
const windChartRef = ref(null);
const panelRef = ref(null);

let echartsModule = null;
let echartsRuntimePromise = null;
let trendChart = null;
let windChart = null;
let resizeDebounceTimer = null;
let panelResizeObserver = null;
let panelResizeFrame = 0;

function loadEchartsRuntime() {
    if (echartsRuntimePromise) return echartsRuntimePromise;

    echartsRuntimePromise = import('../utils/echarts/weatherRuntime.js').then((runtimeModule) => {
        const runtime = runtimeModule?.getWeatherEchartsRuntime?.();
        if (!runtime) {
            throw new Error('天气图表运行时加载失败');
        }

        echartsModule = runtime;
        return runtime;
    }).catch((error) => {
        echartsRuntimePromise = null;
        throw error;
    });

    return echartsRuntimePromise;
}

const WEATHER_ICON_MAP = {
    晴: '☀️',
    多云: '⛅',
    阴: '☁️',
    阵雨: '🌦️',
    雷阵雨: '⛈️',
    小雨: '🌧️',
    中雨: '🌧️',
    大雨: '🌧️',
    暴雨: '🌧️',
    小雪: '🌨️',
    中雪: '🌨️',
    大雪: '❄️',
    雾: '🌫️',
    霾: '🌫️',
    有风: '🌬️',
    大风: '🌬️',
    台风: '🌪️',
    沙尘暴: '🌪️'
};

const WEEK_LABEL_MAP = {
    '1': '周一',
    '2': '周二',
    '3': '周三',
    '4': '周四',
    '5': '周五',
    '6': '周六',
    '7': '周日'
};

const RAIN_KEYWORD_REGEXP = /雨|雷|暴雨|阵雨|冻雨|雨夹雪|毛毛雨|强对流/;

// ── Theme-aware CSS variable reader ──
function readCSSVar(name) {
    if (typeof document === 'undefined') return '';
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function resolveWeatherIcon(weatherText) {
    const text = String(weatherText || '').trim();
    if (!text) return '🌤️';
    const exact = WEATHER_ICON_MAP[text];
    if (exact) return exact;
    const matchedKey = Object.keys(WEATHER_ICON_MAP).find((key) => text.includes(key));
    return matchedKey ? WEATHER_ICON_MAP[matchedKey] : '🌤️';
}

function hasRainSignal(weatherText) {
    return RAIN_KEYWORD_REGEXP.test(String(weatherText || '').trim());
}

function formatWeekLabel(weekValue) {
    const text = String(weekValue || '').trim();
    if (!text) return '--';
    return WEEK_LABEL_MAP[text] || text;
}

function toFixedNumber(value, fallback = '--') {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return fallback;
    return numeric;
}

function toNumberOrNull(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}

function normalizeWindPower(value) {
    const text = String(value ?? '').trim();
    const matched = text.match(/\d+(?:\.\d+)?/);
    const numeric = matched ? Number(matched[0]) : 0;
    return Number.isFinite(numeric) ? numeric : 0;
}

function formatDateLabel(dateText) {
    const text = String(dateText || '').trim();
    if (!text) return '--';

    const date = new Date(text);
    if (Number.isNaN(date.getTime())) return text;

    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${month}-${day}`;
}

const casts = computed(() => {
    const list = Array.isArray(forecastWeather.value?.casts) ? forecastWeather.value.casts : [];
    return list.slice(0, 4);
});

const weatherIcon = computed(() => {
    const weatherText = String(liveWeather.value?.weather || '').trim();
    return resolveWeatherIcon(weatherText);
});

const liveCityLabel = computed(() => {
    const district = String(liveWeather.value?.district || geoInfo.value?.district || '').trim();
    const city = String(liveWeather.value?.city || geoInfo.value?.city || '').trim();
    const province = String(liveWeather.value?.province || geoInfo.value?.province || '').trim();
    // 优先显示区县 + 市，如"天河区, 广州"
    if (district) return `${district}, ${city || province}`;
    if (city) return `${city}, ${province}`;
    if (province) return province;
    if (lastWeatherCoords.value) {
        return `${lastWeatherCoords.value.lat.toFixed(2)}°N, ${lastWeatherCoords.value.lon.toFixed(2)}°E`;
    }
    return '点击地图获取天气';
});

const liveWeatherText = computed(() => String(liveWeather.value?.weather || '天气未知').trim() || '天气未知');
const liveTemperatureText = computed(() => {
    const temp = toFixedNumber(liveWeather.value?.temperature, '--');
    return temp === '--' ? '--°C' : `${temp}°C`;
});
const liveHumidityText = computed(() => {
    const humidity = toFixedNumber(liveWeather.value?.humidity, '--');
    return humidity === '--' ? '--' : `${humidity}%`;
});
const liveWindDirectionText = computed(() => String(liveWeather.value?.windDirection || '--').trim() || '--');
const liveWindPowerText = computed(() => String(liveWeather.value?.windPowerText || '--').trim() || '--');
const liveReportTimeText = computed(() => String(liveWeather.value?.reportTime || forecastWeather.value?.reportTime || '--').trim() || '--');

const rainFocus = computed(() => {
    const liveText = String(liveWeather.value?.weather || '').trim();
    const liveHasRain = hasRainSignal(liveText);

    const hits = [];
    casts.value.forEach((cast) => {
        const date = formatDateLabel(cast?.date || '');

        if (hasRainSignal(cast?.dayWeather)) {
            hits.push({
                date,
                period: '白天',
                weather: String(cast?.dayWeather || '--'),
                icon: resolveWeatherIcon(cast?.dayWeather)
            });
        }

        if (hasRainSignal(cast?.nightWeather)) {
            hits.push({
                date,
                period: '夜间',
                weather: String(cast?.nightWeather || '--'),
                icon: resolveWeatherIcon(cast?.nightWeather)
            });
        }
    });

    const hasRain = liveHasRain || hits.length > 0;
    const hasAnyText = !!liveText || casts.value.some((cast) => String(cast?.dayWeather || cast?.nightWeather || '').trim());

    if (!hasAnyText) {
        return {
            hasRain: false,
            level: 'unknown',
            icon: '🌫️',
            badge: '待判定',
            title: '暂未获取到可判定的天气文本',
            subtitle: '请刷新或切换 adcode 后重试',
            hits
        };
    }

    if (hasRain) {
        return {
            hasRain: true,
            level: 'rain',
            icon: '🌧️',
            badge: '降雨信号',
            title: liveHasRain
                ? `当前实况：${resolveWeatherIcon(liveText)} ${liveText}`
                : '未来 4 日预报存在降雨时段',
            subtitle: hits.length
                ? `未来 4 日识别到 ${hits.length} 个可能降雨时段`
                : '当前天气文本中包含降雨关键词',
            hits
        };
    }

    return {
        hasRain: false,
        level: 'clear',
        icon: '☀️',
        badge: '无雨信号',
        title: '当前与未来 4 日未识别到降雨关键词',
        subtitle: '如需更精细的降雨概率，建议接入分钟级降水或雷达数据',
        hits
    };
});

function renderTrendChart() {
    if (!trendChart || !echartsModule) return;

    const chartWidth = Number(trendChart?.getWidth?.() || trendChartRef.value?.clientWidth || viewportWidth.value || 640);
    const chartHeight = Number(trendChart?.getHeight?.() || trendChartRef.value?.clientHeight || 260);
    const mobile = chartWidth <= 460;
    const compact = chartWidth <= 560 || chartHeight <= 240;

    const dates = casts.value.map((item) => formatDateLabel(item.date));
    const dayTemps = casts.value.map((item) => toNumberOrNull(item?.dayTemp));
    const nightTemps = casts.value.map((item) => toNumberOrNull(item?.nightTemp));
    const validTemps = [...dayTemps, ...nightTemps].filter((temp) => Number.isFinite(temp));

    const yMin = validTemps.length ? Math.max(-50, Math.floor(Math.min(...validTemps) - 2)) : 0;
    const yMax = validTemps.length ? Math.min(60, Math.ceil(Math.max(...validTemps) + 2)) : 40;

    const option = {
        backgroundColor: 'transparent',
        animationDuration: 420,
        animationDurationUpdate: 300,
        tooltip: {
            trigger: 'axis',
            backgroundColor: readCSSVar('--surface-card-strong').replace(')', ', 0.88)').replace('rgba(', 'rgba(') || 'rgba(14,22,34,0.88)',
            borderColor: readCSSVar('--border-active') || 'rgba(13,180,247,0.4)',
            borderWidth: 1,
            textStyle: { color: readCSSVar('--text-primary') || '#e8f4ff' },
            formatter(params) {
                const list = Array.isArray(params) ? params : [];
                if (!list.length) return '--';

                const title = String(list[0]?.axisValue || '--');
                const lines = list
                    .map((item) => {
                        const value = Number(item?.data);
                        const text = Number.isFinite(value) ? `${value}°C` : '--';
                        return `${item.marker}${item.seriesName}: ${text}`;
                    })
                    .join('<br/>');
                return `${title}<br/>${lines}`;
            }
        },
        legend: {
            data: ['白天气温', '晚间气温'],
            top: 8,
            icon: 'roundRect',
            itemWidth: mobile ? 10 : 14,
            itemHeight: mobile ? 6 : 8,
            textStyle: { color: readCSSVar('--text-secondary') || '#6aa9ff', fontSize: mobile ? 11 : 12 }
        },
        grid: {
            left: mobile ? 34 : 42,
            right: mobile ? 14 : 18,
            top: mobile ? 46 : 48,
            bottom: mobile ? 34 : 30,
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: dates,
            axisLine: { lineStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7' } },
            axisLabel: {
                color: readCSSVar('--neon-cyan') || '#0db4f7',
                fontSize: mobile ? 11 : 12,
                rotate: compact ? 14 : 0
            },
            axisTick: { alignWithLabel: true }
        },
        yAxis: {
            type: 'value',
            name: '°C',
            min: yMin,
            max: yMax,
            axisLine: { show: false },
            axisLabel: { color: readCSSVar('--neon-cyan') || '#0db4f7', fontSize: mobile ? 11 : 12 },
            nameTextStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7', fontSize: mobile ? 10 : 11 },
            splitLine: { lineStyle: { color: readCSSVar('--border-subtle') || 'rgba(13,180,247,0.12)' } }
        },
        series: [
            {
                name: '白天气温',
                type: 'line',
                smooth: true,
                showSymbol: !mobile,
                symbolSize: mobile ? 6 : 8,
                data: dayTemps,
                connectNulls: true,
                lineStyle: { width: mobile ? 2.5 : 3, color: readCSSVar('--neon-green') || '#16f2b3' },
                itemStyle: { color: readCSSVar('--neon-green') || '#16f2b3' },
                areaStyle: {
                    color: new echartsModule.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(22,242,179,0.35)' },
                        { offset: 1, color: 'rgba(22,242,179,0.02)' }
                    ])
                },
                emphasis: { focus: 'series' },
                markPoint: mobile ? undefined : {
                    symbolSize: 34,
                    label: { color: '#ffffff', fontSize: 10 },
                    itemStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7' },
                    data: [{ type: 'max', name: '最高' }, { type: 'min', name: '最低' }]
                }
            },
            {
                name: '晚间气温',
                type: 'line',
                smooth: true,
                showSymbol: !mobile,
                symbolSize: mobile ? 6 : 8,
                data: nightTemps,
                connectNulls: true,
                lineStyle: { width: mobile ? 2.5 : 3, color: readCSSVar('--accent-blue') || '#2d8cff' },
                itemStyle: { color: readCSSVar('--accent-blue') || '#2d8cff' },
                areaStyle: {
                    color: new echartsModule.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(45,140,255,0.32)' },
                        { offset: 1, color: 'rgba(45,140,255,0.02)' }
                    ])
                },
                emphasis: { focus: 'series' }
            }
        ]
    };

    trendChart.setOption(option, { notMerge: true, lazyUpdate: true });
}

function clampValue(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return Math.min(max, Math.max(min, value));
}

function getWindLayoutMetrics() {
    const rawWidth = Number(windChart?.getWidth?.() || windChartRef.value?.clientWidth || 640);
    const rawHeight = Number(windChart?.getHeight?.() || windChartRef.value?.clientHeight || 280);

    const width = Math.max(260, rawWidth);
    const height = Math.max(190, rawHeight);
    const ratio = width / Math.max(height, 1);
    const compact = width <= 420 || height <= 230;

    const legendTopPx = clampValue(Math.round(height * 0.03), 4, 12);
    const legendFontSize = compact ? 10 : clampValue(Math.round(width * 0.018), 10, 14);
    const legendItemWidth = clampValue(Math.round(width * 0.02), 8, 16);
    const legendItemHeight = clampValue(Math.round(height * 0.022), 5, 9);

    const preferredGaugeByWidth = ratio >= 2.2 ? width * 0.1 : width * 0.13;
    const preferredGaugeByHeight = height * (compact ? 0.24 : 0.28);
    const gaugeRadiusPx = clampValue(Math.round(Math.min(preferredGaugeByWidth, preferredGaugeByHeight)), compact ? 34 : 42, compact ? 58 : 88);
    const gaugeCenterYPx = clampValue(Math.round(legendTopPx + 18 + gaugeRadiusPx * 0.8), 52, Math.round(height * (compact ? 0.34 : 0.4)));

    const minSide = Math.min(width, height);
    const gaugeRadiusPercent = `${clampValue((gaugeRadiusPx / minSide) * 100, 14, 34).toFixed(2)}%`;
    const gaugeCenterYPercent = `${((gaugeCenterYPx / height) * 100).toFixed(2)}%`;

    const gaugeStroke = clampValue(Math.round(gaugeRadiusPx * 0.15), 6, 11);
    const gaugeSplitLength = clampValue(Math.round(gaugeRadiusPx * 0.12), 5, 8);
    const gaugeAxisFontSize = compact ? 7 : clampValue(Math.round(gaugeRadiusPx * 0.14), 7, 10);
    const gaugeDetailFontSize = compact ? 12 : clampValue(Math.round(gaugeRadiusPx * 0.35), 14, 24);
    const gaugeSplitNumber = 4;
    const gaugeLabelStep = 3;
    const gaugeLabelDistance = clampValue(Math.round(gaugeRadiusPx * 0.25), 10, 22);

    const barsTopPx = clampValue(
        Math.round(gaugeCenterYPx + gaugeRadiusPx * (compact ? 0.5 : 0.46) + height * 0.055),
        compact ? 96 : 116,
        Math.round(height * (compact ? 0.54 : 0.6))
    );
    const barsTopPercent = `${((barsTopPx / height) * 100).toFixed(2)}%`;

    const gridLeft = clampValue(Math.round(width * 0.055), 26, 52);
    const gridRight = clampValue(Math.round(width * 0.03), 12, 22);
    const gridBottom = clampValue(Math.round(height * 0.09), compact ? 20 : 24, 40);
    const axisFontSize = compact ? 10 : clampValue(Math.round(width * 0.017), 10, 13);
    const yNameFontSize = clampValue(axisFontSize - 1, 9, 12);
    const barMaxWidth = clampValue(Math.round(width * 0.028), 8, 20);
    const lineSymbolSize = clampValue(Math.round(width * 0.011), 4, 7);

    return {
        legendTopPx,
        legendFontSize,
        legendItemWidth,
        legendItemHeight,
        gaugeRadiusPercent,
        gaugeCenterYPercent,
        gaugeRadiusPx,
        gaugeStroke,
        gaugeSplitLength,
        gaugeSplitNumber,
        gaugeLabelStep,
        gaugeLabelDistance,
        gaugeAxisFontSize,
        gaugeDetailFontSize,
        barsTopPercent,
        gridLeft,
        gridRight,
        gridBottom,
        axisFontSize,
        yNameFontSize,
        barMaxWidth,
        lineSymbolSize,
        compact
    };
}

function renderWindChart() {
    if (!windChart || !echartsModule) return;

    const metrics = getWindLayoutMetrics();

    const currentWind = normalizeWindPower(liveWeather.value?.windPowerText);
    const dateLabels = casts.value.map((item) => formatDateLabel(item.date));
    const dayPowers = casts.value.map((item) => {
        const numeric = Number(item?.dayPower);
        return Number.isFinite(numeric) ? numeric : normalizeWindPower(item?.dayPowerText);
    });
    const nightPowers = casts.value.map((item) => {
        const numeric = Number(item?.nightPower);
        return Number.isFinite(numeric) ? numeric : normalizeWindPower(item?.nightPowerText);
    });
    const averagePowers = dayPowers.map((dayPower, index) => {
        const nightPower = Number(nightPowers[index]);
        if (!Number.isFinite(dayPower) && !Number.isFinite(nightPower)) return null;
        if (!Number.isFinite(dayPower)) return nightPower;
        if (!Number.isFinite(nightPower)) return dayPower;
        return Number(((dayPower + nightPower) / 2).toFixed(1));
    });

    const forecastMaxPower = Math.max(0, ...dayPowers, ...nightPowers);
    const axisMax = Math.max(8, Math.min(12, Math.ceil(forecastMaxPower + 1)));
    const xLabelRotate = dateLabels.some((item) => String(item || '').length > 5) ? 12 : 0;

    const option = {
        backgroundColor: 'transparent',
        animationDuration: 420,
        animationDurationUpdate: 300,
        legend: {
            data: ['白天风力', '夜间风力', '平均风力'],
            top: metrics.legendTopPx,
            type: 'scroll',
            icon: 'roundRect',
            itemWidth: metrics.legendItemWidth,
            itemHeight: metrics.legendItemHeight,
            pageIconColor: readCSSVar('--neon-cyan') || '#0db4f7',
            pageTextStyle: { color: readCSSVar('--text-muted') || '#789' },
            textStyle: { color: readCSSVar('--text-secondary') || '#6aa9ff', fontSize: metrics.legendFontSize }
        },
        grid: {
            left: metrics.gridLeft,
            right: metrics.gridRight,
            top: metrics.barsTopPercent,
            bottom: metrics.gridBottom,
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: dateLabels,
            axisLabel: {
                color: readCSSVar('--neon-cyan') || '#0db4f7',
                fontSize: metrics.axisFontSize,
                rotate: xLabelRotate
            },
            axisLine: { lineStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7' } }
        },
        yAxis: {
            type: 'value',
            name: '级',
            min: 0,
            max: axisMax,
            axisLabel: { color: readCSSVar('--neon-cyan') || '#0db4f7', fontSize: metrics.axisFontSize },
            nameTextStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7', fontSize: metrics.yNameFontSize },
            splitLine: { lineStyle: { color: readCSSVar('--border-subtle') || 'rgba(13,180,247,0.12)' } }
        },
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            backgroundColor: readCSSVar('--surface-card-strong').replace(')', ', 0.88)').replace('rgba(', 'rgba(') || 'rgba(14,22,34,0.88)',
            borderColor: readCSSVar('--border-active') || 'rgba(13,180,247,0.4)',
            borderWidth: 1,
            textStyle: { color: readCSSVar('--text-primary') || '#e8f4ff' },
            formatter(params) {
                const list = Array.isArray(params) ? params : [];
                if (!list.length) return '--';

                const dataIndex = Number(list[0]?.dataIndex);
                const cast = casts.value[dataIndex] || {};
                const lines = list.map((item) => {
                    const value = Number(item?.data);
                    const text = Number.isFinite(value) ? `${value}级` : '--';
                    return `${item.marker}${item.seriesName}: ${text}`;
                });

                return [
                    String(list[0]?.axisValue || '--'),
                    ...lines,
                    `白天风向: ${String(cast?.dayWind || '--')}`,
                    `夜间风向: ${String(cast?.nightWind || '--')}`
                ].join('<br/>');
            }
        },
        series: [
            {
                type: 'gauge',
                startAngle: 210,
                endAngle: -30,
                tooltip: {
                    trigger: 'item',
                    formatter: `当前实况风力：${currentWind} 级`
                },
                center: ['50%', metrics.gaugeCenterYPercent],
                radius: metrics.gaugeRadiusPercent,
                min: 0,
                max: 12,
                splitNumber: metrics.gaugeSplitNumber,
                progress: { 
                    show: true, 
                    width: metrics.gaugeStroke,
                    roundCap: true,
                    itemStyle: { 
                        color: new echartsModule.graphic.LinearGradient(0, 0, 1, 0, [
                            { offset: 0, color: readCSSVar('--neon-green') || '#16f2b3' },
                            { offset: 1, color: readCSSVar('--neon-cyan') || '#0db4f7' }
                        ])
                    } 
                },
                axisLine: {
                    roundCap: true,
                    lineStyle: {
                        width: metrics.gaugeStroke,
                        color: [[1, readCSSVar('--border-subtle') || 'rgba(13,180,247,0.12)']]
                    }
                },
                axisTick: { show: false },
                splitLine: { 
                    length: metrics.gaugeSplitLength, 
                    lineStyle: { color: readCSSVar('--neon-cyan') || '#0db4f7', width: 2 } 
                },
                axisLabel: {
                    color: readCSSVar('--text-secondary') || '#6aa9ff',
                    fontSize: metrics.gaugeAxisFontSize,
                    distance: metrics.gaugeLabelDistance,
                    formatter(value) {
                        const numeric = Number(value);
                        if (!Number.isFinite(numeric)) return '';
                        return numeric % metrics.gaugeLabelStep === 0 ? String(numeric) : '';
                    }
                },
                pointer: { 
                    itemStyle: { color: readCSSVar('--neon-green') || '#16f2b3' }, 
                    length: '45%',
                    width: Math.max(3, metrics.gaugeStroke * 0.4)
                },
                title: { show: false },
                detail: {
                    valueAnimation: true,
                    fontSize: metrics.compact ? 11 : Math.min(metrics.gaugeDetailFontSize, 13),
                    fontWeight: 700,
                    color: readCSSVar('--text-primary') || '#e8f4ff',
                    offsetCenter: [0, metrics.compact ? '55%' : '48%'],
                    formatter: '{value} 级'
                },
                data: [{ value: currentWind }]
            },
            {
                name: '白天风力',
                type: 'bar',
                barMaxWidth: metrics.barMaxWidth,
                data: dayPowers,
                itemStyle: {
                    borderRadius: [5, 5, 0, 0],
                    color: new echartsModule.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(22, 242, 179, 0.92)' },
                        { offset: 1, color: 'rgba(22, 242, 179, 0.48)' }
                    ])
                }
            },
            {
                name: '夜间风力',
                type: 'bar',
                barMaxWidth: metrics.barMaxWidth,
                data: nightPowers,
                itemStyle: {
                    borderRadius: [5, 5, 0, 0],
                    color: new echartsModule.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(43, 139, 255, 0.9)' },
                        { offset: 1, color: 'rgba(43, 139, 255, 0.45)' }
                    ])
                }
            },
            {
                name: '平均风力',
                type: 'line',
                smooth: true,
                showSymbol: true,
                symbolSize: metrics.lineSymbolSize,
                data: averagePowers,
                lineStyle: { width: 2.2, color: '#2f7f58', type: 'dashed' },
                itemStyle: { color: '#2f7f58' }
            }
        ]
    };

    windChart.setOption(option, { notMerge: true, lazyUpdate: true });
}

function showChartsLoading() {
    trendChart?.showLoading?.('default', { text: '天气数据加载中...' });
    windChart?.showLoading?.('default', { text: '天气数据加载中...' });
}

function hideChartsLoading() {
    trendChart?.hideLoading?.();
    windChart?.hideLoading?.();
}

async function ensureEchartsReady() {
    if (echartsModule) return echartsModule;

    try {
        return await loadEchartsRuntime();
    } catch (error) {
        message.error('ECharts 模块加载失败', error);
        throw error instanceof Error ? error : new Error('ECharts 模块加载失败');
    }
}

async function ensureChartInstances() {
    await ensureEchartsReady();
    await nextTick();

    if (!trendChart && trendChartRef.value) {
        trendChart = echartsModule.init(trendChartRef.value);
    }

    if (!windChart && windChartRef.value) {
        windChart = echartsModule.init(windChartRef.value);
    }
}

function resizeCharts() {
    trendChart?.resize?.();
    windChart?.resize?.();
}

function schedulePanelChartResize() {
    if (typeof window === 'undefined') return;
    if (panelResizeFrame) {
        window.cancelAnimationFrame(panelResizeFrame);
    }
    panelResizeFrame = window.requestAnimationFrame(() => {
        panelResizeFrame = 0;
        resizeCharts();
        renderTrendChart();
        renderWindChart();
    });
}

function startPanelResizeObserver() {
    if (typeof ResizeObserver === 'undefined' || !panelRef.value || panelResizeObserver) return;
    panelResizeObserver = new ResizeObserver(() => {
        schedulePanelChartResize();
    });
    panelResizeObserver.observe(panelRef.value);
    if (trendChartRef.value) panelResizeObserver.observe(trendChartRef.value);
    if (windChartRef.value) panelResizeObserver.observe(windChartRef.value);
}

function stopPanelResizeObserver() {
    panelResizeObserver?.disconnect?.();
    panelResizeObserver = null;
    if (typeof window !== 'undefined' && panelResizeFrame) {
        window.cancelAnimationFrame(panelResizeFrame);
        panelResizeFrame = 0;
    }
}

function handleWindowResize() {
    if (typeof window === 'undefined') return;

    if (resizeDebounceTimer !== null) {
        window.clearTimeout(resizeDebounceTimer);
    }

    resizeDebounceTimer = window.setTimeout(() => {
        viewportWidth.value = window.innerWidth;
        resizeCharts();
        renderTrendChart();
        renderWindChart();
    }, 120);
}

let wxRequestId = 0;
let wxTargetCoords = null; // only respond to the latest target
async function loadWeatherForCoords(lon, lat) {
    const reqId = ++wxRequestId;
    wxTargetCoords = { lon, lat };
    lastWeatherCoords.value = { lon, lat };
    isBusy.value = true;
    try {
        await ensureChartInstances();
        showChartsLoading();
        const data = await fetchOpenMeteo(lat, lon);
        if (reqId !== wxRequestId) return;
        // Preserve geo info from reverse geocode (set by resolveAdcodeByLonLat)
        const prevGeo = liveWeather.value;
        const province = prevGeo?.province || data.live.province || '';
        const city = prevGeo?.city || data.live.city || '';
        liveWeather.value = { ...data.live, province, city };
        forecastWeather.value = data.forecast;
        await nextTick();
        resizeCharts();
        renderTrendChart();
        renderWindChart();
    } catch (e) {
        message.error('天气获取失败，请检查网络连接');
    } finally {
        isBusy.value = false;
        hideChartsLoading();
    }
}

function applyAdcodeFromLocationContext(context, source = 'location-context') {
    const currentContext = context || getGlobalUserLocationContext();
    const adcode = String(currentContext?.encodedLocation?.adcode || '').trim();
    if (!/^\d{6}$/.test(adcode)) return false;

    weatherStore.setAdcode(adcode, {
        city: currentContext?.encodedLocation?.city || weatherStore.currentCity,
        province: currentContext?.encodedLocation?.province || weatherStore.currentProvince,
        source
    });
    adcodeInput.value = adcode;
    return true;
}

async function resolveAdcodeByLonLat(lon, lat, source = 'map-event') {
    const longitude = Number(lon);
    const latitude = Number(lat);
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return;

    // 前端直连高德逆地理编码，获取区/市/省名称
    try {
        const geo = await amapReverseGeocode(longitude, latitude);
        if (geo) {
            geoInfo.value = { district: geo.district, city: geo.city, province: geo.province };
            liveWeather.value = liveWeather.value || {};
            liveWeather.value.province = geo.province;
            liveWeather.value.city = geo.city;
            liveWeather.value.district = geo.district;
            forecastWeather.value = forecastWeather.value || {};
            forecastWeather.value.province = geo.province;
            forecastWeather.value.city = geo.city;
        }
    } catch { /* geocode failed, still show weather with coords */ }

    await loadWeatherForCoords(longitude, latitude);
}

async function refreshWeather() {
    const coords = lastWeatherCoords.value;
    if (coords) {
        await loadWeatherForCoords(coords.lon, coords.lat);
    } else {
        message.info('请先在地图上定位到目标区域，再打开天气看板');
    }
}

function handleLocationContextChange(event) {
    const context = event?.detail?.context || null;
    const changed = applyAdcodeFromLocationContext(context, 'location-context-change');
    if (!changed) return;

    // Use Open-Meteo with last known coordinates
    if (lastWeatherCoords.value) {
        void loadWeatherForCoords(lastWeatherCoords.value.lon, lastWeatherCoords.value.lat);
    }
}

watch(
    () => weatherStore.currentAdcode,
    (nextAdcode) => {
        const normalized = String(nextAdcode || '').trim();
        if (!/^\d{6}$/.test(normalized)) return;
        adcodeInput.value = normalized;
        // Open-Meteo uses coordinates, not adcode
    }
);

watch(
    () => weatherStore.mapPointTrigger,
    (payload) => {
        if (!payload) return;
        void resolveAdcodeByLonLat(payload.lon, payload.lat, payload.source || 'map-event');
    },
    { deep: true }
);

// Re-render charts when theme changes (light/dark switch)
if (typeof window !== 'undefined') {
    const themeObserver = new MutationObserver(() => {
        if (trendChart && windChart) {
            renderTrendChart();
            renderWindChart();
        }
    });
    onMounted(() => {
        const el = document.documentElement;
        if (el) themeObserver.observe(el, { attributes: true, attributeFilter: ['data-theme'] });
    });
    onBeforeUnmount(() => themeObserver.disconnect());
}

onMounted(async () => {
    await ensureChartInstances();
    startPanelResizeObserver();
    viewportWidth.value = typeof window !== 'undefined' ? window.innerWidth : 1366;

    const loadedFromContext = applyAdcodeFromLocationContext(null, 'location-context-initial');
    const initAdcode = loadedFromContext
        ? weatherStore.currentAdcode
        : (weatherStore.currentAdcode || '410202');

    // Open-Meteo waits for map center trigger from user

    if (typeof window !== 'undefined') {
        window.addEventListener(USER_LOCATION_CONTEXT_CHANGE_EVENT, handleLocationContextChange);
        window.addEventListener('resize', handleWindowResize);
    }
});

onBeforeUnmount(() => {
    stopPanelResizeObserver();
    if (typeof window !== 'undefined') {
        window.removeEventListener(USER_LOCATION_CONTEXT_CHANGE_EVENT, handleLocationContextChange);
        window.removeEventListener('resize', handleWindowResize);
        if (resizeDebounceTimer !== null) {
            window.clearTimeout(resizeDebounceTimer);
            resizeDebounceTimer = null;
        }
    }

    trendChart?.dispose?.();
    windChart?.dispose?.();
    trendChart = null;
    windChart = null;
});
</script>

<style scoped>
.weather-panel {
    height: 100%;
    width: 100%;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
    padding: var(--space-md);
    box-sizing: border-box;
    background: var(--glass-bg-heavy);
    backdrop-filter: blur(var(--glass-blur)) var(--glass-saturate);
    -webkit-backdrop-filter: blur(var(--glass-blur)) var(--glass-saturate);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    overflow: auto;
    transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
    container-type: size;
}
.weather-panel.wx-fullscreen {
    position: fixed; inset: 56px 0 0 0; z-index: 100;
    border-radius: 0; max-width: 100vw;
}

.weather-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--surface-0);
    flex-shrink: 0;
}

.weather-title {
    margin: 0; font-size: var(--font-size-lg); font-weight: 600; line-height: 1.2;
    color: var(--text-primary);
}
.weather-subtitle {
    margin: 2px 0 0; font-size: var(--font-size-xs); font-family: var(--font-mono);
    color: var(--text-muted);
}

.weather-toolbar-left {
    min-width: 0;
}

.weather-toolbar-right {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    flex-wrap: wrap;
}

.toolbar-btn {
    border: 1px solid var(--border-active); border-radius: var(--radius-sm);
    background: var(--neon-cyan-dim); color: var(--neon-cyan);
    height: 32px; padding: 0 14px; font-size: var(--font-size-sm); font-weight: 500;
    cursor: pointer; transition: all var(--duration-fast) var(--ease-out-expo);
}
.toolbar-btn:hover {
    background: rgba(13, 180, 247, 0.22);
    box-shadow: var(--neon-cyan-glow);
}
.toolbar-btn:disabled {
    opacity: 0.55;
    cursor: not-allowed;
    box-shadow: none;
}
.wx-max-btn {
    border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
    background: var(--surface-0); color: var(--text-muted);
    height: 32px; width: 32px; font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: all var(--duration-fast) var(--ease-out-expo);
}
.wx-max-btn:hover { color: var(--neon-cyan); border-color: var(--border-active); }








.live-cards {
    display: grid;
    grid-template-columns: minmax(min(260px, 100%), 2.1fr) repeat(4, minmax(96px, 1fr));
    gap: 8px;
    flex-shrink: 0;
}

.live-main-card {
    border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
    background: var(--surface-card); padding: var(--space-md);
    display: flex; align-items: center; gap: var(--space-md);
}

.live-main-icon {
    width: 48px; height: 48px; border-radius: var(--radius-sm);
    background: rgba(13, 180, 247, 0.10);
    display: flex; align-items: center; justify-content: center;
    font-size: 27px; flex-shrink: 0;
}
.live-main-content { min-width: 0; flex: 1; }
.live-city {
    font-size: var(--font-size-md); font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.live-weather-text { margin-top: 2px; font-size: var(--font-size-sm); color: var(--text-secondary); }
.live-report-time { margin-top: 2px; font-size: var(--font-size-xs); color: var(--text-muted); font-family: var(--font-mono); }
.live-temp {
    font-size: 28px; font-weight: 700;
    background: linear-gradient(180deg, var(--text-primary) 30%, var(--neon-cyan));
    background-clip: text; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    flex-shrink: 0;
}

.live-mini-card {
    border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
    background: var(--surface-0); padding: var(--space-sm);
    display: flex; flex-direction: column; justify-content: center; gap: 2px;
}
.mini-label { font-family: var(--font-mono); font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }
.mini-value { font-size: var(--font-size-md); font-weight: 600; color: var(--text-primary); word-break: break-word; }

.rain-focus-panel {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    padding: var(--space-md);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-md);
    flex-shrink: 0;
}
.rain-focus-panel.has-rain {
    border-color: rgba(13, 180, 247, 0.25);
    background: rgba(13, 180, 247, 0.06);
}
.rain-focus-panel.unknown {
    border-color: var(--border-subtle);
}
.rain-focus-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}
.rain-focus-icon {
    width: 44px;
    height: 44px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(13, 180, 247, 0.12);
    font-size: 24px;
    flex-shrink: 0;
}
.rain-focus-title {
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--text-primary);
}
.rain-focus-subtitle {
    margin-top: 3px;
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.rain-focus-right {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
    min-width: min(260px, 100%);
}

.rain-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid rgba(54, 147, 88, 0.35);
    color: #1f6d45;
    font-size: 12px;
    font-weight: 700;
    background: rgba(255, 255, 255, 0.75);
}

.rain-hit-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: flex-end;
}

.rain-hit {
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid rgba(54, 147, 88, 0.25);
    background: rgba(255, 255, 255, 0.75);
    color: #1f5b3b;
    font-size: 11px;
    white-space: normal;
    overflow-wrap: anywhere;
}

.rain-hit.empty {
    border-style: dashed;
    color: #597a68;
}

.charts-layout {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr));
    gap: 10px;
    align-items: stretch;
    position: relative;
    min-height: 0;
}

.chart-panel {
    border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
    background: var(--surface-card);
    display: flex; flex-direction: column; min-width: 0; min-height: 0; position: relative; overflow: hidden;
}
.chart-title {
    padding: var(--space-sm) var(--space-md) 2px;
    font-size: var(--font-size-xs); font-weight: 600;
    font-family: var(--font-mono); text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-muted);
}
.chart-canvas {
    width: 100%;
    height: clamp(210px, 34cqh, 330px);
    min-height: 210px;
}

@container (max-width: 900px) {
    .live-cards {
        grid-template-columns: 1fr 1fr;
    }

    .live-main-card {
        grid-column: 1 / -1;
    }

    .charts-layout {
        grid-template-columns: 1fr;
    }

    .chart-canvas {
        height: clamp(205px, 32cqh, 300px);
        min-height: 205px;
    }
}

@container (max-width: 560px) {
    .weather-panel {
        padding: 9px;
        gap: 8px;
        border-radius: 10px;
    }

    .weather-toolbar {
        flex-direction: column;
        align-items: flex-start;
    }

    .weather-title {
        font-size: 18px;
    }

    .weather-toolbar-right {
        width: 100%;
        justify-content: stretch;
    }

    .toolbar-btn {
        flex: 1 1 180px;
        height: 36px;
    }

    .live-cards {
        grid-template-columns: 1fr;
    }

    .live-main-card {
        grid-column: auto;
    }

    .live-main-icon {
        width: 42px;
        height: 42px;
        font-size: 24px;
    }

    .live-temp {
        font-size: 24px;
    }

    .rain-focus-panel {
        flex-direction: column;
        align-items: flex-start;
    }

    .rain-focus-right {
        min-width: 0;
        width: 100%;
        align-items: flex-start;
    }

    .rain-hit-list {
        justify-content: flex-start;
    }

    .chart-canvas {
        height: clamp(195px, 30cqh, 260px);
        min-height: 195px;
    }
}

@container (max-width: 420px) {
    .weather-panel {
        padding: 8px;
    }

    .weather-title {
        font-size: 16px;
    }

    .weather-subtitle {
        font-size: 11px;
    }

    .live-city {
        font-size: 14px;
    }

    .mini-value {
        font-size: 14px;
    }

    .chart-title {
        font-size: 12px;
    }

    .chart-canvas {
        height: 200px;
        min-height: 190px;
    }
}

@media (max-width: 768px) {
    .weather-panel {
        padding: 9px;
    }
}
</style>
