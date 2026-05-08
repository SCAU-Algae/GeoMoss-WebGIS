<template>
    <div class="api-keys-container">
        <div class="keys-header">
            <h2>API 密钥管理</h2>
            <p class="subtitle">管理第三方 API 密钥，确保系统正常运行</p>
        </div>

        <!-- 密钥列表 -->
        <div class="keys-section">
            <div v-if="loading" class="loading-state">
                <span class="spinner"></span> 加载中...
            </div>

            <div v-else class="keys-grid">
                <!-- 高德地图 API Key -->
                <div class="key-card">
                    <div class="key-header">
                        <h3>高德地图 API Key</h3>
                        <span :class="['status-badge', keysStatus.amap_key?.is_set ? 'set' : 'unset']">
                            {{ keysStatus.amap_key?.is_set ? '已配置' : '未配置' }}
                        </span>
                    </div>
                    <div class="key-body">
                        <div v-if="editingKey === 'amap_key'" class="edit-form">
                            <textarea
                                v-model="editValues.amap_key"
                                placeholder="粘贴您的高德地图 Web 服务 API Key"
                                rows="3"
                                class="key-input"
                            ></textarea>
                            <div class="button-group">
                                <button class="btn btn-save" @click="saveKey('amap_key')">保存</button>
                                <button class="btn btn-cancel" @click="cancelEdit">取消</button>
                            </div>
                        </div>
                        <div v-else class="key-display">
                            <p class="key-value">
                                {{ keysStatus.amap_key?.is_set ? '**********(已设置)' : '未配置' }}
                            </p>
                            <div class="key-actions">
                                <button class="btn btn-edit" @click="startEdit('amap_key')">编辑</button>
                                <button
                                    v-if="keysStatus.amap_key?.is_set"
                                    class="btn btn-delete"
                                    @click="deleteKey('amap_key')"
                                >
                                    删除
                                </button>
                            </div>
                            <p class="key-hint">
                                如需获取密钥，访问
                                <a href="https://lbs.amap.com/api/webservice/guide/create-project/api-key" target="_blank">
                                    高德地图开放平台
                                </a>
                            </p>
                        </div>
                    </div>
                    <div class="key-footer">
                        最后更新: {{ formatTime(keysStatus.amap_key?.updated_at) }}
                    </div>
                </div>

                <!-- Agent 对话 API Key -->
                <div class="key-card">
                    <div class="key-header">
                        <h3>Agent 对话 API Key</h3>
                        <span :class="['status-badge', keysStatus.agent_api_key?.is_set ? 'set' : 'unset']">
                            {{ keysStatus.agent_api_key?.is_set ? '已配置' : '未配置' }}
                        </span>
                    </div>
                    <div class="key-body">
                        <div v-if="editingKey === 'agent_api_key'" class="edit-form">
                            <textarea
                                v-model="editValues.agent_api_key"
                                placeholder="粘贴您的 Agent 对话 API Key"
                                rows="3"
                                class="key-input"
                            ></textarea>
                            <div class="button-group">
                                <button class="btn btn-save" @click="saveKey('agent_api_key')">保存</button>
                                <button class="btn btn-cancel" @click="cancelEdit">取消</button>
                            </div>
                        </div>
                        <div v-else class="key-display">
                            <p class="key-value">
                                {{ keysStatus.agent_api_key?.is_set ? '**********(已设置)' : '未配置' }}
                            </p>
                            <div class="key-actions">
                                <button class="btn btn-edit" @click="startEdit('agent_api_key')">编辑</button>
                                <button
                                    v-if="keysStatus.agent_api_key?.is_set"
                                    class="btn btn-delete"
                                    @click="deleteKey('agent_api_key')"
                                >
                                    删除
                                </button>
                            </div>
                            <p class="key-hint">后端代理对话使用，仅管理员可配置</p>
                        </div>
                    </div>
                    <div class="key-footer">
                        最后更新: {{ formatTime(keysStatus.agent_api_key?.updated_at) }}
                    </div>
                </div>

                <!-- 天地图 API Key (可选) -->
                <div class="key-card">
                    <div class="key-header">
                        <h3>天地图 TK</h3>
                        <span :class="['status-badge', keysStatus.tianditu_tk?.is_set ? 'set' : 'unset']">
                            {{ keysStatus.tianditu_tk?.is_set ? '已配置' : '未配置' }}
                        </span>
                    </div>
                    <div class="key-body">
                        <div v-if="editingKey === 'tianditu_tk'" class="edit-form">
                            <textarea
                                v-model="editValues.tianditu_tk"
                                placeholder="粘贴您的天地图 API Key"
                                rows="3"
                                class="key-input"
                            ></textarea>
                            <div class="button-group">
                                <button class="btn btn-save" @click="saveKey('tianditu_tk')">保存</button>
                                <button class="btn btn-cancel" @click="cancelEdit">取消</button>
                            </div>
                        </div>
                        <div v-else class="key-display">
                            <p class="key-value">
                                {{ keysStatus.tianditu_tk?.is_set ? '**********(已设置)' : '未配置' }}
                            </p>
                            <div class="key-actions">
                                <button class="btn btn-edit" @click="startEdit('tianditu_tk')">编辑</button>
                                <button
                                    v-if="keysStatus.tianditu_tk?.is_set"
                                    class="btn btn-delete"
                                    @click="deleteKey('tianditu_tk')"
                                >
                                    删除
                                </button>
                            </div>
                            <p class="key-hint">
                                天地图底图 API 密钥（可选）
                            </p>
                        </div>
                    </div>
                    <div class="key-footer">
                        最后更新: {{ formatTime(keysStatus.tianditu_tk?.updated_at) }}
                    </div>
                </div>

                <!-- 千问视觉 API Key -->
                <div class="key-card">
                    <div class="key-header">
                        <h3>千问视觉 API Key</h3>
                        <span :class="['status-badge', keysStatus.dashscope_api_key?.is_set ? 'set' : 'unset']">
                            {{ keysStatus.dashscope_api_key?.is_set ? '已配置' : '未配置' }}
                        </span>
                    </div>
                    <div class="key-body">
                        <div v-if="editingKey === 'dashscope_api_key'" class="edit-form">
                            <textarea
                                v-model="editValues.dashscope_api_key"
                                placeholder="粘贴阿里云百炼 DashScope API Key"
                                rows="3"
                                class="key-input"
                            ></textarea>
                            <div class="button-group">
                                <button class="btn btn-save" @click="saveKey('dashscope_api_key')">保存</button>
                                <button class="btn btn-cancel" @click="cancelEdit">取消</button>
                            </div>
                        </div>
                        <div v-else class="key-display">
                            <p class="key-value">
                                {{ keysStatus.dashscope_api_key?.is_set ? '**********(已设置)' : '未配置' }}
                            </p>
                            <div class="key-actions">
                                <button class="btn btn-edit" @click="startEdit('dashscope_api_key')">编辑</button>
                                <button
                                    v-if="keysStatus.dashscope_api_key?.is_set"
                                    class="btn btn-delete"
                                    @click="deleteKey('dashscope_api_key')"
                                >
                                    删除
                                </button>
                            </div>
                            <p class="key-hint">
                                用于风水分析的遥感截图水体识别，后端调用千问视觉模型
                            </p>
                        </div>
                    </div>
                    <div class="key-footer">
                        最后更新: {{ formatTime(keysStatus.dashscope_api_key?.updated_at) }}
                    </div>
                </div>
            </div>
        </div>

        <div class="agent-config-section">
            <div class="section-header-row">
                <h3>Agent 对话参数</h3>
                <div class="section-actions">
                    <button class="btn btn-edit" @click="loadAgentConfig">刷新</button>
                    <button
                        v-if="!editingAgentConfig"
                        class="btn btn-edit"
                        @click="startEditAgentConfig"
                    >
                        编辑参数
                    </button>
                </div>
            </div>

            <div v-if="agentConfigLoading" class="loading-state">
                <span class="spinner"></span> 加载配置中...
            </div>

            <div v-else-if="editingAgentConfig" class="edit-form">
                <div class="config-grid">
                    <label class="config-item">
                        <span>Base URL</span>
                        <input v-model="agentConfigDraft.base_url" class="key-input" placeholder="https://api.xxx.com/v1" />
                    </label>
                    <label class="config-item">
                        <span>Model</span>
                        <input v-model="agentConfigDraft.model" class="key-input" placeholder="留空时按 available_models 随机调度" />
                    </label>
                    <label class="config-item config-item-full">
                        <span>Available Models（逗号或换行分隔）</span>
                        <textarea
                            v-model="agentConfigDraft.available_models_text"
                            rows="3"
                            class="key-input"
                            placeholder="qwen-plus\ndeepseek-chat\ngpt-4o-mini"
                        ></textarea>
                    </label>
                    <label class="config-item">
                        <span>Timeout (seconds)</span>
                        <input v-model.number="agentConfigDraft.timeout_seconds" type="number" min="5" max="180" class="key-input" />
                    </label>
                    <label class="config-item">
                        <span>Max Tokens</span>
                        <input v-model.number="agentConfigDraft.max_tokens" type="number" min="1" max="8192" class="key-input" />
                    </label>
                    <label class="config-item">
                        <span>Temperature</span>
                        <input v-model.number="agentConfigDraft.temperature" type="number" min="0" max="2" step="0.1" class="key-input" />
                    </label>
                    <label class="config-item">
                        <span>Guest 每日额度</span>
                        <input v-model.number="agentConfigDraft.guest_daily_quota" type="number" min="1" max="100000" class="key-input" />
                    </label>
                    <label class="config-item">
                        <span>Registered 每日额度</span>
                        <input v-model.number="agentConfigDraft.registered_daily_quota" type="number" min="1" max="100000" class="key-input" />
                    </label>
                    <label class="config-item config-item-full">
                        <span>System Prompt</span>
                        <textarea
                            v-model="agentConfigDraft.system_prompt"
                            rows="4"
                            class="key-input"
                            placeholder="用于后端统一注入的系统提示词"
                        ></textarea>
                    </label>
                </div>

                <div class="button-group">
                    <button class="btn btn-save" @click="saveAgentConfig">保存参数</button>
                    <button class="btn btn-edit" @click="resetChatQuota">恢复默认额度</button>
                    <button class="btn btn-cancel" @click="cancelEditAgentConfig">取消</button>
                </div>
            </div>

            <div v-else class="config-view">
                <div class="config-grid">
                    <div class="config-item">
                        <span>Base URL</span>
                        <strong>{{ agentConfig.base_url || '未配置' }}</strong>
                    </div>
                    <div class="config-item">
                        <span>Model</span>
                        <strong>{{ agentConfig.model || '未配置' }}</strong>
                    </div>
                    <div class="config-item config-item-full">
                        <span>Available Models</span>
                        <strong>{{ (agentConfig.available_models || []).join(', ') || '未配置' }}</strong>
                    </div>
                    <div class="config-item">
                        <span>Timeout</span>
                        <strong>{{ agentConfig.timeout_seconds || '-' }} 秒</strong>
                    </div>
                    <div class="config-item">
                        <span>Max Tokens</span>
                        <strong>{{ agentConfig.max_tokens || '-' }}</strong>
                    </div>
                    <div class="config-item">
                        <span>Temperature</span>
                        <strong>{{ agentConfig.temperature ?? '-' }}</strong>
                    </div>
                    <div class="config-item">
                        <span>Guest 每日额度</span>
                        <strong>{{ agentQuota.guest }}</strong>
                    </div>
                    <div class="config-item">
                        <span>Registered 每日额度</span>
                        <strong>{{ agentQuota.registered }}</strong>
                    </div>
                    <div class="config-item config-item-full">
                        <span>System Prompt</span>
                        <strong>{{ agentConfig.system_prompt || '未配置' }}</strong>
                    </div>
                </div>

                <p class="config-note">
                    对话额度：游客 {{ agentQuota.guest }} 次/日，注册用户 {{ agentQuota.registered }} 次/日，管理员不限。
                </p>
            </div>
        </div>

        <!-- 提示信息 -->
        <div class="warning-box">
            <span class="warning-icon">!</span>
            <div class="warning-content">
                <p><strong>安全提示：</strong></p>
                <ul>
                    <li>密钥仅存储在后端数据库中，不会暴露到前端运行时</li>
                    <li>仅管理员可以修改和查看密钥</li>
                    <li>不要在前端代码中硬编码 API 密钥</li>
                    <li>定期检查密钥使用情况和安全性</li>
                </ul>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useMessage } from '../../composables/useMessage';
