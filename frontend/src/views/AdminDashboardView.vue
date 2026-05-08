<template>
  <main class="admin-dashboard-page">
    <header class="admin-dashboard-header">
      <div>
        <p class="admin-eyebrow">WebGIS Admin</p>
        <h1>管理员仪表盘</h1>
        <p class="admin-subline">用户、访问、三维数据和后台任务统一监控</p>
      </div>
      <div class="admin-header-actions">
        <button class="admin-secondary-btn" type="button" @click="goHome">返回地图</button>
        <button class="admin-primary-btn" type="button" :disabled="loading" @click="refreshDashboard">
          {{ loading ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
    </header>

    <section class="metric-grid">
      <div v-for="item in metrics" :key="item.key" class="metric-card">
        <span class="metric-label">{{ item.label }}</span>
        <strong class="metric-value">{{ item.value }}</strong>
        <span class="metric-help">{{ item.help }}</span>
      </div>
    </section>

    <section class="admin-dashboard-grid">
      <article class="admin-panel span-2">
        <div class="panel-heading">
          <div>
            <h2>最近用户</h2>
            <p>注册、访问和 API 使用情况</p>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>用户名</th>
                <th>角色</th>
                <th>登录</th>
                <th>访问</th>
                <th>API</th>
                <th>最近登录</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in recentUsers" :key="user.username">
                <td>{{ user.username }}</td>
                <td><span class="status-pill">{{ user.role || 'registered' }}</span></td>
                <td>{{ numberText(user.login_count) }}</td>
                <td>{{ numberText(user.total_visit_count) }}</td>
                <td>{{ numberText(user.total_api_calls) }}</td>
                <td>{{ shortTime(user.last_login_at || user.created_at) }}</td>
              </tr>
              <tr v-if="!recentUsers.length">
                <td colspan="6" class="empty-cell">暂无用户数据</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="admin-panel">
        <div class="panel-heading">
          <div>
            <h2>在线会话</h2>
            <p>当前有效登录状态</p>
          </div>
        </div>
        <div class="stack-list">
          <div v-for="session in activeSessions" :key="`${session.username}_${session.created_at}`" class="stack-item">
            <strong>{{ session.username }}</strong>
            <span>{{ session.role }} · {{ shortTime(session.created_at) }}</span>
          </div>
          <div v-if="!activeSessions.length" class="empty-block">暂无在线会话</div>
        </div>
      </article>

      <article class="admin-panel">
        <div class="panel-heading">
          <div>
            <h2>最近访问</h2>
            <p>定位来源与城市</p>
          </div>
        </div>
        <div class="stack-list">
          <div v-for="visit in recentVisits" :key="`${visit.username}_${visit.created_at}`" class="stack-item">
            <strong>{{ visit.username }}</strong>
            <span>{{ visit.ip_region || '--' }} {{ visit.ip_city || '' }} · {{ visit.coord_source || 'unknown' }}</span>
          </div>
          <div v-if="!recentVisits.length" class="empty-block">暂无访问记录</div>
        </div>
      </article>

      <article class="admin-panel span-2">
        <div class="panel-heading">
          <div>
            <h2>三维数据状态</h2>
            <p>发布图层与后台处理任务</p>
          </div>
        </div>
        <div class="data-columns">
          <div class="stack-list">
            <div v-for="layer in threeDLayers" :key="layer.id" class="stack-item">
              <strong>{{ layer.name }}</strong>
              <span>{{ layer.status }} · {{ numberText(layer.feature_count) }} 要素</span>
            </div>
            <div v-if="!threeDLayers.length" class="empty-block">暂无 3D 图层</div>
          </div>
          <div class="stack-list">
            <div v-for="job in geodataJobs" :key="job.job_id" class="stack-item">
              <strong>{{ job.job_type }} · {{ job.status }}</strong>
              <span>{{ Math.round(Number(job.progress || 0) * 100) }}% · {{ job.phase || '--' }}</span>
            </div>
            <div v-if="!geodataJobs.length" class="empty-block">暂无后台任务</div>
          </div>
        </div>
      </article>

      <article class="admin-panel span-3 admin-control-shell">
        <div class="panel-heading">
          <div>
            <h2>管理操作</h2>
            <p>公告、地理数据生产链路和数据库维护</p>
          </div>
        </div>
        <AdminControlPanel />
      </article>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import AdminControlPanel from '../components/UserCenter/AdminControlPanel.vue';
import { apiAdminOverview } from '../api/backend';
import { useMessage } from '../composables/useMessage';

const router = useRouter();
const message = useMessage();
const loading = ref(false);
const overview = ref({});

const metrics = computed(() => [
  { key: 'users', label: '注册用户', value: numberText(overview.value.total_users), help: `访客身份 ${numberText(overview.value.total_guest_identities)}` },
  { key: 'online', label: '在线会话', value: numberText(overview.value.online_sessions), help: `累计会话 ${numberText(overview.value.total_sessions)}` },
  { key: 'visits', label: '访问记录', value: numberText(overview.value.total_visit_events || overview.value.total_visits), help: `user_visits ${numberText(overview.value.total_visits)}` },
  { key: 'messages', label: '留言', value: numberText(overview.value.visible_messages || overview.value.total_messages), help: `公告 ${numberText(overview.value.active_announcement)}` },
  { key: 'layers', label: '3D 图层', value: numberText(overview.value.published_three_d_layers), help: `总计 ${numberText(overview.value.total_three_d_layers)}` },
  { key: 'jobs', label: '后台任务', value: numberText(overview.value.processing_jobs), help: '排队或处理中' }
]);

const recentUsers = computed(() => Array.isArray(overview.value.recent_users) ? overview.value.recent_users : []);
const activeSessions = computed(() => Array.isArray(overview.value.active_sessions) ? overview.value.active_sessions : []);
const recentVisits = computed(() => Array.isArray(overview.value.recent_visits) ? overview.value.recent_visits : []);
const geodataJobs = computed(() => Array.isArray(overview.value.geodata_jobs) ? overview.value.geodata_jobs : []);
const threeDLayers = computed(() => Array.isArray(overview.value.three_d_layers) ? overview.value.three_d_layers : []);

function numberText(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return '0';
  return num.toLocaleString('zh-CN');
}

function shortTime(value) {
  const text = String(value || '').trim();
  if (!text) return '--';
  return text.replace('T', ' ').slice(0, 19);
}

async function refreshDashboard() {
  loading.value = true;
  try {
    const result = await apiAdminOverview();
    overview.value = result?.data || {};
  } catch (error) {
    message.error(String(error?.message || '管理员仪表盘加载失败'));
  } finally {
    loading.value = false;
  }
}

function goHome() {
  router.push({ name: 'home' });
}

onMounted(refreshDashboard);
</script>

<style scoped>
.admin-dashboard-page {
  min-height: 100vh;
  padding: 24px;
  box-sizing: border-box;
  color: var(--text-primary);
  background:
    linear-gradient(135deg, rgba(71, 215, 198, 0.08), transparent 34%),
    var(--deep-0);
}

.admin-dashboard-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 18px;
}

.admin-eyebrow {
  margin: 0 0 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--neon-cyan);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

h1,
h2 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: clamp(24px, 3vw, 34px);
  line-height: 1.1;
}

