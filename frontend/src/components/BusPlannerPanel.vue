<template>
    <div class="bus-planner-panel">
        <div class="panel-head">
            <div>
                <div class="title">公交规划</div>
                <div class="title-sub">Transit Route Planner</div>
            </div>
            <button class="ghost-btn" @click="$emit('close')">关闭</button>
        </div>

        <MapPointPickerCard
            :pick-mode="pickMode"
            :start-point="startPoint"
            :end-point="endPoint"
            :start-address="startAddress"
            :end-address="endAddress"
            theme="bus"
            start-label="设置起点"
            end-label="设置终点"
            @pick-start="enablePick('start')"
            @pick-end="enablePick('end')"
        />

        <div class="plan-row">
            <label class="plan-label" for="lineTypeSelect">公交策略</label>
            <select id="lineTypeSelect" v-model="lineType" class="plan-select">
                <option value="1">1 - 较快捷</option>
                <option value="2">2 - 少换乘</option>
                <option value="3">3 - 少步行</option>
                <option value="4">4 - 不乘地铁</option>
            </select>
            <button class="plan-btn" :disabled="planning" @click="startTransitPlan">
                {{ planning ? '规划中...' : '开始公交规划' }}
            </button>
        </div>

        <div class="status-line error" v-if="errorMsg">{{ errorMsg }}</div>
        <div class="status-line" v-else-if="pickMode === 'start'">请在主地图上单击一个位置设置起点</div>
        <div class="status-line" v-else-if="pickMode === 'end'">请在主地图上单击一个位置设置终点</div>

        <details class="debug-box">
            <summary>调试信息</summary>
            <div class="debug-row"><span>请求状态：</span><span>{{ debugInfo.status }}</span></div>
            <div class="debug-row"><span>resultCode：</span><span>{{ debugInfo.resultCode || '-' }}</span></div>
            <div class="debug-row"><span>分组数量：</span><span>{{ debugInfo.groupCount }}</span></div>
            <div class="debug-row"><span>线路数量：</span><span>{{ debugInfo.lineCount }}</span></div>
            <div class="debug-row"><span>请求URL：</span><span class="debug-text">{{ debugInfo.requestUrl || '未发起请求' }}</span></div>
            <div class="debug-row"><span>响应结构：</span><span class="debug-text">{{ debugInfo.responseShape || '-' }}</span></div>
            <div class="debug-row"><span>候选数量：</span><span>{{ debugInfo.candidateCount }}</span></div>
            <div class="debug-row"><span>提示：</span><span class="debug-text">{{ debugInfo.message || '-' }}</span></div>
        </details>

        <div class="planner-main">
            <aside class="planner-list-panel">
                <div class="route-title">候选路线</div>

                <div v-if="routes.length === 0" class="route-empty">
                    先在主地图设置起终点并点击开始公交规划
                </div>

                <button
                    v-for="(route, idx) in routes"
                    :key="route.id"
                    type="button"
                    class="route-card"
                    :class="selectedRouteIndex === idx ? 'route-card-active' : ''"
                    @click="handleSelectRoute(route, idx)"
                >
                    <div class="route-head">
                        <div class="route-name">{{ route.lineName }}</div>
                        <span class="route-tag">方案 {{ idx + 1 }}</span>
                    </div>
                    <div class="route-meta">
                        <span>时长：{{ route.time }} 分钟</span>
                        <span>里程：{{ route.distanceKm }} km</span>
                    </div>
                </button>
            </aside>

            <aside class="planner-list-panel">
                <div class="route-title">导航步骤</div>

                <div v-if="!selectedRoute" class="route-empty">
                    选择一个候选方案后，可查看每个分段的起点、终点和路段名称
                </div>

                <button
                    v-for="(step, stepIndex) in selectedRoute?.steps || []"
                    :key="`${selectedRoute?.id || 'route'}_${stepIndex}`"
                    type="button"
                    class="step-card"
                    :class="selectedStepIndex === stepIndex ? 'step-card-active' : ''"
                    @mouseenter="handlePreviewStep(stepIndex)"
                    @mouseleave="clearStepPreview"
                    @click="handleSelectStep(stepIndex)"
                >
                    <div class="step-head">
                        <span class="step-tag">步骤 {{ stepIndex + 1 }}</span>
                        <span class="step-distance">{{ step.distanceKm }} km</span>
                    </div>
                    <div class="step-line">{{ step.segmentName }}</div>
                    <div class="step-stations">{{ step.startName }} -> {{ step.endName }}</div>
                    <div class="step-meta">
                        <span>{{ step.modeText }}</span>
                        <span>{{ step.time }} 分钟</span>
                    </div>
                </button>

                <div v-if="selectedRoute && (!selectedRoute.steps || selectedRoute.steps.length === 0)" class="route-empty">
                    当前方案未返回可展示的分段步骤
                </div>
            </aside>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import MapPointPickerCard from './MapPointPickerCard.vue';