import {
    apiAdminGetAgentConfig,
    apiAdminGetApiKeysStatus,
    apiAdminDeleteApiKey,
    apiAdminSetApiKey,
    apiAdminUpdateAgentConfig,
} from '../../api/backend';

const message = useMessage();

const loading = ref(false);
const keysStatus = ref({
    amap_key: { is_set: false, updated_at: null },
    agent_api_key: { is_set: false, updated_at: null },
    tianditu_tk: { is_set: false, updated_at: null },
    dashscope_api_key: { is_set: false, updated_at: null },
});

const editingKey = ref(null);
const editValues = ref({
    amap_key: '',
    agent_api_key: '',
    tianditu_tk: '',
    dashscope_api_key: '',
});

const agentConfigLoading = ref(false);
const editingAgentConfig = ref(false);
const agentConfig = ref({
    base_url: '',
    model: '',
    available_models: [],
    timeout_seconds: 45,
    max_tokens: 512,
    temperature: 0.2,
    system_prompt: '',
});
const agentConfigDraft = ref({
    ...agentConfig.value,
    available_models_text: '',
    guest_daily_quota: 10,
    registered_daily_quota: 100,
});
const agentQuota = ref({
    guest: 10,
    registered: 100,
});

function formatTime(isoString) {
    if (!isoString) return '从未设置';
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

async function loadKeysStatus() {
    loading.value = true;
    try {
        const result = await apiAdminGetApiKeysStatus();
        const data = result?.data || {};
        keysStatus.value = {
            amap_key: data.amap_key || { is_set: false, updated_at: null },
            agent_api_key: data.agent_api_key || data.agent_token || { is_set: false, updated_at: null },
            tianditu_tk: data.tianditu_tk || { is_set: false, updated_at: null },
            dashscope_api_key: data.dashscope_api_key || data.qwen_vision_api_key || { is_set: false, updated_at: null },
        };
    } catch (error) {
        message.error(`加载密钥状态失败: ${error.message}`);
    } finally {
        loading.value = false;
    }
}

function startEdit(keyName) {
    editingKey.value = keyName;
    editValues.value[keyName] = '';
}

function cancelEdit() {
    editingKey.value = null;
    editValues.value = {
        amap_key: '',
        agent_api_key: '',
        tianditu_tk: '',
        dashscope_api_key: '',
    };
}

function hydrateAgentConfigDraft() {
    agentConfigDraft.value = {
        base_url: String(agentConfig.value.base_url || ''),
        model: String(agentConfig.value.model || ''),
        available_models_text: Array.isArray(agentConfig.value.available_models)
            ? agentConfig.value.available_models.join('\n')
            : '',
        timeout_seconds: Number(agentConfig.value.timeout_seconds || 45),
        max_tokens: Number(agentConfig.value.max_tokens || 512),
        temperature: Number(agentConfig.value.temperature ?? 0.2),
        guest_daily_quota: Number(agentQuota.value.guest || 10),
        registered_daily_quota: Number(agentQuota.value.registered || 100),
        system_prompt: String(agentConfig.value.system_prompt || ''),
    };
}

function parseAvailableModelsText(rawText) {
    return String(rawText || '')
        .split(/[,\n]/g)
        .map((item) => String(item || '').trim())
        .filter(Boolean)
        .filter((item, index, array) => array.indexOf(item) === index)
        .slice(0, 200);
}

function startEditAgentConfig() {
    editingAgentConfig.value = true;
    hydrateAgentConfigDraft();
}

function cancelEditAgentConfig() {
    editingAgentConfig.value = false;
    hydrateAgentConfigDraft();
}

async function loadAgentConfig() {
    agentConfigLoading.value = true;
    try {
        const result = await apiAdminGetAgentConfig();
        const data = result?.data || result || {};
        const provider = data?.provider || {};
        agentConfig.value = {
            base_url: String(provider.base_url || ''),
            model: String(provider.model || ''),
            available_models: Array.isArray(provider.available_models) ? provider.available_models : [],
            timeout_seconds: Number(provider.timeout_seconds || 45),
            max_tokens: Number(provider.max_tokens || 512),
            temperature: Number(provider.temperature ?? 0.2),
            system_prompt: String(provider.system_prompt || ''),
        };

        const quota = data?.chat_quota || {};
        agentQuota.value = {
            guest: Number(quota.guest || 10),
            registered: Number(quota.registered || 100),
        };

        hydrateAgentConfigDraft();
    } catch (error) {
        message.error(`加载 Agent 配置失败: ${error.message}`);
    } finally {
        agentConfigLoading.value = false;
    }
}

async function saveAgentConfig() {
    const availableModels = parseAvailableModelsText(agentConfigDraft.value.available_models_text)
    const guestDailyQuota = Number(agentConfigDraft.value.guest_daily_quota || 0);
    const registeredDailyQuota = Number(agentConfigDraft.value.registered_daily_quota || 0);

    const payload = {
        base_url: String(agentConfigDraft.value.base_url || '').trim(),
        model: String(agentConfigDraft.value.model || '').trim(),
        available_models: availableModels,
        timeout_seconds: Number(agentConfigDraft.value.timeout_seconds || 45),
        max_tokens: Number(agentConfigDraft.value.max_tokens || 512),
        temperature: Number(agentConfigDraft.value.temperature ?? 0.2),
        guest_daily_quota: guestDailyQuota,
        registered_daily_quota: registeredDailyQuota,
        system_prompt: String(agentConfigDraft.value.system_prompt || '').trim(),
    };

    if (!payload.base_url || !payload.system_prompt) {
        message.error('Base URL、System Prompt 不能为空');
        return;
    }

    if (!payload.model && payload.available_models.length === 0) {
        message.error('请至少配置一个固定 Model 或 available_models 列表');
        return;
    }

    if (!Number.isFinite(guestDailyQuota) || guestDailyQuota < 1) {
        message.error('Guest 每日额度必须是大于 0 的整数');
        return;
    }

    if (!Number.isFinite(registeredDailyQuota) || registeredDailyQuota < 1) {
        message.error('Registered 每日额度必须是大于 0 的整数');
        return;
    }

    try {
        const result = await apiAdminUpdateAgentConfig(payload);
        const data = result?.data || result || {};
        const provider = data?.provider || {};
        agentConfig.value = {
            base_url: String(provider.base_url || payload.base_url),
            model: String(provider.model || payload.model),
            available_models: Array.isArray(provider.available_models)
                ? provider.available_models
                : payload.available_models,
            timeout_seconds: Number(provider.timeout_seconds || payload.timeout_seconds),
            max_tokens: Number(provider.max_tokens || payload.max_tokens),
            temperature: Number(provider.temperature ?? payload.temperature),
            system_prompt: String(provider.system_prompt || payload.system_prompt),
        };

        const quota = data?.chat_quota || {};
        agentQuota.value = {
            guest: Number(quota.guest || payload.guest_daily_quota || 10),
            registered: Number(quota.registered || payload.registered_daily_quota || 100),
        };

        hydrateAgentConfigDraft();
        editingAgentConfig.value = false;
        message.success('Agent 参数已保存');
    } catch (error) {
        message.error(`保存 Agent 配置失败: ${error.message}`);
    }
}

async function resetChatQuota() {
    try {
        await apiAdminUpdateAgentConfig({ reset_chat_quota: true });
        await loadAgentConfig();
        message.success('已恢复默认对话额度');
    } catch (error) {
        message.error(`恢复默认额度失败: ${error.message}`);
    }
}

async function saveKey(keyName) {
    const keyValue = editValues.value[keyName]?.trim();

    if (!keyValue) {
        message.error('密钥值不能为空');
        return;
    }

    try {
        await apiAdminSetApiKey(keyName, keyValue);
        message.success(`密钥 ${keyName} 已保存`);
        cancelEdit();
        await loadKeysStatus();
    } catch (error) {
        message.error(`保存密钥失败: ${error.message}`);
    }
}

async function deleteKey(keyName) {
    if (!confirm(`确定要删除 ${keyName} 吗？此操作无法撤销！`)) {
        return;
    }

    try {
        await apiAdminDeleteApiKey(keyName);
        message.success(`密钥 ${keyName} 已删除`);
        await loadKeysStatus();
    } catch (error) {
        message.error(`删除密钥失败: ${error.message}`);
    }
}

onMounted(async () => {
    await loadKeysStatus();
    await loadAgentConfig();
});
</script>

<style scoped>
.api-keys-container {
    width: 100%;
    min-width: 0;
    padding: 0;
    margin: 0;
    color: var(--text-primary);
}

.keys-header {
    margin-bottom: 14px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border-subtle);
    text-align: left;
}

