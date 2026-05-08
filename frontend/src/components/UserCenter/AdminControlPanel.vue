<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from '../../composables/useMessage'
import AdminGeodataPanel from './AdminGeodataPanel.vue'
import {
  apiAdminDeleteRows,
  apiAdminGetTableRows,
  apiAdminInsertRow,
  apiAdminListTables,
  apiAdminOverview,
  apiAdminPublishAnnouncement,
  apiAdminUpdateContact,
  apiAdminUpdateRows
} from '../../api/backend'

const message = useMessage()

const overview = ref({
  table_count: 0,
  total_users: 0,
  total_sessions: 0,
  total_messages: 0,
  active_announcement: 0
})

const tables = ref([])
const selectedTable = ref('')
const tableRows = ref([])

const tableLimit = ref(30)
const tableOffset = ref(0)
const insertJsonText = ref('{\n  \n}')

const adminContactText = ref('')
const announcementText = ref('')

const loadingOverview = ref(false)
const loadingTables = ref(false)
const loadingRows = ref(false)
const submittingConfig = ref(false)
const submittingTable = ref(false)

const selectedTableMeta = computed(() => {
  return tables.value.find((item) => item.name === selectedTable.value) || null
})

const rowCountText = computed(() => `共加载 ${tableRows.value.length} 行`)

function parseJsonObject(text, hint = 'JSON 格式错误') {
  try {
    const parsed = JSON.parse(String(text || '{}'))
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('JSON 必须是对象')
    }
    return parsed
  } catch (error) {
    const detail = String(error?.message || '').trim()
    throw new Error(`${hint}${detail ? `：${detail}` : ''}`)
  }
}

function resolveWhere(row) {
  if (row && row.__rowid != null) {
    return { __rowid: row.__rowid }
  }
  if (row && row.id != null) {
    return { id: row.id }
  }
  if (row && row.token != null) {
    return { token: row.token }
  }
  if (row && row.username != null && selectedTable.value === 'user_metrics') {
    return { username: row.username }
  }
  return null
}

function toEditablePayload(row) {
  const payload = { ...(row || {}) }
  delete payload.__rowid
  return payload
}

async function loadOverview() {
  loadingOverview.value = true
  try {
    const result = await apiAdminOverview()
    overview.value = {
      ...overview.value,
      ...(result?.data || {})
    }
  } catch (error) {
    message.error(String(error?.message || '管理员概览加载失败'))
  } finally {
    loadingOverview.value = false
  }
}

async function loadTables() {
  loadingTables.value = true
  try {
    const result = await apiAdminListTables()
    const list = Array.isArray(result?.data) ? result.data : []
    tables.value = list

    if (!selectedTable.value && list.length > 0) {
      selectedTable.value = String(list[0].name || '')
    }

    if (selectedTable.value && !list.some((item) => item.name === selectedTable.value)) {
      selectedTable.value = String(list[0]?.name || '')
    }
  } catch (error) {
    message.error(String(error?.message || '数据库表列表加载失败'))
  } finally {
    loadingTables.value = false
  }
}

async function loadRows() {
  const tableName = String(selectedTable.value || '').trim()
  if (!tableName) {
    tableRows.value = []
    return
  }

  loadingRows.value = true
  try {
    const result = await apiAdminGetTableRows(tableName, tableLimit.value, tableOffset.value)
    tableRows.value = Array.isArray(result?.data) ? result.data : []
  } catch (error) {
    tableRows.value = []
    message.error(String(error?.message || '表数据加载失败'))
  } finally {
    loadingRows.value = false
  }
}

async function handleInsertRow() {
  if (submittingTable.value) return

  const tableName = String(selectedTable.value || '').trim()
  if (!tableName) {
    message.warning('请先选择数据表')
    return
  }

  let rowPayload = null
  try {
    rowPayload = parseJsonObject(insertJsonText.value, '新增数据解析失败')
  } catch (error) {
    message.error(String(error?.message || '新增数据解析失败'))
    return
  }

  submittingTable.value = true
  try {
    await apiAdminInsertRow(tableName, rowPayload)
    message.success('新增成功')
    await loadRows()
    await loadOverview()
  } catch (error) {
    message.error(String(error?.message || '新增失败'))
  } finally {
    submittingTable.value = false
  }
}

