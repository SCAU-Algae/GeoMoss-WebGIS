<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from '../../composables/useMessage'
import {
  apiAuthChangePassword,
  apiAuthChangeAvatar,
  apiAuthLogout,
  apiAuthMe,
  apiAgentListModels,
  apiCreateUserMessage,
  apiListUserMessages,
  apiStatisticsCenter,
  apiStatisticsRealtime,
  syncUserRoleToUrl
} from '../../api/backend'
import { clearAuthSession, getAuthToken, getAuthUser, setAuthSession } from '../../utils/auth'
import { BASEMAP_OPTIONS } from '../../constants'
import { useUserPreferencesStore } from '../../stores'

const AdminControlPanel = defineAsyncComponent(() => import('./AdminControlPanel.vue'))
const ApiManagementPanel = defineAsyncComponent(() => import('./ApiManagementPanel.vue'))

const router = useRouter()
const message = useMessage()
const userPreferencesStore = useUserPreferencesStore()
const props = defineProps({
  open: {
    type: Boolean,
    default: undefined
  },
  showFab: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['fullscreen-change', 'update:open'])

// Panel State
const isOpen = ref(false)
const isFullscreen = ref(false)
const activeMenu = ref('overview') // 'overview', 'security', 'admin', 'api-management', 'preferences'
const isSubmitting = ref(false)
const isLoadingCenter = ref(false)
const isPostingMessage = ref(false)
const user = ref(getAuthUser())

const centerData = ref({
  quota: {
    limit: null,
    used: 0,
    remaining: null,
    usage_date: ''
  },
  self_stats: {
    registered_at: '',
    login_count: 0,
    total_login_seconds: 0,
    total_api_calls: 0,
    total_visit_count: 0,
    last_login_at: '',
    last_logout_at: '',
    current_session_seconds: 0
  },
  realtime: {
    online_users: 0,
    total_visit_count: 0,
    total_api_calls: 0,
    total_registered_users: 0
  },
  admin_contact: '管理员联系方式：admin@geomoss.local',
  messages: []
})

const newMessageText = ref('')

// Password Form
const currentPassword = ref('')
const nextPassword = ref('')
const confirmPassword = ref('')

// Avatar Management
const selectedAvatarIndex = ref(0)
const avatarSaving = ref(false)

const preferenceDraft = ref({
  default_basemap: '',
  language: 'zh-CN',
  unit_system: 'metric',
  preferred_agent_model: ''
})
const preferenceSaving = ref(false)
const preferenceModelOptions = ref([])

const roleTextMap = Object.freeze({
  admin: '管理员',
  super_admin: '管理员',
  registered: '注册用户',
  guest: '游客'
})

const isAdmin = computed(() => String(user.value?.role || '') === 'admin')

function resolvePublicAssetPath(relativePath) {
  const base = String(import.meta.env.BASE_URL || '/').trim()
  const normalizedBase = base.endsWith('/') ? base : `${base}/`
  const normalizedPath = String(relativePath || '').replace(/^\/+/, '')
  return `${normalizedBase}${normalizedPath}`
}

const userAvatarIndex = computed(() => {
  const raw = Number(user.value?.avatar_index)
  if (Number.isInteger(raw) && raw >= 0 && raw <= 11) {
    return raw
  }
  const role = String(user.value?.role || '').trim()
  if (role === 'admin') {
    return 1
  }
  return 0
})

const userAvatarSrc = computed(() => {
  return resolvePublicAssetPath(`avatars/avatar-${userAvatarIndex.value}.svg`)
})

const getAvatarSrc = (avatarIndex) => {
  return resolvePublicAssetPath(`avatars/avatar-${avatarIndex}.svg`)
}

const roleText = computed(() => {
  const role = String(user.value?.role || '').trim()
  return roleTextMap[role] || '未知角色'
})

const hasControlledOpen = computed(() => props.open !== undefined)

const panelLabel = computed(() => {
  const username = String(user.value?.username || '').trim()
  return username ? `账号：${username}` : '账号中心'
})

const basemapPreferenceOptions = computed(() => {
  return Array.isArray(BASEMAP_OPTIONS) ? BASEMAP_OPTIONS : []
})

const selfStats = computed(() => centerData.value?.self_stats || {})
const quotaInfo = computed(() => centerData.value?.quota || {})
const realtimeStats = computed(() => centerData.value?.realtime || {})
const adminContact = computed(() => String(centerData.value?.admin_contact || '').trim())
const recentMessages = computed(() => {
  const source = centerData.value?.messages
  return Array.isArray(source) ? source : []
})

const quotaText = computed(() => {
  const used = Number(quotaInfo.value?.used || 0)
  const limit = quotaInfo.value?.limit
  if (limit == null) {
    return `已调用 ${used} 次 / 不限额`
  }
  return `已调用 ${used}/${limit} 次`
})

const sessionDurationText = computed(() => {
  const sec = Number(selfStats.value?.current_session_seconds || 0)
  return formatDuration(sec)
})

function formatDuration(totalSeconds) {
  const sec = Math.max(0, Number(totalSeconds || 0))
  const day = Math.floor(sec / 86400)
  const hour = Math.floor((sec % 86400) / 3600)
  const minute = Math.floor((sec % 3600) / 60)
  const second = sec % 60

  if (day > 0) {
    return `${day}天 ${hour}小时 ${minute}分钟`
  }
  if (hour > 0) {
    return `${hour}小时 ${minute}分钟 ${second}秒`
  }
  if (minute > 0) {
    return `${minute}分钟 ${second}秒`
  }
  return `${second}秒`
}

function formatDateTime(value) {
  const raw = String(value || '').trim()
  if (!raw) return '-'

  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) {
    return raw
  }

  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

async function syncCurrentUser() {
  try {
    const result = await apiAuthMe()
    if (!result?.user) return

    user.value = result.user
    selectedAvatarIndex.value = Number(result?.user?.avatar_index ?? selectedAvatarIndex.value)
    syncUserRoleToUrl(result.user)
    const token = getAuthToken()
    if (token) {
      setAuthSession({ token, user: result.user })
    }
  } catch {
    // handled by interceptor
  }
}

async function loadCenterData({ silent = false } = {}) {
  if (isLoadingCenter.value) return

  isLoadingCenter.value = true
  try {
    const result = await apiStatisticsCenter()

    if (result?.user) {
      user.value = result.user
      selectedAvatarIndex.value = Number(result?.user?.avatar_index ?? selectedAvatarIndex.value)
      syncUserRoleToUrl(result.user)
      const token = getAuthToken()
      if (token) {
        setAuthSession({ token, user: result.user })
      }
    }

    centerData.value = {
      ...centerData.value,
      ...(result || {})
    }
  } catch (error) {
    if (!silent) {
      message.warning(String(error?.message || '用户中心数据加载失败'))
    }
  } finally {
    isLoadingCenter.value = false
  }
}

async function refreshRealtimeData({ silent = true } = {}) {
  try {
    const result = await apiStatisticsRealtime()
    if (result?.data) {
      centerData.value = {
        ...centerData.value,
        realtime: {
          ...centerData.value.realtime,
          ...result.data
        }
      }
    }
  } catch (error) {
    if (!silent) {
      message.warning(String(error?.message || '实时统计刷新失败'))
    }
  }
}

async function refreshMessages() {
  try {
    const result = await apiListUserMessages()
    const list = Array.isArray(result?.data) ? result.data : []
    centerData.value = {
      ...centerData.value,
      messages: list
    }
  } catch {
    // keep latest messages in panel
  }
}

function closePanel() {
  setOpen(false)
  setFullscreen(false)
  setTimeout(() => {
    activeMenu.value = 'overview'
    resetPasswordForm()
  }, 200)
}

function setOpen(nextValue) {
  const normalized = Boolean(nextValue)
  if (isOpen.value === normalized) return
  isOpen.value = normalized
  emit('update:open', normalized)
}

function setFullscreen(nextValue) {
  const normalized = Boolean(nextValue)
  if (isFullscreen.value === normalized) return
  isFullscreen.value = normalized
  emit('fullscreen-change', normalized)
}

function toggleFullscreen() {
  setFullscreen(!isFullscreen.value)
}

function togglePanel() {
  const nextOpen = !isOpen.value
  setOpen(nextOpen)

  if (nextOpen) {
    loadCenterData({ silent: true })
  }

  if (!nextOpen) {
    setFullscreen(false)
    setTimeout(() => {
      activeMenu.value = 'overview'
      resetPasswordForm()
    }, 200)
  }
}

watch(
  () => props.open,
  (nextValue) => {
    if (!hasControlledOpen.value) return
    const normalized = Boolean(nextValue)
    if (isOpen.value !== normalized) {
      isOpen.value = normalized
      if (normalized) {
        loadCenterData({ silent: true })
      } else {
        setFullscreen(false)
        setTimeout(() => {
          activeMenu.value = 'overview'
          resetPasswordForm()
        }, 200)
      }
    }
  },
  { immediate: true }
)

function selectMenu(menu) {
  if (menu === 'admin' && !isAdmin.value) return

  activeMenu.value = menu
  if (menu === 'preferences') {
    void loadUserPreferences({ silent: true })
    void loadPreferenceModelOptions({ silent: true })
  }
  if (menu !== 'security') {
    resetPasswordForm()
  }
}

function normalizePreferences(raw = {}) {
  const languageRaw = String(raw?.language || '').trim().toLowerCase().replace('_', '-')
  const language = languageRaw === 'en-us' ? 'en-US' : 'zh-CN'
  const unitRaw = String(raw?.unit_system || '').trim().toLowerCase()
  const unitSystem = unitRaw === 'imperial' ? 'imperial' : 'metric'

  return {
    default_basemap: String(raw?.default_basemap || '').trim(),
    language,
    unit_system: unitSystem,
    preferred_agent_model: String(raw?.preferred_agent_model || '').trim(),
  }
}

function syncPreferenceDraftFromStore() {
  preferenceDraft.value = normalizePreferences(userPreferencesStore.preferences)
}

async function loadUserPreferences({ silent = true } = {}) {
  try {
    await userPreferencesStore.loadPreferences({ force: true, silent })
    syncPreferenceDraftFromStore()
  } catch (error) {
    if (!silent) {
      message.error(String(error?.message || '偏好设置加载失败'))
    }
  }
}

async function loadPreferenceModelOptions({ silent = true } = {}) {
  try {
    const result = await apiAgentListModels()
    const data = result?.data || result || {}
    const models = Array.isArray(data?.models) ? data.models : []
    preferenceModelOptions.value = models
      .filter((item) => item?.chat_compatible !== false)
      .map((item) => String(item?.id || '').trim())
      .filter(Boolean)
      .filter((item, index, array) => array.indexOf(item) === index)
  } catch (error) {
    preferenceModelOptions.value = []
    if (!silent) {
      message.warning(String(error?.message || '模型列表加载失败'))
    }
  }
}

async function handleSavePreferences() {
  if (preferenceSaving.value) return
  preferenceSaving.value = true

  try {
    const saved = await userPreferencesStore.savePreferences(normalizePreferences(preferenceDraft.value))
    preferenceDraft.value = normalizePreferences(saved)
    message.success('偏好设置已保存')
  } catch (error) {
    message.error(String(error?.message || '偏好设置保存失败'))
  } finally {
    preferenceSaving.value = false
  }
}



function resetPasswordForm() {
  currentPassword.value = ''
  nextPassword.value = ''
  confirmPassword.value = ''
}

function handleDocumentClick(event) {
  const root = event.target?.closest?.('.floating-account-manager')
  if (!root) {
    closePanel()
  }
}

function handleDocumentKeydown(event) {
  if (event.key === 'Escape' && isFullscreen.value) {
    setFullscreen(false)
  }
}

async function forceBackToLogin(hintText = '') {
  clearAuthSession()
  closePanel()

  if (hintText) {
    message.success(hintText)
  }

  await router.replace('/register')
}

async function handleLogout() {
  if (isSubmitting.value) return
  isSubmitting.value = true

  try {
    await apiAuthLogout()
  } catch {
  } finally {
    isSubmitting.value = false
  }

  await forceBackToLogin('已退出登录')
}

async function handleChangePassword() {
  if (isSubmitting.value) return

  const oldPass = String(currentPassword.value || '').trim()
  const newPass = String(nextPassword.value || '').trim()
  const confirmPass = String(confirmPassword.value || '').trim()

  if (!oldPass || !newPass || !confirmPass) {
    message.error('请完整填写密码信息')
    return
  }

  if (newPass !== confirmPass) {
    message.error('两次输入的新密码不一致')
    return
  }

  if (newPass.length < 6) {
    message.error('新密码长度至少为 6 位')
    return
  }

  isSubmitting.value = true

  try {
    await apiAuthChangePassword(oldPass, newPass)
    resetPasswordForm()
    await forceBackToLogin('密码已修改，请重新登录')
  } catch (error) {
    const detail = String(error?.message || '').trim()
    message.error(detail || '密码修改失败，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

async function handleSaveAvatar() {
  if (avatarSaving.value) return

  avatarSaving.value = true
  try {
    const result = await apiAuthChangeAvatar(selectedAvatarIndex.value)
    if (result?.status === 'success') {
      message.success('头像已更新')
      // 更新本地用户对象
      if (user.value) {
        user.value.avatar_index = Number(result?.avatar_index ?? selectedAvatarIndex.value)
        const token = getAuthToken()
        if (token) {
          setAuthSession({ token, user: user.value })
        }
      }
    } else {
      message.error('头像更新失败，请稍后重试')
    }
  } catch (error) {
    const detail = String(error?.message || '').trim()
    message.error(detail || '头像更新失败，请稍后重试')
  } finally {
    avatarSaving.value = false
  }
}

async function handleSubmitUserMessage() {
  if (isPostingMessage.value) return

  const content = String(newMessageText.value || '').trim()
  if (!content) {
    message.warning('留言内容不能为空')
    return
  }

  isPostingMessage.value = true
  try {
    await apiCreateUserMessage(content)
    newMessageText.value = ''
    message.success('留言已发布')
    await refreshMessages()
    await refreshRealtimeData({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '留言发布失败'))
  } finally {
    isPostingMessage.value = false
  }
}

let centerTimer = null

onMounted(() => {
  syncCurrentUser()
  void loadUserPreferences({ silent: true })
  void loadPreferenceModelOptions({ silent: true })
  // 初始化头像选择为当前用户的头像
  selectedAvatarIndex.value = userAvatarIndex.value
  loadCenterData({ silent: true })
  refreshRealtimeData({ silent: true })
  refreshMessages()

  if (typeof window !== 'undefined') {
    centerTimer = window.setInterval(() => {
      loadCenterData({ silent: true })
      refreshRealtimeData({ silent: true })
    }, 30000)
  }

  document.addEventListener('pointerdown', handleDocumentClick)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  setFullscreen(false)

  if (centerTimer && typeof window !== 'undefined') {
    window.clearInterval(centerTimer)
    centerTimer = null
  }

  document.removeEventListener('pointerdown', handleDocumentClick)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>

<template>
  <div class="floating-account-manager" :class="{ 'is-open': isOpen, 'is-fullscreen': isFullscreen }">
    <button
      v-if="showFab"
      class="account-fab"
      type="button"
      :aria-label="panelLabel"
      @click.stop="togglePanel"
    >
      <div class="fab-content">
        <div class="account-avatar-wrapper">
            <span class="account-avatar">
              <img :src="userAvatarSrc" :alt="`${user?.username || '用户'}头像`" loading="lazy">
            </span>
            <span class="status-dot"></span>
        </div>
        <span class="account-fab-text">{{ user?.username || '用户' }}</span>
        <i class="fas fa-chevron-up fold-icon" :class="{ 'rotated': !isOpen }"></i>
      </div>
    </button>

    <transition name="account-panel-transition">
      <div v-if="isOpen" class="account-panel" :class="{ 'is-fullscreen': isFullscreen }" @pointerdown.stop>
        
        <!-- Header Profile Summary -->
        <div class="panel-header blur-bg">
          <div class="profile-main">
            <div class="profile-avatar large blur-bg">
              <img :src="userAvatarSrc" :alt="`${user?.username || '用户'}头像`" loading="lazy">
            </div>
            <div class="profile-info">
              <h3 class="profile-name">{{ user?.username || 'unknown' }}</h3>
              <span class="profile-role">
                <i class="fas fa-id-badge"></i> {{ roleText }}
              </span>
            </div>
          </div>
          <button
            type="button"
            class="btn-fullscreen"
            :title="isFullscreen ? '退出全屏' : '全屏展开'"
            @click="toggleFullscreen"
          >
            <i :class="isFullscreen ? 'fas fa-compress-alt' : 'fas fa-expand-alt'"></i>
          </button>
        </div>

        <!-- Navigation Tabs -->
        <div class="panel-nav">
          <button 
            type="button" 
            class="nav-tab" 
            :class="{ active: activeMenu === 'overview' }"
            @click="selectMenu('overview')"
          >
            <i class="fas fa-home"></i> 总览
          </button>
          <button 
            type="button" 
            class="nav-tab" 
            :class="{ active: activeMenu === 'security' }"
            @click="selectMenu('security')"
          >
            <i class="fas fa-shield-alt"></i> 安全
          </button>
          <button
            v-if="isAdmin"
            type="button"
            class="nav-tab"
            :class="{ active: activeMenu === 'admin' }"
            @click="selectMenu('admin')"
          >
            <i class="fas fa-database"></i> 管理
          </button>
          <button
            v-if="isAdmin"
            type="button"
            class="nav-tab"
            :class="{ active: activeMenu === 'api-management' }"
            @click="selectMenu('api-management')"
          >
            <i class="fas fa-sliders-h"></i> API
          </button>
          <button 
            type="button" 
            class="nav-tab" 
            :class="{ active: activeMenu === 'preferences' }"
            @click="selectMenu('preferences')"
          >
            <i class="fas fa-sliders-h"></i> 偏好
          </button>
        </div>

        <!-- Scrollable Content Area -->
        <div class="panel-body styled-scrollbar">
          
          <!-- View 1: Overview -->
          <transition name="fade-slide" mode="out-in">
            <div v-if="activeMenu === 'overview'" class="view-content overview-view" key="overview">
              <div class="info-card">
                <div class="info-row">
                  <span class="info-label">注册时间</span>
                  <span class="info-value">{{ formatDateTime(selfStats.registered_at) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">上次登录</span>
                  <span class="info-value">{{ formatDateTime(selfStats.last_login_at) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">本次在线时长</span>
                  <span class="info-value">{{ sessionDurationText }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">当前 API 配额</span>
                  <span class="info-value">{{ quotaText }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">当前状态</span>
                  <span class="info-value text-success">
                    <i class="fas fa-circle active-dot"></i> 在线
                  </span>
                </div>
              </div>
              
              <div class="stats-grid">
                <div class="stat-box">
                  <i class="fas fa-sign-in-alt stat-icon"></i>
                  <span class="stat-num">{{ selfStats.login_count || 0 }}</span>
                  <span class="stat-name">登录次数</span>
                </div>
                <div class="stat-box">
                  <i class="fas fa-chart-line stat-icon"></i>
                  <span class="stat-num">{{ selfStats.total_visit_count || 0 }}</span>
                  <span class="stat-name">访问次数</span>
                </div>
                <div class="stat-box">
                  <i class="fas fa-bolt stat-icon"></i>
                  <span class="stat-num">{{ selfStats.total_api_calls || 0 }}</span>
                  <span class="stat-name">API 调用</span>
                </div>
              </div>

              <div class="info-card account-extra-card">
                <div class="info-row">
                  <span class="info-label">全站在线用户</span>
                  <span class="info-value">{{ realtimeStats.online_users || 0 }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">全站总浏览量</span>
                  <span class="info-value">{{ realtimeStats.total_visit_count || 0 }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">全站总 API 调用</span>
                  <span class="info-value">{{ realtimeStats.total_api_calls || 0 }}</span>
                </div>
                <div class="info-row">
                  <span class="info-label">注册用户总数</span>
                  <span class="info-value">{{ realtimeStats.total_registered_users || 0 }}</span>
                </div>
              </div>

              <div class="info-card account-extra-card">
                <div class="info-row">
                  <span class="info-label">管理员联系方式</span>
                  <span class="info-value break-text">{{ adminContact || '未配置' }}</span>
                </div>
              </div>

              <div class="info-card account-extra-card">
                <div class="compose-title">用户留言</div>
                <textarea
                  v-model="newMessageText"
                  class="user-message-input"
                  placeholder="请输入你的建议或反馈，发布后所有用户都能看到"
                ></textarea>
                <button
                  class="btn-primary w-100"
                  type="button"
                  :disabled="isPostingMessage"
                  @click="handleSubmitUserMessage"
                >
                  <i class="fas" :class="isPostingMessage ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
                  {{ isPostingMessage ? '发布中...' : '发布留言' }}
                </button>

                <div class="message-list">
                  <div v-if="recentMessages.length === 0" class="message-empty">暂无留言</div>
                  <div v-for="item in recentMessages" :key="item.id" class="message-item">
                    <div class="message-item-meta">
                      <span class="message-author">{{ item.username || '匿名' }}</span>
                      <span class="message-time">{{ formatDateTime(item.created_at) }}</span>
                    </div>
                    <div class="message-item-content">{{ item.content }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- View 2: Security -->
            <div v-else-if="activeMenu === 'security'" class="view-content security-view" key="security">
              <div v-if="user?.role === 'guest'" class="guest-warning">
                <i class="fas fa-exclamation-triangle"></i>
                <p>游客账号不支持修改密码，请注册正式账号享受完整功能。</p>
              </div>
              <div v-else-if="user?.role === 'admin'" class="guest-warning">
                <i class="fas fa-user-shield"></i>
                <p>管理员密码优先由 SUPER_USER 控制（本地未配置时默认 123456），不支持在线修改。</p>
              </div>
              <div v-else class="password-form-container">
                <h4 class="section-title">修改密码</h4>
                <div class="modern-input-group">
                  <i class="fas fa-lock input-icon"></i>
                  <input
                    v-model="currentPassword"
                    type="password"
                    autocomplete="current-password"
                    placeholder="当前密码"
                  >
                </div>
                <div class="modern-input-group">
                  <i class="fas fa-key input-icon"></i>
                  <input
                    v-model="nextPassword"
                    type="password"
                    autocomplete="new-password"
                    placeholder="新密码 (至少6位)"
                  >
                </div>
                <div class="modern-input-group">
                  <i class="fas fa-check-double input-icon"></i>
                  <input
                    v-model="confirmPassword"
                    type="password"
                    autocomplete="new-password"
                    placeholder="确认新密码"
                  >
                </div>
                
                <button
                  class="btn-primary w-100"
                  type="button"
                  :disabled="isSubmitting"
                  @click="handleChangePassword"
                >
                  <i class="fas" :class="isSubmitting ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                  {{ isSubmitting ? '正在提交...' : '保存新密码' }}
                </button>
              </div>
            </div>

            <!-- View 3: Admin -->
            <div v-else-if="activeMenu === 'admin' && isAdmin" class="view-content admin-view" key="admin">
              <AdminControlPanel />
            </div>

            <!-- View 4: API Management -->
            <div v-else-if="activeMenu === 'api-management' && isAdmin" class="view-content api-mgmt-view" key="api-management">
              <ApiManagementPanel />
            </div>

            <!-- View 5: Preferences -->
            <div v-else-if="activeMenu === 'preferences'" class="view-content prefs-view" key="preferences">
              <div class="pref-list">
                <div class="pref-item">
                  <div class="pref-info">
                    <span class="pref-title"><i class="fas fa-map"></i> 默认底图</span>
                    <span class="pref-desc">刷新后自动应用当前选择的底图</span>
                  </div>
                  <select v-model="preferenceDraft.default_basemap" class="pref-select">
                    <option value="">跟随系统默认</option>
                    <option
                      v-for="option in basemapPreferenceOptions"
                      :key="option.value"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </div>

                <div class="pref-item">
                  <div class="pref-info">
                    <span class="pref-title"><i class="fas fa-language"></i> 界面语言</span>
                    <span class="pref-desc">设置账号默认语言偏好</span>
                  </div>
                  <select v-model="preferenceDraft.language" class="pref-select">
                    <option value="zh-CN">简体中文</option>
                    <option value="en-US">English</option>
                  </select>
                </div>

                <div class="pref-item">
                  <div class="pref-info">
                    <span class="pref-title"><i class="fas fa-ruler-combined"></i> 单位制</span>
                    <span class="pref-desc">控制距离等数值默认单位</span>
                  </div>
                  <select v-model="preferenceDraft.unit_system" class="pref-select">
                    <option value="metric">公制 (km / m)</option>
                    <option value="imperial">英制 (mi / ft)</option>
                  </select>
                </div>

                <div class="pref-item">
                  <div class="pref-info">
                    <span class="pref-title"><i class="fas fa-robot"></i> 偏好 Agent 模型</span>
                    <span class="pref-desc">设置后将锁定优先使用该模型（若可用）</span>
                  </div>
                  <select v-model="preferenceDraft.preferred_agent_model" class="pref-select">
                    <option value="">自动调度（后端随机）</option>
                    <option
                      v-for="modelId in preferenceModelOptions"
                      :key="modelId"
                      :value="modelId"
                    >
                      {{ modelId }}
                    </option>
                  </select>
                </div>

                <button
                  class="btn-primary w-100"
                  type="button"
                  :disabled="preferenceSaving"
                  @click="handleSavePreferences"
                >
                  <i class="fas" :class="preferenceSaving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                  {{ preferenceSaving ? '保存中...' : '保存偏好设置' }}
                </button>

                <!-- 头像选择器 -->
                <div class="pref-item avatar-selector-item">
                  <div class="pref-info">
                    <span class="pref-title"><i class="fas fa-image"></i> 个人头像</span>
                    <span class="pref-desc">选择你喜欢的头像样式</span>
                  </div>
                </div>



                <div class="avatar-grid">
                  <div 
                    v-for="index in 12" 
                    :key="index - 1"
                    class="avatar-option"
                    :class="{ selected: selectedAvatarIndex === (index - 1) }"
                    @click="selectedAvatarIndex = index - 1"
                  >
                    <img :src="getAvatarSrc(index - 1)" :alt="`Avatar ${index}`" />
                  </div>
                </div>
                <button 
                  v-if="selectedAvatarIndex !== (user?.avatar_index || 0)"
                  class="avatar-save-btn"
                  @click="handleSaveAvatar"
                  :disabled="avatarSaving"
                >
                  <i class="fas fa-save"></i> {{ avatarSaving ? '保存中...' : '保存头像' }}
                </button>
                <div v-else class="avatar-status">
                  <i class="fas fa-check-circle"></i> 当前头像
                </div>
              </div>
            </div>
          </transition>
        </div>

        <!-- Footer Actions -->
        <div class="panel-footer blur-bg">
          <button
            class="btn-logout"
            type="button"
            :disabled="isSubmitting"
            @click="handleLogout"
            title="安全退出"
          >
            <i class="fas fa-sign-out-alt"></i>
            退出系统
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
/* 
  High-End Atmospheric Floating Account Center
  Emerald Gradient & Premium Glassmorphism Design
*/

/* .floating-account-manager {
  position: fixed;
  top: 200px;
  left: 250px;
  z-index: 1500;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  align-items: flex-start;
  gap: 16px;
} */

.floating-account-manager.is-fullscreen {
  z-index: 3000;
}

.floating-account-manager.is-fullscreen .account-fab {
  display: none;
}

/* Float FAB */
.account-fab {
  border: 1px solid var(--border-active);
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--surface-2), var(--glass-bg-heavy));
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: var(--text-primary);

  /* 👇 抛弃固定高度，用自适应单位 */
  height: auto;
  min-height: 44px; /* 移动端最小可点击高度 */
  max-height: 56px; /* 大屏不超出原来的设计 */

  /* 👇 内边距也自适应 */
  padding: 6px 20px 6px 8px;
  display: inline-flex;
  align-items: center;
  gap: 8px; /* 图标和文字的间距 */

  cursor: pointer;
  box-shadow: var(--shadow-panel);
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
  position: relative;
  overflow: hidden;
}

.account-fab::before {
  content: '';
  position: absolute;
  top: 0; left: -100%;
  width: 50%; height: 100%;
  background: linear-gradient(90deg, transparent, var(--neon-cyan-dim), transparent);
  transition: left var(--duration-slow) var(--ease-panel);
}

.account-fab:hover {
  transform: translateY(-2px);
  background: var(--surface-hover);
  box-shadow: var(--shadow-elevated);
  border-color: var(--border-glow);
}

.account-fab:hover::before {
  left: 150%;
}

.fab-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.account-avatar-wrapper {
  position: relative;
}

.account-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--neon-cyan), var(--neon-green));
  color: var(--deep-0);
  box-shadow: inset 0 -3px 6px rgba(0,0,0,0.4);
  border: 2px solid var(--border-active);
}

.account-avatar img {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  object-fit: cover;
}

.status-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 12px;
  height: 12px;
  background: var(--neon-green);
  border: 2px solid var(--deep-1);
  border-radius: 50%;
  box-shadow: var(--neon-green-glow);
}

.account-fab-text {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
  white-space: nowrap;
  color: var(--text-primary);
  text-shadow: none;
}

.fold-icon {
  font-size: 14px;
  color: var(--neon-cyan);
  opacity: 0.8;
  transition: transform var(--duration-panel) var(--ease-spring-subtle);
  margin-left: 2px;
}

.fold-icon.rotated {
  transform: rotate(180deg);
}

/* Glass Panel */
.account-panel {
  width: 420px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--glass-border);
  background: linear-gradient(180deg, var(--surface-card-strong), var(--glass-bg-heavy));
  box-shadow: var(--shadow-elevated);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px);
  display: flex;
  flex-direction: column;
  transform-origin: bottom left;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-panel) var(--ease-spring-subtle),
    opacity var(--duration-normal) var(--ease-spatial);
}

.account-panel.is-fullscreen {
  border-radius: 0;
  border: none;
  clip-path: none;
  z-index: 1;
  transform-origin: center;
  /* background defaults to panel gradient */
}

.account-panel.is-fullscreen .panel-header {
  padding: 16px 20px;
}

.account-panel.is-fullscreen .panel-nav {
  flex-wrap: wrap;
  gap: 8px;
}

.account-panel.is-fullscreen .nav-tab {
  flex: 0 1 calc(25% - 6px);
  padding: 10px 12px;
}

.account-panel.is-fullscreen .panel-body {
  height: auto;
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.account-panel.is-fullscreen .panel-footer {
  position: sticky;
  bottom: 0;
  padding: 12px 20px;
}

.account-panel.is-fullscreen .panel-header {
  padding: 16px 20px;
}

.account-panel.is-fullscreen .panel-nav {
  flex-wrap: wrap;
  gap: 8px;
}

.account-panel.is-fullscreen .nav-tab {
  flex: 0 1 calc(25% - 6px);
  padding: 10px 12px;
}

.account-panel.is-fullscreen .panel-body {
  height: auto;
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.account-panel.is-fullscreen .panel-footer {
  position: sticky;
  bottom: 0;
  padding: 12px 20px;
}

.blur-bg {
  background: transparent;
}

/* Header */
.panel-header {
  padding: 24px;
  border-bottom: 1px solid var(--border-subtle);
  position: relative;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.panel-header::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 100%;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-active), transparent);
}

.profile-main {
  display: flex;
  align-items: center;
  gap: 20px;
  flex: 1;
}

.profile-avatar.large {
  width: 64px;
  height: 64px;
  font-size: 26px;
  /* background: linear-gradient(135deg, #5bcf89 0%, #3dce7e 100%); */
  /* background:transparent; */
  background: var(--neon-green-dim);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  /* color: #fff; */
  font-weight: bold;
  /* border: 1px solid rgba(91, 207, 137, 0.6); */
  box-shadow: var(--neon-green-glow);
}

.profile-avatar.large img {
  width: 100%;
  height: 100%;
  border-radius: var(--radius-md);
  object-fit: cover;
}

.profile-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.profile-name {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1.2;
  text-shadow: none;
}

.profile-role {
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}

.profile-role i {
  color: var(--neon-cyan);
}

.btn-fullscreen {
  background: var(--surface-1);
  border: 1px solid var(--border-subtle);
  color: var(--neon-cyan);
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
  font-size: 16px;
  flex-shrink: 0;
}

.btn-fullscreen:hover {
  background: var(--surface-hover);
  border-color: var(--border-active);
  box-shadow: var(--neon-cyan-glow);
}

.btn-fullscreen:active {
  transform: scale(0.95);
}

/* Nav Tabs */
.panel-nav {
  display: flex;
  padding: 0 12px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--surface-card);
}

.nav-tab {
  flex: 1;
  background: transparent;
  border: none;
  padding: 16px 0;
  font-size: 14px;
  font-weight: 600;
  min-height: 48px;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    color var(--duration-fast) var(--ease-spatial);
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.nav-tab:hover {
  color: var(--text-primary);
  background: var(--neon-cyan-dim);
}

.nav-tab.active {
  color: var(--text-primary);
  text-shadow: none;
}

.nav-tab.active i {
  color: var(--neon-cyan);
}

.nav-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 15%;
  width: 70%;
  height: 3px;
  border-radius: 3px 3px 0 0;
  background: var(--neon-cyan);
  box-shadow: var(--neon-cyan-glow);
}

/* Content Area */
.panel-body {
  height: 280px;
  overflow-y: auto;
  padding: 24px;
  position: relative;
}

.styled-scrollbar::-webkit-scrollbar {
  width: 5px;
}
.styled-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.styled-scrollbar::-webkit-scrollbar-thumb {
  background-color: var(--border-active);
  border-radius: 5px;
}
.styled-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: var(--border-glow);
}

/* View: Overview */
.info-card {
  background: var(--surface-card);
  border-radius: var(--radius-md);
  padding: 16px;
  border: 1px solid var(--border-subtle);
  margin-bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  box-shadow: var(--shadow-button);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
}

.info-label {
  color: var(--text-secondary);
}

.info-value {
  font-weight: 600;
  color: var(--text-primary);
}

.text-success { color: var(--neon-green); text-shadow: none; }
.active-dot { font-size: 10px; margin-right: 6px; vertical-align: middle; color: var(--neon-green); border-radius: 50%; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}

.stat-box {
  background: var(--surface-card);
  border-radius: var(--radius-md);
  padding: 16px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-subtle);
  transition:
    transform var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    background-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial);
  box-shadow: var(--shadow-button);
}

.stat-box:hover {
  transform: translateY(-2px);
  border-color: var(--border-active);
  background: var(--surface-hover);
  box-shadow: var(--shadow-panel);
}

.stat-icon {
  font-size: 20px;
  color: var(--neon-cyan);
  filter: none;
}

.stat-num {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  text-shadow: none;
}

.stat-name {
  font-size: 12px;
  color: var(--text-secondary);
}

.account-extra-card {
  margin-top: 12px;
}

.break-text {
  max-width: 200px;
  text-align: right;
  word-break: break-word;
}

.compose-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.user-message-input {
  width: 100%;
  min-height: 86px;
  box-sizing: border-box;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 14px;
  resize: vertical;
  color: var(--text-primary);
  background: var(--surface-card);
  transition:
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    background-color var(--duration-fast) var(--ease-spatial);
}

.user-message-input:focus {
  outline: none;
  border-color: var(--border-active);
  box-shadow: var(--shadow-focus);
  background: var(--surface-hover);
}

.message-list {
  max-height: 200px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
}

.message-empty {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 12px;
}

.message-item {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  padding: 10px 12px;
  transition: border-color 0.2s ease;
}

.message-item:hover {
  border-color: var(--border-active);
}

.message-item-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.message-author {
  color: var(--neon-cyan);
  font-weight: 700;
}

.message-item-content {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
  word-break: break-word;
}

.admin-view {
  display: flex;
  flex-direction: column;
}

.api-mgmt-view {
  display: flex;
  flex-direction: column;
}

/* View: Security */
.password-form-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 1px;
  border-left: 3px solid var(--neon-cyan);
  padding-left: 10px;
}

.modern-input-group {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 16px;
  color: var(--text-muted);
  font-size: 16px;
}

.modern-input-group input {
  width: 100%;
  height: 48px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0 16px 0 44px;
  font-size: 14px;
  color: var(--text-primary);
  transition:
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    background-color var(--duration-fast) var(--ease-spatial);
  background: var(--surface-card);
}

.modern-input-group input::placeholder {
  color: var(--text-muted);
}

.modern-input-group input:focus {
  outline: none;
  border-color: var(--border-active);
  box-shadow: var(--shadow-focus);
  background: var(--surface-hover);
}

.btn-primary {
  background: linear-gradient(135deg, var(--neon-cyan-dim), var(--neon-green-dim));
  color: var(--text-primary);
  border: 1px solid var(--border-active);
  height: 48px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  box-shadow: var(--shadow-button);
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
  margin-top: 8px;
  text-shadow: none;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: var(--neon-cyan-glow);
  border-color: var(--border-glow);
  background: linear-gradient(135deg, var(--neon-cyan-dim), var(--accent-amber-dim));
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  filter: grayscale(0.5);
}

.w-100 { width: 100%; }

.guest-warning {
  background: var(--accent-rose-dim);
  border: 1px solid rgba(239, 127, 138, 0.36);
  color: var(--accent-rose);
  padding: 20px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 16px;
  box-shadow: inset 0 0 12px rgba(239, 68, 68, 0.1);
}

.guest-warning i {
  font-size: 28px;
  color: var(--accent-rose);
  text-shadow: none;
}

.guest-warning p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
}