.keys-header h2 {
    font-size: 16px;
    line-height: 1.35;
    margin: 0 0 6px 0;
    color: var(--text-primary);
    font-weight: 700;
}

.subtitle {
    color: var(--text-secondary);
    margin: 0;
    font-size: 14px;
}

.loading-state {
    min-height: 128px;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 10px;
    padding: 28px;
    border: 1px dashed var(--border-subtle);
    border-radius: var(--radius-sm);
    background: var(--surface-1);
    color: var(--text-secondary);
    text-align: center;
    font-size: 13px;
}

.spinner {
    display: inline-block;
    width: 18px;
    height: 18px;
    border: 2px solid var(--neon-cyan-dim);
    border-top: 2px solid var(--neon-cyan);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.keys-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
    margin-bottom: 14px;
}

.key-card {
    min-width: 0;
    background: var(--surface-1);
    border-radius: var(--radius-sm);
    overflow: hidden;
    border: 1px solid var(--border-subtle);
    box-shadow: var(--shadow-button);
    display: flex;
    flex-direction: column;
    transition:
        border-color var(--duration-fast) var(--ease-spatial),
        background var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
}

.key-card:hover {
    border-color: var(--border-active);
    background: var(--surface-hover);
    transform: translateY(-1px);
}

.key-header {
    background: var(--neon-cyan-dim);
    color: var(--text-primary);
    padding: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    border-bottom: 1px solid var(--border-subtle);
}

