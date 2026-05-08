<template>
    <div class="api-management-container">
        <div class="management-header">
            <h1>API 管理后台</h1>
            <p class="subtitle">查看和管理用户 API 调用统计与配额</p>
        </div>

        <!-- 标签页导航 -->
        <div class="tabs-nav">
            <button
                v-for="tab in tabs"
                :key="tab.id"
                class="tab-btn"
                :class="{ active: activeTab === tab.id }"
                @click="activeTab = tab.id"
            >
                <component :is="tab.icon" :size="15" />
                {{ tab.label }}
            </button>
        </div>

        <!-- 标签页内容 -->
        <div class="tabs-content">
            <!-- 1. 用户 API 使用统计 -->
            <div v-show="activeTab === 'by-user'" class="tab-panel">
                <div class="panel-header">
                    <h2>用户 API 调用统计</h2>
                    <div class="filter-controls">
                        <label>统计天数：</label>
                        <select v-model.number="userStatsFilter.days" @change="loadUserStats">
                            <option :value="7">最近 7 天</option>
                            <option :value="30">最近 30 天</option>
                            <option :value="90">最近 90 天</option>
                        </select>
                    </div>
                </div>

                <div v-if="loadingUserStats" class="loading-state">
                    <span class="spinner"></span> 加载中...
                </div>

                <div v-else-if="userStats.length > 0" class="data-table-shell">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>用户名</th>
                                <th>角色</th>
                                <th>调用次数</th>
                                <th>活跃天数</th>
                                <th>平均响应时间</th>
                                <th>最后调用</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(stat, idx) in userStats" :key="idx" class="data-row">
                                <td class="username">{{ stat.username }}</td>
                                <td>
                                    <span class="role-badge" :class="getRoleClass(stat.role)">
                                        {{ stat.role || 'unknown' }}
                                    </span>
                                </td>
                                <td class="highlight">{{ stat.call_count }}</td>
                                <td>{{ stat.active_days }}</td>
                                <td>{{ stat.avg_response_time_ms?.toFixed(2) || 'N/A' }} ms</td>
                                <td class="timestamp">{{ formatTime(stat.last_called_at) }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <div v-else class="empty-state">暂无数据</div>
            </div>

            <!-- 2. API 端点使用统计 -->
            <div v-show="activeTab === 'by-endpoint'" class="tab-panel">
                <div class="panel-header">
                    <h2>API 端点调用统计</h2>
                    <div class="filter-controls">
                        <label>统计天数：</label>
                        <select v-model.number="endpointStatsFilter.days" @change="loadEndpointStats">
                            <option :value="7">最近 7 天</option>
                            <option :value="30">最近 30 天</option>
                            <option :value="90">最近 90 天</option>
                        </select>
                    </div>
                </div>

                <div v-if="loadingEndpointStats" class="loading-state">
                    <span class="spinner"></span> 加载中...
                </div>

                <div v-else-if="endpointStats.length > 0" class="data-table-shell">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>API 端点</th>
                                <th>调用次数</th>
                                <th>成功</th>
                                <th>错误</th>
                                <th>成功率</th>
                                <th>平均响应时间</th>
                                <th>最大/最小响应时间</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(stat, idx) in endpointStats" :key="idx" class="data-row">
                                <td class="endpoint-name">{{ formatEndpoint(stat.api_endpoint) }}</td>
                                <td class="highlight">{{ stat.call_count }}</td>
                                <td class="success">{{ stat.success_count }}</td>
                                <td class="error">{{ stat.error_count }}</td>
                                <td class="percentage">
                                    {{ calcSuccessRate(stat.success_count, stat.call_count) }}%
                                </td>
                                <td>{{ stat.avg_response_time_ms?.toFixed(2) || 'N/A' }} ms</td>
                                <td class="response-range">
                                    {{ stat.max_response_time_ms?.toFixed(0) || 'N/A' }} /
                                    {{ stat.min_response_time_ms?.toFixed(0) || 'N/A' }} ms
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
                <div v-else class="empty-state">暂无数据</div>
            </div>

            <!-- 3. API 调用日志 -->
            <div v-show="activeTab === 'logs'" class="tab-panel">
                <div class="panel-header">
                    <h2>API 调用日志</h2>
                    <div class="filter-controls">
                        <input
                            v-model="logsFilter.username"
                            type="text"
                            placeholder="按用户名过滤..."
                            @change="resetLogsAndLoad"
                        />
                        <input
                            v-model="logsFilter.endpoint"
                            type="text"
                            placeholder="按 API 端点过滤..."
                            @change="resetLogsAndLoad"
                        />
                        <select v-model.number="logsFilter.days" @change="resetLogsAndLoad">
                            <option :value="7">最近 7 天</option>
                            <option :value="30">最近 30 天</option>
                            <option :value="90">最近 90 天</option>
                        </select>
                        <button class="btn-refresh" @click="loadLogs">
                            <refresh-cw-icon :size="14" />
                            刷新
                        </button>
                    </div>
                </div>

                <div v-if="loadingLogs" class="loading-state">
                    <span class="spinner"></span> 加载中...
                </div>

                <div v-else-if="apiLogs.length > 0" class="data-table-shell">
                    <table class="data-table logs-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>用户</th>
                                <th>角色</th>
                                <th>API 端点</th>
                                <th>状态码</th>
                                <th>响应时间</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="(log, idx) in apiLogs" :key="idx" class="data-row">
                                <td class="timestamp">{{ formatTime(log.timestamp) }}</td>
                                <td>{{ log.username }}</td>
                                <td>
                                    <span class="role-badge" :class="getRoleClass(log.role)">
                                        {{ log.role || 'unknown' }}
                                    </span>
                                </td>
                                <td class="endpoint-name">{{ formatEndpoint(log.api_endpoint) }}</td>
                                <td>
                                    <span class="status-code" :class="getStatusClass(log.status_code)">
                                        {{ log.status_code }}
                                    </span>
                                </td>
                                <td>{{ log.response_time_ms?.toFixed(2) || 'N/A' }} ms</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- 分页控制 -->
                <div v-if="!loadingLogs && apiLogs.length > 0" class="pagination">
                    <button
                        class="btn-paging"
                        :disabled="logsFilter.offset === 0"
                        @click="moveLogsPage(-1)"
                    >
                        ← 上一页
                    </button>
                    <span class="page-info">
                        第 {{ (logsFilter.offset / logsFilter.limit) + 1 }} 页
                        (显示 {{ apiLogs.length }} 条)
                    </span>
                    <button
                        class="btn-paging"
                        :disabled="apiLogs.length < logsFilter.limit"
                        @click="moveLogsPage(1)"
                    >
                        下一页 →
                    </button>
                </div>

                <div v-if="!loadingLogs && apiLogs.length === 0" class="empty-state">暂无数据</div>
            </div>

            <!-- 4. 配额配置 -->
            <div v-show="activeTab === 'quota'" class="tab-panel">
                <div class="panel-header">
                    <h2>API 配额配置</h2>
                </div>

                <div v-if="loadingQuota" class="loading-state">
                    <span class="spinner"></span> 加载中...
                </div>

                <div v-else class="quota-grid">
                    <div v-for="(config, role) in quotaConfig" :key="role" class="quota-card">
                        <div class="quota-header">
                            <h3>{{ getRoleLabel(role) }}</h3>
                            <span class="role-badge" :class="role.toLowerCase()">{{ role }}</span>
                        </div>
                        <div class="quota-body">
                            <div class="quota-item">
                                <label>每日限额：</label>
                                <span class="quota-value">
                                    {{ config.daily_limit === null ? '无限制' : `${config.daily_limit} 次` }}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="quota-note">
                    <strong>说明：</strong> 配额通过后端环境变量配置，如需修改请编辑
                    <code>GUEST_DAILY_API_QUOTA</code>、<code>REGISTERED_DAILY_API_QUOTA</code>
                    环境变量后重启后端服务。
                </div>
            </div>

            <!-- 5. API 密钥管理 -->
            <div v-show="activeTab === 'api-keys'" class="tab-panel">
                <ApiKeysManagementPanel />
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { apiAdminApiUsageByUser, apiAdminApiUsageByEndpoint, apiAdminApiLogs, apiAdminQuotaConfig } from '../../api/backend';
import { useMessage } from '../../composables/useMessage';
import ApiKeysManagementPanel from './ApiKeysManagementPanel.vue';
import {
    BarChart3 as BarChart3Icon,
    Gauge as GaugeIcon,
    KeyRound as KeyRoundIcon,
    Link2 as Link2Icon,
    RefreshCw as RefreshCwIcon,
    ScrollText as ScrollTextIcon,
} from 'lucide-vue-next';

const message = useMessage();

const activeTab = ref('by-user');
const tabs = [
    { id: 'by-user', label: '用户统计', icon: BarChart3Icon },
    { id: 'by-endpoint', label: '端点统计', icon: Link2Icon },
    { id: 'logs', label: '调用日志', icon: ScrollTextIcon },
    { id: 'quota', label: '配额配置', icon: GaugeIcon },
    { id: 'api-keys', label: '密钥管理', icon: KeyRoundIcon },
];

// 用户统计
const userStats = ref([]);
const loadingUserStats = ref(false);
const userStatsFilter = ref({ days: 7 });

// 端点统计
const endpointStats = ref([]);
const loadingEndpointStats = ref(false);
const endpointStatsFilter = ref({ days: 7 });

// API 日志
const apiLogs = ref([]);
const loadingLogs = ref(false);
const logsFilter = ref({
    username: '',
    endpoint: '',
    days: 7,
    limit: 50,
    offset: 0,
});

// 配额配置
const quotaConfig = ref({});
const loadingQuota = ref(false);

function formatTime(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    } catch (e) {
        return isoString;
    }
}