/* View: Preferences */
.pref-list {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.pref-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--surface-card);
  padding: 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  transition:
    border-color var(--duration-fast) var(--ease-spatial),
    background-color var(--duration-fast) var(--ease-spatial);
}

.pref-item:hover {
  border-color: var(--border-active);
  background: var(--surface-hover);
}

.pref-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pref-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
}

.pref-title i {
  color: var(--neon-cyan);
}

.pref-desc {
  font-size: 13px;
  color: var(--text-muted);
}

.pref-select {
  min-width: 150px;
  min-height: 40px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface-card);
  color: var(--text-primary);
  padding: 8px 10px;
}

.pref-select:focus {
  outline: none;
  border-color: var(--border-active);
  box-shadow: var(--shadow-focus);
}

.modern-toggle {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;
}

.modern-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: not-allowed;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: var(--surface-card);
  transition: transform var(--duration-normal) var(--ease-spring-subtle), background-color var(--duration-fast) var(--ease-spatial);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-subtle);
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px; width: 18px;
  left: 4px; bottom: 3px;
  background-color: var(--text-muted);
  transition: transform var(--duration-normal) var(--ease-spring-subtle), background-color var(--duration-fast) var(--ease-spatial);
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,0.5);
}

input:checked + .slider { 
  background-color: var(--neon-cyan-dim); 
  border-color: var(--border-active);
}
input:checked + .slider:before { 
  transform: translateX(20px); 
  background-color: var(--neon-cyan);
  box-shadow: var(--neon-cyan-glow);
}