.key-header h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 700;
    line-height: 1.35;
}

.status-badge {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: var(--radius-full);
    font-weight: 700;
    white-space: nowrap;
}

.status-badge.set {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border: 1px solid var(--border-active);
}

.status-badge.unset {
    background: var(--accent-amber-dim);
    color: var(--accent-amber);
    border: 1px solid rgba(246, 173, 85, 0.32);
}

.key-body {
    padding: 12px;
    flex: 1;
    display: flex;
    flex-direction: column;
}

.key-display {
    flex: 1;
}

.key-value {
    background: rgba(6, 11, 16, 0.42);
    padding: 10px;
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    color: var(--text-primary);
    border: 1px solid var(--border-subtle);
    margin: 0 0 10px 0;
    word-break: break-all;
    font-size: 12px;
}

.key-actions {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
}

.key-hint {
    font-size: 12px;
    color: var(--text-secondary);
    margin: 0;
}

.key-hint a {
    color: var(--neon-cyan);
    text-decoration: none;
    font-weight: bold;
}

.key-hint a:hover {
    text-decoration: underline;
    color: var(--text-primary);
}

.edit-form {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.key-input {
    width: 100%;
    min-height: 38px;
    padding: 10px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    font-size: 12px;
    resize: vertical;
    box-sizing: border-box;
    background: rgba(6, 11, 16, 0.62);
    color: var(--text-primary);
    transition:
        border-color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        background var(--duration-fast) var(--ease-spatial);
}

.key-input:focus {
    outline: none;
    border-color: var(--border-active);
    background: var(--surface-card-strong);
    box-shadow: var(--shadow-focus);
}

.button-group {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.btn {
    min-height: 34px;
    padding: 0 13px;
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition:
        background var(--duration-fast) var(--ease-spatial),
        border-color var(--duration-fast) var(--ease-spatial),
        color var(--duration-fast) var(--ease-spatial),
        box-shadow var(--duration-fast) var(--ease-spatial),
        transform var(--duration-fast) var(--ease-spatial);
    flex: 1;
}

.btn-edit {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border-color: var(--border-active);
}

.btn-edit:hover {
    background: var(--surface-hover);
    color: var(--neon-cyan);
    box-shadow: var(--neon-cyan-glow);
    transform: translateY(-1px);
}

.btn-delete {
    background: var(--accent-rose-dim);
    color: var(--accent-rose);
    border-color: rgba(245, 101, 101, 0.36);
}

.btn-delete:hover {
    background: rgba(245, 101, 101, 0.22);
    color: var(--text-primary);
}

.btn-save {
    background: var(--neon-cyan-dim);
    color: var(--neon-cyan);
    border-color: var(--border-active);
}

.btn-save:hover {
    background: var(--surface-hover);
    box-shadow: var(--neon-cyan-glow);
    transform: translateY(-1px);
}

.btn-cancel {
    background: var(--surface-1);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
}

.btn-cancel:hover {
    color: var(--text-primary);
    background: var(--surface-hover);
}

.key-footer {
    background: rgba(6, 11, 16, 0.36);
    padding: 8px 12px;
    border-top: 1px solid var(--border-subtle);
    font-size: 11px;
    color: var(--text-secondary);
}

.agent-config-section {
    margin-top: 16px;
    background: var(--surface-1);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 14px;
    box-shadow: var(--shadow-button);
}

.section-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
}

.section-header-row h3 {
    margin: 0;
    color: var(--text-primary);
}

.section-actions {
    display: flex;
    gap: 8px;
}

.config-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
}