h2 {
  font-size: 15px;
}

.admin-subline,
.panel-heading p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 13px;
}

.admin-header-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.admin-primary-btn,
.admin-secondary-btn {
  min-height: 38px;
  border-radius: var(--radius-sm);
  padding: 0 14px;
  border: 1px solid var(--border-active);
  cursor: pointer;
  font-weight: 700;
}

.admin-primary-btn {
  background: var(--neon-cyan-dim);
  color: var(--neon-cyan);
}

.admin-secondary-btn {
  background: var(--surface-card);
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.metric-card,
.admin-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  box-shadow: var(--shadow-panel);
}

.metric-card {
  padding: 14px;
  display: grid;
  gap: 5px;
}

.metric-label,
.metric-help {
  color: var(--text-muted);
  font-size: 12px;
}

.metric-value {
  font-size: 24px;
  color: var(--neon-cyan);
}

.admin-dashboard-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.admin-panel {
  min-width: 0;
  padding: 14px;
}

.span-2 {
  grid-column: span 2;
}

.span-3 {
  grid-column: 1 / -1;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.table-wrap {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 640px;
}

th,
td {
  padding: 10px 8px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  font-size: 12px;
}

th {
  color: var(--text-muted);
  font-weight: 700;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-full);
  color: var(--neon-cyan);
  background: var(--neon-cyan-dim);
}

.stack-list {
  display: grid;
  gap: 8px;
}

.stack-item,
.empty-block {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface-1);
  padding: 10px;
}

.stack-item {
  display: grid;
  gap: 4px;
}

.stack-item strong {
  font-size: 13px;
  color: var(--text-primary);
}

.stack-item span,
.empty-block,
.empty-cell {
  color: var(--text-muted);
  font-size: 12px;
}

.data-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.admin-control-shell :deep(.admin-console) {
  gap: 14px;
}

@media (max-width: 1200px) {
  .metric-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .admin-dashboard-grid {
    grid-template-columns: 1fr;
  }

  .span-2 {
    grid-column: 1;
  }
}

@media (max-width: 760px) {
  .admin-dashboard-page {
    padding: 14px;
  }

  .admin-dashboard-header,
  .data-columns {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