import { useMessage } from '../composables/useMessage';
import { locationToAddress } from '../api';
import { showLoading, hideLoading } from '../utils/loading';

const message = useMessage();


interface TransitStation {
    name: string;
    lonlat: string;
}

interface TransitSegmentLine {
    linePoint: string;
    lineName: string;
    segmentTime?: number | string;
    segmentDistance?: number | string;
}

interface TransitSegment {
    segmentType: 1 | 2 | number;
    stationStart: TransitStation;
    stationEnd: TransitStation;
    segmentLine: TransitSegmentLine[];
}

interface TransitLine {
    lineName?: string;
    segments: TransitSegment[];
}

interface TransitResultGroup {
    lineType?: string | number;
    lines?: TransitLine[];
}

interface TransitResponse {
    resultCode?: string | number;
    msg?: string;
    message?: string;
    results?: TransitResultGroup[];
}

interface StepInfo {
    index: number;
    segmentType: number;
    modeText: string;
    segmentName: string;
    startName: string;
    endName: string;
    time: number;
    distanceKm: string;
}

interface RouteCandidate {
    id: string;
    lineName: string;
    time: number;
    distanceKm: string;
    segments: TransitSegment[];
    steps: StepInfo[];
}

const props = defineProps<{
    token: string;
    startBusPointPick?: (type: 'start' | 'end') => Promise<{ lng: number; lat: number } | null>;
    drawRouteOnMap?: (route: RouteCandidate) => Promise<void> | void;
    zoomToBusRouteStep?: (stepIndex: number) => Promise<void> | void;
    previewBusRouteStep?: (stepIndex: number) => Promise<void> | void;
    clearBusRouteStepPreview?: () => Promise<void> | void;
}>();

defineEmits(['close']);

const errorMsg = ref('');
const pickMode = ref<'start' | 'end' | ''>('');
const startPoint = ref<{ lng: number; lat: number } | undefined>(undefined);
const endPoint = ref<{ lng: number; lat: number } | undefined>(undefined);
const startAddress = ref('');
const endAddress = ref('');
const lineType = ref('1');
const planning = ref(false);
const routes = ref<RouteCandidate[]>([]);
const selectedRouteIndex = ref(-1);
const selectedStepIndex = ref(-1);
const debugInfo = ref({
    status: 'idle',
    requestUrl: '',
    responseShape: '',
    candidateCount: 0,
    message: '',
    resultCode: '',
    groupCount: 0,
    lineCount: 0
});

const selectedRoute = computed<RouteCandidate | null>(() => {
    const idx = Number(selectedRouteIndex.value);
    if (idx < 0 || idx >= routes.value.length) return null;
    return routes.value[idx] || null;
});

function parseSegmentMetrics(segment: TransitSegment) {
    const firstLine = Array.isArray(segment?.segmentLine) ? segment.segmentLine[0] : undefined;
    const t = Number(firstLine?.segmentTime ?? 0);
    const d = Number(firstLine?.segmentDistance ?? 0);
    return {
        time: Number.isFinite(t) ? t : 0,
        distance: Number.isFinite(d) ? d : 0
    };
}

function resolveStationName(name: string | undefined, type: 'start' | 'end', index: number, total: number): string {
    const normalized = String(name || '').trim();
    if (normalized) return normalized;

    if (type === 'start' && index === 0) return '起点';
    if (type === 'end' && index === total - 1) return '终点';
    return '途经点';
}

function getSegmentDisplayName(segment: TransitSegment, stepIndex: number): string {
    const firstLine = Array.isArray(segment?.segmentLine) ? segment.segmentLine[0] : undefined;
    const lineName = String(firstLine?.lineName || '').trim();
    if (Number(segment?.segmentType ?? 0) === 1) {
        return lineName || '步行';
    }
    return lineName || `公交段 ${stepIndex + 1}`;
}