async function handleEditRow(row) {
  if (submittingTable.value) return

  const tableName = String(selectedTable.value || '').trim()
  const where = resolveWhere(row)

  if (!tableName || !where) {
    message.warning('当前行缺少可定位键，无法编辑')
    return
  }

  const editable = toEditablePayload(row)
  const defaultText = JSON.stringify(editable, null, 2)
  const nextText = window.prompt('请输入更新后的 JSON 对象（整行替换）', defaultText)

  if (nextText === null) return

  let nextValues = null
  try {
    nextValues = parseJsonObject(nextText, '编辑数据解析失败')
  } catch (error) {
    message.error(String(error?.message || '编辑数据解析失败'))
    return
  }

  submittingTable.value = true
  try {
    await apiAdminUpdateRows(tableName, where, nextValues)
    message.success('更新成功')
    await loadRows()
  } catch (error) {
    message.error(String(error?.message || '更新失败'))
  } finally {
    submittingTable.value = false
  }
}

async function handleDeleteRow(row) {
  if (submittingTable.value) return

  const tableName = String(selectedTable.value || '').trim()
  const where = resolveWhere(row)

  if (!tableName || !where) {
    message.warning('当前行缺少可定位键，无法删除')
    return
  }

  const ok = window.confirm('确认删除该行数据？此操作不可撤销。')
  if (!ok) return

  submittingTable.value = true
  try {
    await apiAdminDeleteRows(tableName, where)
    message.success('删除成功')
    await loadRows()
    await loadOverview()
  } catch (error) {
    message.error(String(error?.message || '删除失败'))
  } finally {
    submittingTable.value = false
  }
}

async function handlePublishAnnouncement() {
  if (submittingConfig.value) return

  const content = String(announcementText.value || '').trim()
  if (!content) {
    message.warning('请输入公告内容')
    return
  }

  submittingConfig.value = true
  try {
    await apiAdminPublishAnnouncement(content)
    message.success('公告发布成功')
    announcementText.value = ''
    await loadOverview()
  } catch (error) {
    message.error(String(error?.message || '公告发布失败'))
  } finally {
    submittingConfig.value = false
  }
}

async function handleSaveContact() {
  if (submittingConfig.value) return

  const contact = String(adminContactText.value || '').trim()
  if (!contact) {
    message.warning('管理员联系方式不能为空')
    return
  }

  submittingConfig.value = true
  try {
    await apiAdminUpdateContact(contact)
    message.success('管理员联系方式已更新')
  } catch (error) {
    message.error(String(error?.message || '联系方式更新失败'))
  } finally {
    submittingConfig.value = false
  }
}

watch(selectedTable, async () => {
  tableOffset.value = 0
  await loadRows()
})

onMounted(async () => {
  await loadOverview()
  await loadTables()
  await loadRows()
})
</script>

<template>
  <div class="admin-console">
    <div class="admin-card">
      <div class="admin-title-row">
        <h4 class="admin-title">管理员控制台</h4>
        <button class="admin-mini-btn" type="button" :disabled="loadingOverview" @click="loadOverview">
          刷新概览
        </button>
      </div>

      <div class="overview-grid">
        <div class="overview-item">
          <span class="overview-label">数据表</span>
          <strong class="overview-value">{{ overview.table_count }}</strong>
        </div>
        <div class="overview-item">
          <span class="overview-label">用户</span>
          <strong class="overview-value">{{ overview.total_users }}</strong>
        </div>
        <div class="overview-item">
          <span class="overview-label">在线会话</span>
          <strong class="overview-value">{{ overview.total_sessions }}</strong>
        </div>
        <div class="overview-item">
          <span class="overview-label">留言</span>
          <strong class="overview-value">{{ overview.total_messages }}</strong>
        </div>
      </div>
    </div>

    <div class="admin-card">
      <h5 class="admin-subtitle">系统配置</h5>

      <label class="admin-field-label">管理员联系方式</label>
      <input v-model="adminContactText" class="admin-input" type="text" placeholder="例如：邮箱 / 微信 / QQ" />

      <button class="admin-action-btn" type="button" :disabled="submittingConfig" @click="handleSaveContact">
        保存联系方式
      </button>

      <label class="admin-field-label">常驻顶部公告</label>
      <textarea
        v-model="announcementText"
        class="admin-textarea"
        placeholder="发布后会同步给所有用户，用户点击后才会消失"
      ></textarea>

      <button class="admin-action-btn" type="button" :disabled="submittingConfig" @click="handlePublishAnnouncement">
        发布公告
      </button>
    </div>

    <div class="admin-card">
      <AdminGeodataPanel />
    </div>

    <div class="admin-card">
      <div class="admin-title-row">
        <h5 class="admin-subtitle">数据库管理</h5>
        <button class="admin-mini-btn" type="button" :disabled="loadingTables" @click="loadTables">
          刷新表
        </button>
      </div>

      <div class="admin-select-row">
        <select v-model="selectedTable" class="admin-select">
          <option value="" disabled>请选择数据表</option>
          <option v-for="item in tables" :key="item.name" :value="item.name">
            {{ item.name }}
          </option>
        </select>
        <button class="admin-mini-btn" type="button" :disabled="loadingRows" @click="loadRows">刷新行</button>
      </div>

      <div class="admin-meta-row">
        <span>{{ rowCountText }}</span>
        <span v-if="selectedTableMeta">字段数：{{ selectedTableMeta.columns?.length || 0 }}</span>
      </div>

      <div class="rows-wrap" v-if="tableRows.length > 0">
        <div v-for="row in tableRows" :key="String(row.__rowid || row.id || row.token || Math.random())" class="row-item">
          <pre class="row-json">{{ JSON.stringify(row, null, 2) }}</pre>
          <div class="row-actions">
            <button class="admin-mini-btn" type="button" :disabled="submittingTable" @click="handleEditRow(row)">编辑</button>
            <button class="admin-mini-btn danger" type="button" :disabled="submittingTable" @click="handleDeleteRow(row)">删除</button>
          </div>
        </div>
      </div>
      <div v-else class="rows-empty">当前表暂无可展示数据</div>

      <label class="admin-field-label">新增一行（JSON 对象）</label>
      <textarea
        v-model="insertJsonText"
        class="admin-textarea"
        placeholder='例如：{"username":"demo","content":"hello"}'
      ></textarea>

      <button class="admin-action-btn" type="button" :disabled="submittingTable" @click="handleInsertRow">
        新增到当前表
      </button>
    </div>
  </div>