.coming-soon {
  text-align: center;
  margin-top: 30px;
  color: var(--text-muted);
  font-size: 13px;
  font-style: italic;
  position: relative;
}

.coming-soon::before, .coming-soon::after {
  content: '';
  position: absolute;
  top: 50%;
  width: 25%;
  height: 1px;
  background: var(--border-subtle);
}

.coming-soon::before { left: 0; }
.coming-soon::after { right: 0; }

/* Avatar Selector */
.avatar-selector-item {
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 16px;
  padding-bottom: 12px;
}

.avatar-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 16px 0;
  margin: 12px 0;
}

.avatar-option {
  position: relative;
  aspect-ratio: 1;
  border: 2px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  cursor: pointer;
  transition:
    transform var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    background-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial);
  background: var(--surface-card);
}

.avatar-option img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}

.avatar-option:hover {
  border-color: var(--border-active);
  background: var(--surface-hover);
  transform: scale(1.03);
  box-shadow: var(--shadow-button);
}

.avatar-option.selected {
  border-color: var(--border-glow);
  background: var(--neon-cyan-dim);
  box-shadow: var(--shadow-focus), inset 0 0 0 2px var(--border-active);
}

.avatar-option.selected::after {
  content: '✓';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 20px;
  color: var(--neon-cyan);
  font-weight: bold;
  background: var(--surface-card-strong);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-button);
}