function normalizeTransitResults(raw: TransitLine[]): RouteCandidate[] {
    if (!Array.isArray(raw)) return [];

    return raw.map((item, idx) => {
        const segmentList = Array.isArray(item?.segments) ? item.segments : [];
        const total = segmentList.reduce((acc, segment) => {
            const metrics = parseSegmentMetrics(segment);
            return {
                time: acc.time + metrics.time,
                distance: acc.distance + metrics.distance
            };
        }, { time: 0, distance: 0 });

        const lineName = String(item?.lineName || '').replace(/\s*\|\s*$/, '').trim() || `方案 ${idx + 1}`;
        const steps: StepInfo[] = segmentList.map((segment, segmentIndex) => {
            const firstLine = Array.isArray(segment?.segmentLine) ? segment.segmentLine[0] : undefined;
            const metrics = parseSegmentMetrics(segment);
            const segmentType = Number(segment?.segmentType ?? 0);
            const startName = resolveStationName(segment?.stationStart?.name, 'start', segmentIndex, segmentList.length);
            const endName = resolveStationName(segment?.stationEnd?.name, 'end', segmentIndex, segmentList.length);
            const segmentName = getSegmentDisplayName(segment, segmentIndex);

            return {
                index: segmentIndex,
                segmentType,
                modeText: segmentType === 1 ? '步行' : '公交',
                segmentName,
                startName,
                endName,
                time: Math.round(metrics.time),
                distanceKm: (metrics.distance / 1000).toFixed(2)
            };
        });

        return {
            id: `${idx}_${lineName}`,
            lineName,
            time: Math.round(total.time),
            distanceKm: (total.distance / 1000).toFixed(2),
            segments: segmentList,
            steps
        };
    });
}

function extractLinesFromTransitResponse(data: TransitResponse) {
    const groups = Array.isArray(data?.results) ? data.results : [];
    const allLines: TransitLine[] = [];

    groups.forEach((group) => {
        const lines = Array.isArray(group?.lines) ? group.lines : [];
        lines.forEach((line) => allLines.push(line));
    });

    return {
        groups,
        lines: allLines
    };
}

async function enablePick(type: 'start' | 'end') {
    if (!props.startBusPointPick) {
        errorMsg.value = '主地图未就绪，无法选点';
        return;
    }

    pickMode.value = type;
    errorMsg.value = '';

    try {
        const point = await props.startBusPointPick(type);
        if (!point) return;
        if (type === 'start') {
            startPoint.value = point;
        } else {
            endPoint.value = point;
        }

        try {
            const reverse = await locationToAddress(point.lng, point.lat, 'base');
            const label = String(reverse?.formattedAddress || '').trim();
            if (type === 'start') {
                startAddress.value = label;
            } else {
                endAddress.value = label;
            }
        } catch {
            if (type === 'start') {
                startAddress.value = '';
            } else {
                endAddress.value = '';
            }
        }
    } catch (err: any) {
        errorMsg.value = err?.message || '地图选点失败';
    } finally {
        pickMode.value = '';
    }
}

async function handleSelectRoute(route: RouteCandidate, idx: number) {
    selectedRouteIndex.value = idx;
    selectedStepIndex.value = -1;

    if (!props.drawRouteOnMap) return;

    try {
        await props.drawRouteOnMap(route);
    } catch (err: any) {
        errorMsg.value = err?.message || '路线绘制失败';
    }
}

async function handleSelectStep(stepIndex: number) {
    selectedStepIndex.value = stepIndex;

    try {
        if (props.drawRouteOnMap && selectedRoute.value) {
            await props.drawRouteOnMap(selectedRoute.value);
        }
        if (!props.zoomToBusRouteStep) return;
        await props.zoomToBusRouteStep(stepIndex);
    } catch (err: any) {
        errorMsg.value = err?.message || `无法定位步骤 ${stepIndex + 1}`;
    }
}

async function handlePreviewStep(stepIndex: number) {
    try {
        if (!props.previewBusRouteStep) return;
        await props.previewBusRouteStep(stepIndex);
    } catch {
        // 预览失败不影响主流程
    }
}