function formatEndpoint(endpoint) {
    if (!endpoint) return 'N/A';
    // 提取最后的部分
    const parts = endpoint.split('/');
    return parts.slice(-2).join('/') || endpoint;
}

function calcSuccessRate(successCount, totalCount) {
    if (totalCount === 0) return '0';
    return ((successCount / totalCount) * 100).toFixed(1);
}

function getStatusClass(statusCode) {
    if (statusCode >= 200 && statusCode < 300) return 'success';
    if (statusCode >= 400 && statusCode < 500) return 'client-error';
    if (statusCode >= 500) return 'server-error';
    return 'info';
}

function getRoleLabel(role) {
    const labels = {
        guest: '游客',
        registered: '注册用户',
        admin: '管理员',
    };
    return labels[role] || role;
}

function getRoleClass(role) {
    return String(role || 'unknown').toLowerCase();
}

async function loadUserStats() {
    loadingUserStats.value = true;
    try {
        const result = await apiAdminApiUsageByUser(userStatsFilter.value.days, 100);
        userStats.value = result?.data || [];
    } catch (error) {
        message.error(`加载用户统计失败: ${error.message}`);
    } finally {
        loadingUserStats.value = false;
    }
}

async function loadEndpointStats() {
    loadingEndpointStats.value = true;
    try {
        const result = await apiAdminApiUsageByEndpoint(endpointStatsFilter.value.days, 50);
        endpointStats.value = result?.data || [];
    } catch (error) {
        message.error(`加载端点统计失败: ${error.message}`);
    } finally {
        loadingEndpointStats.value = false;
    }
}