.avatar-save-btn {
  width: 100%;
  padding: 10px;
  margin-top: 12px;
  min-height: 44px;
  background: linear-gradient(135deg, var(--neon-cyan-dim), var(--neon-green-dim));
  border: 1px solid var(--border-active);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.avatar-save-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  border-color: var(--border-glow);
  box-shadow: var(--neon-cyan-glow);
  transform: translateY(-2px);
}

.avatar-save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.avatar-status {
  text-align: center;
  color: var(--neon-green);
  font-size: 13px;
  padding: 8px;
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.avatar-status i {
  font-size: 14px;
}

/* Footer Action */
.panel-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-subtle);
  position: relative;
}

.panel-footer::before {
  content: '';
  position: absolute;
  top: -1px;
  left: 0;
  width: 100%;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-active), transparent);
}

.btn-logout {
  width: 100%;
  height: 48px;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(239, 127, 138, 0.36);
  background: var(--accent-rose-dim);
  color: var(--accent-rose);
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition:
    background-color var(--duration-fast) var(--ease-spatial),
    border-color var(--duration-fast) var(--ease-spatial),
    color var(--duration-fast) var(--ease-spatial),
    box-shadow var(--duration-fast) var(--ease-spatial),
    transform var(--duration-fast) var(--ease-spatial);
}