async function clearStepPreview() {
    try {
        if (!props.clearBusRouteStepPreview) return;
        await props.clearBusRouteStepPreview();
    } catch {
        // 预览失败不影响主流程
    }
}

async function startTransitPlan() {
    if (!startPoint.value || !endPoint.value) {
        errorMsg.value = '请先设置起点和终点';
        return;
    }

    planning.value = true;
    showLoading('正在规划公交路线...');
    errorMsg.value = '';
    debugInfo.value = {
        status: 'requesting',
        requestUrl: '',
        responseShape: '',
        candidateCount: 0,
        message: '',
        resultCode: '',
        groupCount: 0,
        lineCount: 0
    };

    try {
        const postObj = {
            startposition: `${startPoint.value.lng},${startPoint.value.lat}`,
            endposition: `${endPoint.value.lng},${endPoint.value.lat}`,
            linetype: String(lineType.value)
        };

        const encodedPostStr = encodeURIComponent(JSON.stringify(postObj));
        const requestUrl = `https://api.tianditu.gov.cn/transit?tk=${encodeURIComponent(props.token)}&type=busplan&postStr=${encodedPostStr}`;
        debugInfo.value.requestUrl = requestUrl;

        const res = await fetch(requestUrl, { method: 'GET' });
        debugInfo.value.status = `http ${res.status}`;
        if (!res.ok) {
            throw new Error(`公交规划请求失败: ${res.status}`);
        }

        const data = await res.json() as TransitResponse;
        const shapeKeys = data && typeof data === 'object' ? Object.keys(data).slice(0, 8).join(', ') : typeof data;
        const extracted = extractLinesFromTransitResponse(data);
        const normalized = normalizeTransitResults(extracted.lines);

        debugInfo.value.responseShape = shapeKeys || '-';
        debugInfo.value.candidateCount = normalized.length;
        debugInfo.value.message = data?.msg || data?.message || '';
        debugInfo.value.resultCode = String(data?.resultCode ?? '');
        debugInfo.value.groupCount = extracted.groups.length;
        debugInfo.value.lineCount = extracted.lines.length;

        routes.value = normalized;
        selectedRouteIndex.value = normalized.length ? 0 : -1;
        selectedStepIndex.value = -1;

        if (normalized.length && props.drawRouteOnMap) {
            await props.drawRouteOnMap(normalized[0]);
        }

        if (!normalized.length) {
            errorMsg.value = '未查询到可用公交方案';
            debugInfo.value.status = 'empty';
            if (Number(data?.resultCode) !== 0) {
                debugInfo.value.message = `resultCode=${data?.resultCode}`;
            }
        }
    } catch (err: any) {
        const rawMessage = err?.message || '';
        const likelyNetworkBlocked = err instanceof TypeError || /failed\s+to\s+fetch/i.test(String(rawMessage));
        const hint = likelyNetworkBlocked
            ? '网络请求被浏览器拦截或跨域失败。请确认：1) 部署站点使用 https；2) 天地图 token 已绑定当前域名；3) 浏览器控制台无 Mixed Content/CORS 报错。'
            : '';
        errorMsg.value = hint || rawMessage || '公交规划失败';
        routes.value = [];
        selectedRouteIndex.value = -1;
        selectedStepIndex.value = -1;
        debugInfo.value.status = 'error';
        debugInfo.value.message = hint || rawMessage || '公交规划失败';
        message.error(errorMsg.value);
    } finally {
        planning.value = false;
        hideLoading();
    }
}
</script>

<style scoped>
.bus-planner-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 14px;
    background:
        radial-gradient(140% 90% at 0% 0%, rgba(139, 209, 124, 0.12), rgba(139, 209, 124, 0) 58%),
        var(--glass-bg-heavy);
    gap: 12px;
    color: var(--text-primary);
}

.panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 2px 2px 0;
}

.title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0;
    color: var(--text-primary);
}

.title-sub {
    margin-top: 2px;
    font-size: 11px;
    color: var(--text-muted);
    letter-spacing: 0;
    text-transform: uppercase;
}

.ghost-btn {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-full);
    background: rgba(139, 209, 124, 0.08);
    color: var(--text-secondary);
    padding: 6px 12px;
    font-size: 12px;
    transition: all var(--duration-fast) var(--ease-spatial);
    cursor: pointer;
}