async function loadLogs() {
    loadingLogs.value = true;
    try {
        const result = await apiAdminApiLogs(
            logsFilter.value.limit,
            logsFilter.value.offset,
            logsFilter.value.username || undefined,
            logsFilter.value.endpoint || undefined,
            logsFilter.value.days,
        );
        apiLogs.value = result?.data || [];
    } catch (error) {
        message.error(`加载日志失败: ${error.message}`);
    } finally {
        loadingLogs.value = false;
    }
}

async function resetLogsAndLoad() {
    logsFilter.value.offset = 0;
    await loadLogs();
}

async function moveLogsPage(direction) {
    const nextOffset = Math.max(
        0,
        logsFilter.value.offset + direction * logsFilter.value.limit,
    );
    if (nextOffset === logsFilter.value.offset) return;
    logsFilter.value.offset = nextOffset;
    await loadLogs();
}

async function loadQuotaConfig() {
    loadingQuota.value = true;
    try {
        const result = await apiAdminQuotaConfig();
        quotaConfig.value = result?.data || {};
    } catch (error) {
        message.error(`加载配额配置失败: ${error.message}`);
    } finally {
        loadingQuota.value = false;
    }
}

onMounted(async () => {
    await loadUserStats();
    await loadEndpointStats();
    await loadLogs();
    await loadQuotaConfig();
});
</script>

<style scoped>
.api-management-container {
    width: 100%;
    min-width: 0;
    color: var(--text-primary);
}

.management-header {
    display: none;
}

.tabs-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
    padding: 8px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    background: var(--surface-card);
    box-shadow: var(--shadow-button);
}