.btn-logout:hover:not(:disabled) {
  background: var(--accent-rose-dim);
  border-color: var(--accent-rose);
  color: var(--text-primary);
  box-shadow: 0 0 14px var(--accent-rose-dim);
  transform: translateY(-1px);
}

/* Transitions */
.account-panel-transition-enter-active,
.account-panel-transition-leave-active {
  transition:
    opacity var(--duration-panel) var(--ease-spatial),
    transform var(--duration-panel) var(--ease-spring-subtle),
    filter var(--duration-normal) var(--ease-spatial);
}

.account-panel-transition-enter-from,
.account-panel-transition-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.96);
  filter: blur(8px);
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-spatial),
    transform var(--duration-normal) var(--ease-spatial);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(-15px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(15px);
}

/* Responsive Adjustments */
@media (max-width: 768px) {
  .floating-account-manager {
    top: 500px;
    left: 100px;
  }
  .account-panel {
    width: min(96vw, 420px);
  }

  /* Fullscreen mode on mobile */
  .account-panel.is-fullscreen {
    border-radius: 0;
    border: none;
  }

  .account-panel.is-fullscreen .panel-header {
    padding: 12px 16px;
  }

  .account-panel.is-fullscreen .profile-avatar.large {
    width: 48px;
    height: 48px;
    font-size: 20px;
  }

  .account-panel.is-fullscreen .profile-name {
    font-size: 16px;
  }

  .account-panel.is-fullscreen .panel-nav {
    flex-direction: column;
  }

  .account-panel.is-fullscreen .nav-tab {
    flex: none;
    width: 100%;
    justify-content: flex-start;
  }

  .account-panel.is-fullscreen .panel-body {
    padding: 16px;
    max-height: none;
  }

  .btn-fullscreen {
    width: 36px;
    height: 36px;
    font-size: 14px;
  }
}

@media (max-width: 480px) {
  .account-panel.is-fullscreen .panel-header {
    flex-direction: column;
    gap: 8px;
  }

  .account-panel.is-fullscreen .profile-main {
    gap: 12px;
  }

  .account-panel.is-fullscreen .panel-nav {
    padding: 0;
  }

  .account-panel.is-fullscreen .nav-tab {
    border-radius: 0;
    padding: 12px 16px;
  }
}
</style>