.ghost-btn:hover {
    background: rgba(139, 209, 124, 0.16);
    border-color: rgba(139, 209, 124, 0.32);
    color: var(--neon-green);
    transform: translateY(-1px);
}

.plan-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: var(--surface-0);
}

.plan-label {
    font-size: 12px;
    color: var(--text-muted);
    white-space: nowrap;
}

.plan-select {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 7px 8px;
    background: rgba(5, 11, 10, 0.54);
    color: var(--text-primary);
    outline: none;
}

.plan-btn {
    border: 1px solid rgba(139, 209, 124, 0.36);
    border-radius: var(--radius-sm);
    background: var(--neon-green-dim);
    color: var(--neon-green);
    padding: 8px 12px;
    cursor: pointer;
    font-weight: 600;
    white-space: nowrap;
    box-shadow: none;
    transition: transform var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        background var(--duration-fast) var(--ease-spatial);
}

.plan-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: var(--neon-green-glow);
    background: rgba(139, 209, 124, 0.2);
}

.plan-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.status-line {
    font-size: 12px;
    color: var(--text-secondary);
}

.status-line.error {
    color: var(--accent-rose);
}

.debug-box {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: var(--surface-0);
    padding: 6px 8px;
    font-size: 12px;
}

.debug-box summary {
    cursor: pointer;
    color: var(--neon-green);
    font-weight: 600;
}

.debug-row {
    margin-top: 4px;
    color: var(--text-secondary);
    display: grid;
    grid-template-columns: 64px 1fr;
    gap: 6px;
}

.debug-text {
    word-break: break-all;
}

.planner-main {
    flex: 1;
    min-height: 220px;
    display: flex;
    gap: 8px;
}

.planner-list-panel {
    width: 100%;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: rgba(5, 11, 10, 0.28);
    padding: 8px;
    overflow-y: auto;
}

.route-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--neon-green);
    margin: 2px 2px 8px;
}

.route-card {
    width: 100%;
    text-align: left;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: rgba(139, 209, 124, 0.08);
    padding: 10px;
    margin-bottom: 8px;
    transition: all var(--duration-fast) var(--ease-spatial);
    color: var(--text-secondary);
}

.route-card:hover {
    border-color: rgba(139, 209, 124, 0.32);
    background: rgba(139, 209, 124, 0.15);
    transform: translateY(-1px);
}

.route-card-active {
    border-color: rgba(139, 209, 124, 0.5);
    background: rgba(139, 209, 124, 0.18);
    box-shadow: var(--neon-green-glow);
}

.route-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 6px;
}

.route-name {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.35;
}

.route-tag {
    flex-shrink: 0;
    border-radius: var(--radius-full);
    border: 1px solid rgba(139, 209, 124, 0.28);
    background: rgba(139, 209, 124, 0.1);
    color: var(--neon-green);
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}

.route-meta {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
}

.route-empty {
    font-size: 12px;
    color: var(--text-muted);
    line-height: 1.6;
}

.step-card {
    width: 100%;
    text-align: left;
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
    background: rgba(71, 215, 198, 0.08);
    padding: 10px;
    margin-bottom: 8px;
    transition: all var(--duration-fast) var(--ease-spatial);
    color: var(--text-secondary);
}

.step-card:hover {
    border-color: var(--border-active);
    background: rgba(71, 215, 198, 0.15);
    transform: translateY(-1px);
}

.step-card-active {
    border-color: var(--border-glow);
    background: var(--neon-cyan-dim);
    box-shadow: var(--neon-cyan-glow);
}

.step-head {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: center;
}

.step-tag {
    border-radius: var(--radius-full);
    border: 1px solid var(--border-active);
    background: rgba(71, 215, 198, 0.1);
    color: var(--neon-cyan);
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}

.step-distance {
    font-size: 12px;
    color: var(--text-secondary);
    font-weight: 600;
}

.step-line {
    margin-top: 7px;
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.35;
}

.step-stations {
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-secondary);
}

.step-meta {
    margin-top: 6px;
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    color: var(--text-secondary);
}

@media (max-width: 860px) {
    .plan-row {
        flex-wrap: wrap;
    }

    .plan-select {
        min-width: 100%;
    }

    .plan-btn {
        width: 100%;
    }

    .planner-main {
        flex-direction: column;
    }
}
</style>