</template>

<style scoped>
.admin-console {
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--text-primary);
}

.admin-card {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface-card);
  padding: 12px;
  box-shadow: var(--shadow-panel);
}

.admin-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.admin-title {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
  font-weight: 600;
}

.admin-subtitle {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text-primary);
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.overview-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  background: var(--surface-1);
  display: flex;
  flex-direction: column;
  gap: 4px;
  box-shadow: var(--shadow-button);
}

.overview-label {
  font-size: 12px;
  color: var(--text-muted);
}

.overview-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--neon-cyan);
}

.admin-field-label {
  display: block;
  margin: 10px 0 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.admin-input,
.admin-select,
.admin-textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: rgba(6, 11, 16, 0.62);
  color: var(--text-primary);
  padding: 10px;
  font-size: 13px;
  transition: border-color var(--duration-fast) var(--ease-spatial), box-shadow var(--duration-fast) var(--ease-spatial), background var(--duration-fast) var(--ease-spatial);
}

.admin-input::placeholder,
.admin-textarea::placeholder {
  color: var(--text-muted);
}

.admin-input:focus,
.admin-select:focus,
.admin-textarea:focus {
  outline: none;
  border-color: var(--border-active);
  background: var(--surface-card-strong);
  box-shadow: var(--neon-cyan-glow);
}

.admin-textarea {
  min-height: 88px;
  resize: vertical;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.admin-action-btn,
.admin-mini-btn {
  background: var(--neon-cyan-dim);
  color: var(--neon-cyan);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-spatial);
  font-weight: 700;
}

.admin-action-btn {
  margin-top: 8px;
  padding: 10px 14px;
  font-size: 13px;
  width: 100%;
  box-shadow: var(--shadow-button);
}

.admin-mini-btn {
  padding: 6px 12px;
  font-size: 12px;
}

.admin-mini-btn:hover:not(:disabled),
.admin-action-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-active);
  color: var(--neon-cyan);
  transform: translateY(-1px);
  box-shadow: var(--neon-cyan-glow);
}

.admin-mini-btn:disabled,
.admin-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
  background: var(--surface-1);
  color: var(--text-muted);
  border-color: var(--border-subtle);
}

.admin-mini-btn.danger {
  background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
  border-color: rgba(220, 38, 38, 0.5);
}

.admin-mini-btn.danger:hover:not(:disabled) {
  background: linear-gradient(135deg, #fca5a5 0%, #f87171 100%);
  box-shadow: 0 4px 10px rgba(220, 38, 38, 0.2);
}

.admin-select-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: center;
}

.admin-meta-row {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-muted);
}

.rows-wrap {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
  padding-right: 4px;
}

.rows-wrap::-webkit-scrollbar {
  width: 6px;
}
.rows-wrap::-webkit-scrollbar-thumb {
  background: var(--border-active);
  border-radius: 4px;
}

.row-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-1);
  padding: 10px;
  box-shadow: var(--shadow-button);
}

.row-json {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(6, 11, 16, 0.62);
  padding: 8px;
  border-radius: var(--radius-sm);
  border: 1px dashed var(--border-subtle);
}

.row-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.rows-empty {
  margin-top: 10px;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px;
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  background: var(--surface-1);
}
</style>