.tab-btn {
    min-height: 38px;
    padding: 0 13px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    color: var(--text-secondary);
    background: var(--surface-1);
    cursor: pointer;
    font-size: 13px;
    font-weight: 700;
    transition:
        background var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
}

.tab-btn:hover {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--surface-hover);
    transform: translateY(-1px);
}

.tab-btn.active {
    color: var(--neon-cyan);
    border-color: var(--border-glow);
    background: var(--neon-cyan-dim);
    box-shadow: var(--neon-cyan-glow);
}

.tab-btn:focus-visible,
.btn-refresh:focus-visible,
.btn-paging:focus-visible,
.filter-controls select:focus-visible,
.filter-controls input:focus-visible {
    outline: none;
    box-shadow: var(--shadow-focus);
}

.tabs-content {
    min-width: 0;
}

.tab-panel {
    min-width: 0;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 14px;
    background: var(--surface-card);
    box-shadow: var(--shadow-panel);
}

.panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
}

.panel-header h2 {
    margin: 0;
    font-size: 16px;
    line-height: 1.35;
    color: var(--text-primary);
    font-weight: 700;
}

.filter-controls {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
}

.filter-controls label {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 600;
}

.filter-controls select,
.filter-controls input {
    min-height: 38px;
    min-width: 132px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 0 10px;
    color: var(--text-primary);
    background: rgba(6, 11, 16, 0.62);
    box-sizing: border-box;
    font-size: 13px;
    transition: border-color var(--duration-fast) var(--ease-spatial), box-shadow var(--duration-fast) var(--ease-spatial), background var(--duration-fast) var(--ease-spatial);
}

.filter-controls input::placeholder {
    color: var(--text-muted);
}

.filter-controls select:focus,
.filter-controls input:focus {
    outline: none;
    border-color: var(--border-active);
    background: var(--surface-card-strong);
    box-shadow: var(--shadow-focus);
}

.filter-controls select option {
    background: var(--deep-2);
    color: var(--text-primary);
}

.btn-refresh {
    min-height: 38px;
    padding: 0 13px;
    border: 1px solid var(--border-active);
    border-radius: var(--radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    color: var(--neon-cyan);
    background: var(--neon-cyan-dim);
    cursor: pointer;
    font-size: 13px;
    font-weight: 750;
    transition: transform var(--duration-fast) var(--ease-spatial), box-shadow var(--duration-fast) var(--ease-spatial), background var(--duration-fast) var(--ease-spatial);
}

.btn-refresh:hover {
    transform: translateY(-1px);
    background: var(--surface-hover);
    box-shadow: var(--neon-cyan-glow);
}

.data-table-shell {
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    background: var(--surface-1);
    box-shadow: var(--shadow-button);
}

.data-table {
    width: 100%;
    min-width: 760px;
    border-collapse: collapse;
    font-size: 13px;
    background: transparent;
}

.logs-table {
    min-width: 900px;
}

.data-table thead {
    background: var(--neon-cyan-dim);
    border-bottom: 1px solid var(--border-active);
}

.data-table th {
    padding: 12px;
    text-align: left;
    font-weight: 700;
    color: var(--neon-cyan);
    white-space: nowrap;
}

.data-table td {
    padding: 12px;
    border-bottom: 1px solid var(--border-subtle);
    color: var(--text-secondary);
    vertical-align: middle;
}

.data-table tbody tr:last-child td {
    border-bottom: none;
}

.data-row {
    transition: background var(--duration-fast) var(--ease-spatial);
}

.data-row:hover {
    background: rgba(71, 215, 198, 0.06);
}

.username {
    font-weight: 700;
    color: var(--text-primary);
}

.endpoint-name {
    display: inline-flex;
    max-width: 260px;
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 3px 7px;
    color: var(--text-primary);
    background: rgba(6, 11, 16, 0.42);
    font-family: Consolas, Monaco, 'Courier New', monospace;
    word-break: break-all;
}

.role-badge,
.status-code {
    display: inline-flex;
    min-height: 24px;
    align-items: center;
    justify-content: center;
    padding: 0 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 750;
    text-transform: uppercase;
    border: 1px solid transparent;
}

.role-badge.guest {
    color: var(--accent-blue);
    background: var(--accent-blue-dim);
    border-color: rgba(106, 169, 255, 0.28);
}

.role-badge.registered {
    color: var(--neon-cyan);
    background: var(--neon-cyan-dim);
    border-color: var(--border-active);
}

.role-badge.admin {
    color: var(--accent-amber);
    background: var(--accent-amber-dim);
    border-color: rgba(246, 173, 85, 0.3);
}

.highlight {
    color: var(--neon-cyan);
    font-weight: 800;
}

.timestamp,
.response-range {
    color: var(--text-muted);
    font-size: 12px;
    white-space: nowrap;
}

.success {
    color: var(--neon-green);
    font-weight: 700;
}

.error {
    color: var(--accent-rose);
    font-weight: 700;
}

.percentage {
    font-weight: 700;
    color: var(--text-primary);
}

.status-code.success {
    color: var(--neon-green);
    background: var(--neon-green-dim);
    border-color: rgba(22, 242, 179, 0.24);
}

.status-code.client-error {
    color: var(--accent-amber);
    background: var(--accent-amber-dim);
    border-color: rgba(246, 173, 85, 0.24);
}

.status-code.server-error {
    color: var(--accent-rose);
    background: var(--accent-rose-dim);
    border-color: rgba(245, 101, 101, 0.24);
}

.status-code.info {
    color: var(--accent-blue);
    background: var(--accent-blue-dim);
    border-color: rgba(106, 169, 255, 0.24);
}

.loading-state,
.empty-state {
    min-height: 128px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 10px;
    padding: 28px;
    border: 1px dashed var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    background: var(--surface-1);
    font-size: 13px;
    text-align: center;
}

.loading-state {
    display: flex;
}

.spinner {
    width: 18px;
    height: 18px;
    border: 2px solid var(--neon-cyan-dim);
    border-top: 2px solid var(--neon-cyan);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px solid var(--border-subtle);
}

.btn-paging {
    min-height: 34px;
    padding: 0 13px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    background: var(--surface-1);
    cursor: pointer;
    font-size: 13px;
    font-weight: 650;
    transition: background var(--duration-fast) var(--ease-spatial), border-color var(--duration-fast) var(--ease-spatial), color var(--duration-fast) var(--ease-spatial);
}

.btn-paging:hover:not(:disabled) {
    color: var(--neon-cyan);
    border-color: var(--border-active);
    background: var(--neon-cyan-dim);
}

.btn-paging:disabled {
    opacity: 0.48;
    cursor: not-allowed;
}

.page-info {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 600;
}

.quota-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 12px;
    margin-bottom: 14px;
}