.config-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--text-secondary);
    font-size: 13px;
}

.config-item strong {
    color: var(--text-primary);
    font-weight: 600;
    white-space: pre-wrap;
    word-break: break-word;
}

.config-item-full {
    grid-column: 1 / -1;
}

.config-view {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.config-note {
    margin: 0;
    font-size: 12px;
    color: var(--text-secondary);
}

@media (max-width: 900px) {
    .config-grid {
        grid-template-columns: 1fr;
    }
}

.warning-box {
    background: var(--accent-amber-dim);
    border: 1px solid rgba(246, 173, 85, 0.28);
    border-radius: var(--radius-sm);
    padding: 14px;
    display: flex;
    gap: 12px;
    margin-top: 14px;
}

.warning-icon {
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 999px;
    border: 1px solid rgba(246, 173, 85, 0.4);
    color: var(--accent-amber);
    font-size: 14px;
    font-weight: 800;
    flex-shrink: 0;
}

.warning-content {
    flex: 1;
}

.warning-content p {
    margin: 0 0 8px 0;
    color: var(--accent-amber);
    font-size: 13px;
    font-weight: bold;
}

.warning-content ul {
    margin: 8px 0 0 20px;
    padding: 0;
    color: var(--text-secondary);
    font-size: 13px;
}

.warning-content li {
    margin: 4px 0;
}

@media (max-width: 768px) {
    .keys-grid,
    .config-grid {
        grid-template-columns: 1fr;
    }

    .key-header,
    .section-header-row,
    .key-actions,
    .button-group {
        align-items: stretch;
        flex-direction: column;
    }

    .btn {
        width: 100%;
    }

    .warning-box {
        flex-direction: column;
    }
}
</style>