.quota-card {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 14px;
    background: var(--surface-1);
    box-shadow: var(--shadow-button);
    transition: border-color var(--duration-fast) var(--ease-spatial), background var(--duration-fast) var(--ease-spatial);
}

.quota-card:hover {
    border-color: var(--border-active);
    background: var(--surface-hover);
}

.quota-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border-subtle);
}

.quota-header h3 {
    margin: 0;
    font-size: 15px;
    color: var(--text-primary);
}

.quota-body {
    display: grid;
    gap: 10px;
}

.quota-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
}

.quota-item label {
    color: var(--text-secondary);
    font-size: 13px;
}

.quota-value {
    font-size: 17px;
    font-weight: 800;
    color: var(--neon-cyan);
}

.quota-note {
    border: 1px solid rgba(246, 173, 85, 0.28);
    border-radius: var(--radius-sm);
    padding: 12px;
    color: var(--text-secondary);
    background: var(--accent-amber-dim);
    font-size: 13px;
    line-height: 1.6;
}

.quota-note strong {
    color: var(--accent-amber);
}

.quota-note code {
    display: inline-flex;
    margin: 0 2px;
    padding: 2px 6px;
    border-radius: 5px;
    color: var(--text-primary);
    background: rgba(6, 11, 16, 0.42);
    border: 1px solid var(--border-subtle);
    font-family: Consolas, Monaco, 'Courier New', monospace;
    font-weight: 700;
}

@media (max-width: 768px) {
    .tabs-nav {
        padding: 6px;
    }

    .tab-btn {
        flex: 1 1 calc(50% - 8px);
    }

    .tab-panel {
        padding: 12px;
    }

    .panel-header {
        flex-direction: column;
        align-items: flex-start;
    }

    .filter-controls {
        width: 100%;
        justify-content: flex-start;
    }

    .filter-controls select,
    .filter-controls input,
    .btn-refresh {
        width: 100%;
    }

    .data-table {
        font-size: 12px;
    }

    .quota-grid {
        grid-template-columns: 1fr;
    }
}
</style>
