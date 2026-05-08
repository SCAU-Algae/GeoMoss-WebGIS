<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Database as DatabaseIcon,
  FileArchive as FileArchiveIcon,
  Grid3X3 as GridIcon,
  Layers3 as Layers3Icon,
  Play as PlayIcon,
  RefreshCw as RefreshIcon,
  ShieldCheck as ShieldCheckIcon,
  Trash2 as TrashIcon,
  Upload as UploadIcon
} from 'lucide-vue-next'
import { useMessage } from '../../composables/useMessage'
import {
  apiAdminCancelGeodataJob,
  apiAdminConfirmBoundaryDataset,
  apiAdminCreateThreeDLayer,
  apiAdminDeleteBoundaryDataset,
  apiAdminDeleteThreeDLayer,
  apiAdminListBoundaryDatasets,
  apiAdminListGeodataJobs,
  apiAdminListTerrainLayers,
  apiAdminListThreeDLayers,
  apiAdminPublishGuangdongDem,
  apiAdminPreviewBoundaryDataset,
  apiAdminPreviewThreeDSource,
  apiAdminUpdateThreeDLayerStatus
} from '../../api/backend'

const message = useMessage()

const boundaryFileInput = ref(null)
const threeDFileInput = ref(null)

const boundaries = ref([])
const threeDLayers = ref([])
const terrainLayers = ref([])
const jobs = ref([])
const boundaryPreview = ref(null)
const threeDPreview = ref(null)

const loading = ref(false)
const boundaryUploading = ref(false)
const boundarySaving = ref(false)
const threeDUploading = ref(false)
const threeDCreating = ref(false)
const terrainPublishing = ref(false)
const boundaryUploadPercent = ref(0)
const threeDUploadPercent = ref(0)
let jobsTimer = null

const splitMode = ref('grid')

const boundaryForm = ref({
  name: '',
  field_code: '',
  field_name: '',
  field_level: ''
})

const threeDForm = ref({
  name: '',
  description: '',
  height_field: '',
  base_color: '#2d8cff',
  opacity: 1,
  classification_field: '',
  color_ramp: 'cool',
  boundary_dataset_id: '',
  grid_width_m: 1000,
  grid_height_m: 1000,
  tile_batch_size: 1500,
  publish_when_done: true
})

const boundaryFields = computed(() => Array.isArray(boundaryPreview.value?.fields) ? boundaryPreview.value.fields : [])
const threeDFields = computed(() => Array.isArray(threeDPreview.value?.fields) ? threeDPreview.value.fields : [])
const hasReadyBoundary = computed(() => boundaries.value.some((item) => String(item?.status || '') === 'ready'))
const activeJobs = computed(() => jobs.value.filter((job) => ['queued', 'running', 'processing'].includes(String(job?.status || '').toLowerCase())))
const selectedBoundaryName = computed(() => {
  const found = boundaries.value.find((item) => String(item?.id || '') === String(threeDForm.value.boundary_dataset_id || ''))
  return found?.name || ''
})

const canConfirmBoundary = computed(() => {
  return !!boundaryPreview.value?.file_token
    && boundaryForm.value.name.trim()
    && boundaryForm.value.field_code
    && boundaryForm.value.field_name
})

const splitReady = computed(() => {
  if (splitMode.value === 'grid') {
    return Number(threeDForm.value.grid_width_m) >= 50 && Number(threeDForm.value.grid_height_m) >= 50
  }
  return !!threeDForm.value.boundary_dataset_id && hasReadyBoundary.value
})

const canCreateThreeDLayer = computed(() => {
  if (!threeDPreview.value?.file_token) return false
  if (!threeDForm.value.name.trim()) return false
  return splitReady.value
})

watch(splitMode, (mode) => {
  if (mode === 'admin_boundary' && !threeDForm.value.boundary_dataset_id && boundaries.value.length) {
    threeDForm.value.boundary_dataset_id = String(boundaries.value[0]?.id || '')
  }
})

function formatNumber(value) {
  const number = Number(value || 0)
  if (!Number.isFinite(number)) return '0'
  return number.toLocaleString('zh-CN')
}

function formatDateTime(value) {
  const raw = String(value || '').trim()
  if (!raw) return '-'
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

function statusLabel(status) {
  const map = {
    ready: '就绪',
    processing: '处理中',
    published: '已发布',
    archived: '已归档',
    error: '失败',
    queued: '排队',
    running: '运行中',
    done: '完成',
    cancelled: '已取消'
  }
  return map[String(status || '').toLowerCase()] || String(status || '未知')
}

function terrainModeLabel(layer) {
  const metadata = layer?.metadata && typeof layer.metadata === 'object' ? layer.metadata : {}
  if (metadata.crop_mode === 'admin_boundary') return '行政区边界裁剪'
  if (metadata.crop_mode === 'admin_boundary_bbox') return '行政区外包框裁剪'
  if (metadata.fallback_bbox) return '广东外包框裁剪'
  return metadata.crop_mode || 'DEM 裁剪'
}

function formatHeightRange(layer) {
  const min = Number(layer?.min_height || 0)
  const max = Number(layer?.max_height || 0)
  if (!Number.isFinite(min) || !Number.isFinite(max)) return '-'
  return `${Math.round(min)}m ~ ${Math.round(max)}m`
}

function progressPercent(job) {
  return Math.max(0, Math.min(100, Math.round(Number(job?.progress || 0) * 100)))
}

function uploadProgressSetter(targetRef) {
  return (event) => {
    const total = Number(event?.total || 0)
    const loaded = Number(event?.loaded || 0)
    targetRef.value = total > 0 ? Math.max(1, Math.min(100, Math.round((loaded / total) * 100))) : 8
  }
}

function resetBoundaryPreview() {
  boundaryPreview.value = null
  boundaryUploadPercent.value = 0
  boundaryForm.value = {
    name: '',
    field_code: '',
    field_name: '',
    field_level: ''
  }
}

function resetThreeDPreview() {
  threeDPreview.value = null
  threeDUploadPercent.value = 0
  threeDForm.value = {
    ...threeDForm.value,
    name: '',
    description: '',
    height_field: '',
    base_color: '#2d8cff',
    opacity: 1,
    classification_field: '',
    color_ramp: 'cool',
    publish_when_done: true
  }
}

async function loadGeodataState({ silent = false } = {}) {
  if (loading.value) return
  loading.value = true
  try {
    const [boundaryResult, layerResult, terrainResult, jobsResult] = await Promise.all([
      apiAdminListBoundaryDatasets(),
      apiAdminListThreeDLayers(),
      apiAdminListTerrainLayers().catch(() => ({ data: [] })),
      apiAdminListGeodataJobs(30)
    ])
    boundaries.value = Array.isArray(boundaryResult?.data) ? boundaryResult.data : []
    threeDLayers.value = Array.isArray(layerResult?.data) ? layerResult.data : []
    terrainLayers.value = Array.isArray(terrainResult?.data) ? terrainResult.data : []
    jobs.value = Array.isArray(jobsResult?.data) ? jobsResult.data : []
    if (!threeDForm.value.boundary_dataset_id && boundaries.value.length) {
      threeDForm.value.boundary_dataset_id = String(boundaries.value[0]?.id || '')
    }
  } catch (error) {
    if (!silent) message.error(String(error?.message || '地理数据状态加载失败'))
  } finally {
    loading.value = false
  }
}

async function publishGuangdongDem() {
  if (terrainPublishing.value) return
  terrainPublishing.value = true
  try {
    await apiAdminPublishGuangdongDem()
    message.success('广东省 DEM 地形已发布')
    await loadGeodataState({ silent: true })
  } catch (error) {
    message.error(String(error?.message || 'DEM 地形发布失败'))
  } finally {
    terrainPublishing.value = false
  }
}

async function refreshJobs({ silent = true } = {}) {
  try {
    const result = await apiAdminListGeodataJobs(30)
    jobs.value = Array.isArray(result?.data) ? result.data : []
  } catch (error) {
    if (!silent) message.warning(String(error?.message || '任务列表刷新失败'))
  }
}

function triggerBoundaryUpload() {
  boundaryFileInput.value?.click()
}

function triggerThreeDUpload() {
  if (!splitReady.value) {
    message.warning(splitMode.value === 'grid' ? '请先设置有效网格尺寸' : '请先选择或上传行政区划数据')
    return
  }
  threeDFileInput.value?.click()
}

function isBoundaryComponentFile(file) {
  return /\.(shp|dbf|shx|prj|cpg)$/i.test(String(file?.name || ''))
}

async function handleBoundaryFileChange(event) {
  const files = Array.from(event.target?.files || [])
  event.target.value = ''
  if (!files.length) return

  const invalid = files.filter((file) => !isBoundaryComponentFile(file))
  if (invalid.length) {
    message.warning(`行政区划只支持 .shp/.dbf/.shx/.prj/.cpg：${invalid.map((file) => file.name).join(', ')}`)
    return
  }

  const extensions = new Set(files.map((file) => String(file.name || '').split('.').pop()?.toLowerCase()))
  const missing = ['shp', 'dbf', 'shx'].filter((ext) => !extensions.has(ext))
  if (missing.length) {
    message.warning(`请同时选择完整 Shapefile 组件，缺少：${missing.map((ext) => `.${ext}`).join('、')}`)
    return
  }

  if (extensions.size !== files.length) {
    message.warning('同一套 Shapefile 每种组件只能选择一个文件')
    return
  }

  const stems = new Set(files.map((file) => String(file.name || '').replace(/\.[^.]+$/i, '').toLowerCase()))
  if (stems.size > 1) {
    message.warning('请选择同一套 Shapefile 组件文件，文件主名需要一致')
    return
  }

  boundaryUploading.value = true
  boundaryUploadPercent.value = 1
  try {
    const result = await apiAdminPreviewBoundaryDataset(files, uploadProgressSetter(boundaryUploadPercent))
    boundaryPreview.value = result
    const shpFile = files.find((file) => /\.shp$/i.test(file.name))
    boundaryForm.value.name = String(shpFile?.name || files[0]?.name || '').replace(/\.[^.]+$/i, '')
    const fields = Array.isArray(result?.fields) ? result.fields : []
    boundaryForm.value.field_code = fields.find((field) => /adcode|code|编码|区划/i.test(field)) || fields[0] || ''
    boundaryForm.value.field_name = fields.find((field) => /name|名称|县|区|市/i.test(field)) || fields[1] || fields[0] || ''
    boundaryForm.value.field_level = fields.find((field) => /level|级别|层级|type/i.test(field)) || ''
    boundaryUploadPercent.value = 100
    message.success('行政区划字段解析完成')
  } catch (error) {
    resetBoundaryPreview()
    message.error(String(error?.message || '行政区划解析失败'))
  } finally {
    boundaryUploading.value = false
  }
}

async function confirmBoundaryDataset() {
  if (!canConfirmBoundary.value || boundarySaving.value) return
  boundarySaving.value = true
  try {
    const result = await apiAdminConfirmBoundaryDataset({
      file_token: boundaryPreview.value.file_token,
      name: boundaryForm.value.name.trim(),
      field_code: boundaryForm.value.field_code,
      field_name: boundaryForm.value.field_name,
      field_level: boundaryForm.value.field_level || ''
    })
    message.success('行政区划数据集已入库')
    const datasetId = String(result?.data?.id || '')
    resetBoundaryPreview()
    await loadGeodataState({ silent: true })
    if (datasetId) {
      splitMode.value = 'admin_boundary'
      threeDForm.value.boundary_dataset_id = datasetId
    }
  } catch (error) {
    message.error(String(error?.message || '行政区划入库失败'))
  } finally {
    boundarySaving.value = false
  }
}

async function deleteBoundaryDataset(dataset) {
  const id = String(dataset?.id || '')
  if (!id) return
  if (!window.confirm(`确认删除行政区划数据集「${dataset?.name || id}」？`)) return
  try {
    await apiAdminDeleteBoundaryDataset(id)
    message.success('行政区划数据集已删除')
    if (threeDForm.value.boundary_dataset_id === id) {
      threeDForm.value.boundary_dataset_id = ''
      splitMode.value = 'grid'
    }
    await loadGeodataState({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '删除失败'))
  }
}

async function handleThreeDFileChange(event) {
  const file = event.target?.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.zip')) {
    message.warning('3D 图层源数据请上传 Shapefile ZIP 压缩包')
    return
  }

  threeDUploading.value = true
  threeDUploadPercent.value = 1
  try {
    const result = await apiAdminPreviewThreeDSource(file, uploadProgressSetter(threeDUploadPercent))
    threeDPreview.value = result
    threeDForm.value.name = file.name.replace(/\.zip$/i, '')
    threeDForm.value.height_field = result?.suggested_height_field || ''
    threeDForm.value.classification_field = ''
    threeDUploadPercent.value = 100
    message.success('3D 源数据字段解析完成')
  } catch (error) {
    resetThreeDPreview()
    message.error(String(error?.message || '3D 源数据解析失败'))
  } finally {
    threeDUploading.value = false
  }
}

async function createThreeDLayer() {
  if (!canCreateThreeDLayer.value || threeDCreating.value) return
  threeDCreating.value = true
  try {
    await apiAdminCreateThreeDLayer({
      file_token: threeDPreview.value.file_token,
      name: threeDForm.value.name.trim(),
      description: threeDForm.value.description.trim(),
      height_field: threeDForm.value.height_field || '',
      base_color: threeDForm.value.base_color || '#2d8cff',
      opacity: Number(threeDForm.value.opacity || 1),
      classification_field: threeDForm.value.classification_field || '',
      color_ramp: threeDForm.value.color_ramp || 'cool',
      split_strategy: splitMode.value,
      boundary_dataset_id: splitMode.value === 'admin_boundary' ? threeDForm.value.boundary_dataset_id : '',
      grid_width_m: Number(threeDForm.value.grid_width_m || 1000),
      grid_height_m: Number(threeDForm.value.grid_height_m || 1000),
      tile_batch_size: Number(threeDForm.value.tile_batch_size || 1500),
      publish_when_done: threeDForm.value.publish_when_done === true
    })
    message.success('3D 图层生产任务已创建')
    resetThreeDPreview()
    await loadGeodataState({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '3D 图层任务创建失败'))
  } finally {
    threeDCreating.value = false
  }
}

async function updateLayerStatus(layer, nextStatus) {
  const id = String(layer?.id || '')
  if (!id) return
  try {
    await apiAdminUpdateThreeDLayerStatus(id, nextStatus)
    message.success(nextStatus === 'published' ? '3D 图层已发布' : '3D 图层状态已更新')
    await loadGeodataState({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '状态更新失败'))
  }
}

async function deleteThreeDLayer(layer) {
  const id = String(layer?.id || '')
  if (!id) return
  if (!window.confirm(`确认删除 3D 图层「${layer?.name || id}」及其瓦片文件？`)) return
  try {
    await apiAdminDeleteThreeDLayer(id)
    message.success('3D 图层已删除')
    await loadGeodataState({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '删除失败'))
  }
}

async function cancelJob(job) {
  const id = String(job?.job_id || '')
  if (!id) return
  try {
    await apiAdminCancelGeodataJob(id)
    message.success('任务取消请求已提交')
    await refreshJobs({ silent: true })
  } catch (error) {
    message.error(String(error?.message || '任务取消失败'))
  }
}

onMounted(() => {
  loadGeodataState()
  jobsTimer = window.setInterval(() => refreshJobs({ silent: true }), 3500)
})

onUnmounted(() => {
  if (jobsTimer) window.clearInterval(jobsTimer)
})
</script>

<template>
  <section class="geodata-panel">
    <input
      ref="boundaryFileInput"
      class="hidden-input"
      type="file"
      multiple
      accept=".shp,.dbf,.shx,.prj,.cpg"
      @change="handleBoundaryFileChange"
    />
    <input ref="threeDFileInput" class="hidden-input" type="file" accept=".zip" @change="handleThreeDFileChange" />

    <div class="geo-header">
      <div>
        <div class="geo-eyebrow">
          <shield-check-icon :size="15" />
          管理员专属
        </div>
        <h5>空间数据生产链路</h5>
      </div>
      <button class="geo-icon-btn" type="button" :disabled="loading" title="刷新" @click="loadGeodataState">
        <refresh-icon :size="16" />
      </button>
    </div>

    <div class="geo-summary">
      <div class="summary-cell">
        <database-icon :size="16" />
        <span>行政区划</span>
        <strong>{{ boundaries.length }}</strong>
      </div>
      <div class="summary-cell">
        <layers3-icon :size="16" />
        <span>3D 图层</span>
        <strong>{{ threeDLayers.length }}</strong>
      </div>
      <div class="summary-cell">
        <database-icon :size="16" />
        <span>地形图层</span>
        <strong>{{ terrainLayers.length }}</strong>
      </div>
      <div class="summary-cell">
        <play-icon :size="16" />
        <span>运行任务</span>
        <strong>{{ activeJobs.length }}</strong>
      </div>
    </div>

    <div class="geo-card">
      <div class="geo-card-head">
        <div>
          <h6>1. 选择切分方式</h6>
          <p>网格切分直接输入长宽；行政区切分需要先提供行政区划 Shapefile 组件。</p>
        </div>
      </div>

      <div class="strategy-tabs">
        <button class="strategy-tab" :class="{ active: splitMode === 'grid' }" type="button" @click="splitMode = 'grid'">
          <grid-icon :size="16" />
          网格切分
        </button>
        <button
          class="strategy-tab"
          :class="{ active: splitMode === 'admin_boundary' }"
          type="button"
          @click="splitMode = 'admin_boundary'"
        >
          <database-icon :size="16" />
          行政区切分
        </button>
      </div>

      <div v-if="splitMode === 'grid'" class="mode-config">
        <div class="form-grid">
          <label>
            网格宽度（米）
            <input v-model.number="threeDForm.grid_width_m" class="geo-input" type="number" min="50" step="50" />
          </label>
          <label>
            网格高度（米）
            <input v-model.number="threeDForm.grid_height_m" class="geo-input" type="number" min="50" step="50" />
          </label>
          <label>
            单瓦片批量
            <input v-model.number="threeDForm.tile_batch_size" class="geo-input" type="number" min="100" max="10000" step="100" />
          </label>
        </div>
      </div>

      <div v-else class="mode-config">
        <div class="geo-card-head nested">
          <div>
            <h6>行政区划数据</h6>
            <p>请选择同一套 Shapefile 的 .shp、.dbf、.shx 文件；.prj/.cpg 可选。</p>
          </div>
          <button class="geo-action small" type="button" :disabled="boundaryUploading" @click="triggerBoundaryUpload">
            <upload-icon :size="15" />
            上传 SHP 组件
          </button>
        </div>

        <div v-if="boundaryUploading || boundaryPreview" class="preview-box">
          <div class="progress-row">
            <span>{{ boundaryUploading ? '上传解析中' : '解析完成' }}</span>
            <span>{{ boundaryUploadPercent }}%</span>
          </div>
          <div class="progress-track"><div class="progress-fill" :style="{ width: `${boundaryUploadPercent}%` }"></div></div>
          <div v-if="boundaryPreview" class="form-grid">
            <label>
              数据集名称
              <input v-model.trim="boundaryForm.name" class="geo-input" />
            </label>
            <label>
              区划编码字段
              <select v-model="boundaryForm.field_code" class="geo-input">
                <option v-for="field in boundaryFields" :key="field" :value="field">{{ field }}</option>
              </select>
            </label>
            <label>
              区划名称字段
              <select v-model="boundaryForm.field_name" class="geo-input">
                <option v-for="field in boundaryFields" :key="field" :value="field">{{ field }}</option>
              </select>
            </label>
            <label>
              级别字段
              <select v-model="boundaryForm.field_level" class="geo-input">
                <option value="">不使用</option>
                <option v-for="field in boundaryFields" :key="field" :value="field">{{ field }}</option>
              </select>
            </label>
          </div>
          <div v-if="boundaryPreview" class="preview-meta">
            要素 {{ formatNumber(boundaryPreview.record_count) }} 个，字段 {{ boundaryFields.length }} 个
          </div>
          <div v-if="boundaryPreview" class="action-row">
            <button class="geo-action secondary" type="button" @click="resetBoundaryPreview">取消</button>
            <button class="geo-action" type="button" :disabled="!canConfirmBoundary || boundarySaving" @click="confirmBoundaryDataset">
              确认入库并使用
            </button>
          </div>
        </div>

        <div class="dataset-list">
          <div v-if="!boundaries.length" class="empty-line">暂无行政区划数据集</div>
          <div v-for="item in boundaries" :key="item.id" class="dataset-row" :class="{ selected: item.id === threeDForm.boundary_dataset_id }">
            <label class="dataset-select">
              <input v-model="threeDForm.boundary_dataset_id" type="radio" :value="item.id" />
              <span>
                <strong>{{ item.name }}</strong>
                <em>{{ item.field_code }} / {{ item.field_name }} · {{ formatNumber(item.feature_count) }} 个区划</em>
              </span>
            </label>
            <button class="geo-icon-btn danger" type="button" title="删除" @click="deleteBoundaryDataset(item)">
              <trash-icon :size="15" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="geo-card">
      <div class="geo-card-head">
        <div>
          <h6>2. 上传 3D 图层源数据</h6>
          <p>
            当前切分方式：
            <strong>{{ splitMode === 'grid' ? `网格 ${threeDForm.grid_width_m}m × ${threeDForm.grid_height_m}m` : (selectedBoundaryName || '未选择行政区划') }}</strong>
          </p>
        </div>
        <button class="geo-action small" type="button" :disabled="threeDUploading || !splitReady" @click="triggerThreeDUpload">
          <file-archive-icon :size="15" />
          上传 ZIP
        </button>
      </div>

      <div v-if="threeDUploading || threeDPreview" class="preview-box">
        <div class="progress-row">
          <span>{{ threeDUploading ? '上传解析中' : '解析完成' }}</span>
          <span>{{ threeDUploadPercent }}%</span>
        </div>
        <div class="progress-track"><div class="progress-fill" :style="{ width: `${threeDUploadPercent}%` }"></div></div>
        <div v-if="threeDPreview" class="form-grid">
          <label>
            图层名称
            <input v-model.trim="threeDForm.name" class="geo-input" />
          </label>
          <label>
            高度字段
            <select v-model="threeDForm.height_field" class="geo-input">
              <option value="">自动检测</option>
              <option v-for="field in threeDFields" :key="field" :value="field">{{ field }}</option>
            </select>
          </label>
          <label>
            基础颜色
            <input v-model="threeDForm.base_color" class="geo-input color-control" type="color" />
          </label>
          <label>
            透明度
            <input v-model.number="threeDForm.opacity" class="geo-input" type="number" min="0.1" max="1" step="0.1" />
          </label>
          <label>
            分级字段
            <select v-model="threeDForm.classification_field" class="geo-input">
              <option value="">不使用</option>
              <option v-for="field in threeDFields" :key="field" :value="field">{{ field }}</option>
            </select>
          </label>
          <label>
            色带
            <select v-model="threeDForm.color_ramp" class="geo-input">
              <option value="greens">青绿</option>
              <option value="blues">蓝色</option>
              <option value="reds">红色</option>
              <option value="warm">暖色</option>
              <option value="cool">冷色</option>
            </select>
          </label>
        </div>
        <label v-if="threeDPreview" class="checkbox-row">
          <input v-model="threeDForm.publish_when_done" type="checkbox" />
          转换完成后自动发布给普通用户
        </label>
        <label v-if="threeDPreview" class="full-row">
          图层说明
          <textarea v-model.trim="threeDForm.description" class="geo-input geo-textarea"></textarea>
        </label>
        <div v-if="threeDPreview" class="preview-meta">
          要素 {{ formatNumber(threeDPreview.record_count) }} 个，字段 {{ threeDFields.length }} 个
        </div>
        <div v-if="threeDPreview" class="action-row">
          <button class="geo-action secondary" type="button" @click="resetThreeDPreview">取消</button>
          <button class="geo-action" type="button" :disabled="!canCreateThreeDLayer || threeDCreating" @click="createThreeDLayer">
            创建后台任务
          </button>
        </div>
      </div>
    </div>

    <div class="geo-card">
      <div class="geo-card-head compact">
        <h6>3. 3D 图层发布</h6>
        <span>{{ threeDLayers.length }} 个</span>
      </div>
      <div class="dataset-list">
        <div v-if="!threeDLayers.length" class="empty-line">暂无 3D 图层</div>
        <div v-for="layer in threeDLayers" :key="layer.id" class="layer-row">
          <div class="layer-main">
            <strong>{{ layer.name }}</strong>
            <span>{{ statusLabel(layer.status) }} · {{ formatNumber(layer.feature_count) }} 个要素</span>
          </div>
          <div class="layer-actions">
            <button
              class="geo-mini"
              type="button"
              :disabled="layer.status === 'processing' || layer.status === 'published'"
              @click="updateLayerStatus(layer, 'published')"
            >
              发布
            </button>
            <button
              class="geo-mini"
              type="button"
              :disabled="layer.status === 'processing' || layer.status === 'ready'"
              @click="updateLayerStatus(layer, 'ready')"
            >
              下架
            </button>
            <button class="geo-icon-btn danger" type="button" title="删除" @click="deleteThreeDLayer(layer)">
              <trash-icon :size="15" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="geo-card">
      <div class="geo-card-head">
        <div>
          <h6>4. DEM 地形发布</h6>
          <p>从服务器全国 DEM 裁剪广东省地形，并作为普通用户可开关的三维图层发布。</p>
        </div>
        <button class="geo-action small" type="button" :disabled="terrainPublishing" @click="publishGuangdongDem">
          <database-icon :size="15" />
          {{ terrainPublishing ? '发布中' : '裁剪并发布' }}
        </button>
      </div>
      <div v-if="terrainPublishing" class="preview-box">
        <div class="progress-row">
          <span>正在调用 GDAL 裁剪 DEM</span>
          <span>请稍候</span>
        </div>
        <div class="progress-track"><div class="progress-fill indeterminate"></div></div>
      </div>
      <div class="dataset-list">
        <div v-if="!terrainLayers.length" class="empty-line">暂无地形图层</div>
        <div v-for="layer in terrainLayers" :key="layer.id" class="layer-row">
          <div class="layer-main">
            <strong>{{ layer.name }}</strong>
            <span>
              {{ statusLabel(layer.status) }} · {{ terrainModeLabel(layer) }} · {{ formatHeightRange(layer) }}
            </span>
          </div>
          <div class="layer-actions">
            <span class="geo-pill">{{ formatNumber(layer.width) }} × {{ formatNumber(layer.height) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="geo-card">
      <div class="geo-card-head compact">
        <h6>后台任务</h6>
        <button class="geo-mini" type="button" @click="refreshJobs({ silent: false })">刷新</button>
      </div>
      <div class="job-list">
        <div v-if="!jobs.length" class="empty-line">暂无任务</div>
        <div v-for="job in jobs" :key="job.job_id" class="job-row">
          <div class="job-top">
            <strong>{{ statusLabel(job.status) }}</strong>
            <span>{{ progressPercent(job) }}%</span>
          </div>
          <div class="progress-track"><div class="progress-fill" :class="`status-${job.status}`" :style="{ width: `${progressPercent(job)}%` }"></div></div>
          <div class="job-meta">
            <span>{{ job.message || job.phase }}</span>
            <span>{{ formatDateTime(job.updated_at) }}</span>
          </div>
          <button
            v-if="['queued', 'running'].includes(String(job.status || ''))"
            class="geo-mini danger"
            type="button"
            @click="cancelJob(job)"
          >
            取消任务
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.geodata-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--text-primary);
}

.hidden-input {
  display: none;
}

.geo-header,
.geo-card-head,
.action-row,
.layer-actions,
.job-top,
.job-meta,
.progress-row,
.dataset-select {
  display: flex;
  align-items: center;
}

.geo-header,
.geo-card-head {
  justify-content: space-between;
  gap: 12px;
}

.geo-header h5,
.geo-card h6 {
  margin: 0;
  color: var(--text-primary);
}

.geo-header h5 {
  font-size: 15px;
}

.geo-card h6 {
  font-size: 14px;
}

.geo-card-head p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.geo-card-head.compact {
  margin-bottom: 10px;
}

.geo-card-head.nested {
  margin-top: 4px;
}

.geo-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--neon-cyan);
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}

.geo-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.summary-cell {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  padding: 10px;
  display: grid;
  gap: 4px;
  color: var(--text-secondary);
  box-shadow: var(--shadow-button);
}

.summary-cell svg {
  color: var(--neon-cyan);
}

.summary-cell span {
  font-size: 12px;
  color: var(--text-muted);
}

.summary-cell strong {
  font-size: 18px;
  color: var(--text-primary);
}

.geo-card,
.preview-box,
.dataset-row,
.layer-row,
.job-row {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-card);
  box-shadow: var(--shadow-button);
}

.geo-card {
  padding: 12px;
}

.mode-config,
.preview-box {
  margin-top: 12px;
}

.mode-config {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}

.preview-box {
  padding: 12px;
  background: rgba(6, 11, 16, 0.46);
}

.progress-row,
.job-top,
.job-meta {
  justify-content: space-between;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.progress-track {
  height: 7px;
  border-radius: var(--radius-full);
  background: rgba(45, 140, 255, 0.14);
  overflow: hidden;
  margin: 8px 0;
}

.progress-fill {
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--neon-cyan), var(--accent-blue));
  box-shadow: var(--neon-cyan-glow);
  transition: width 220ms var(--ease-spatial);
}

.progress-fill.indeterminate {
  width: 42%;
  min-width: 42%;
  animation: geo-progress-scan 1.15s ease-in-out infinite;
}

@keyframes geo-progress-scan {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(245%); }
}

.progress-fill.status-error,
.progress-fill.status-cancelled {
  background: linear-gradient(90deg, #ef4444, #f97316);
  box-shadow: none;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.form-grid label,
.full-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.geo-input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: rgba(6, 11, 16, 0.62);
  color: var(--text-primary);
  padding: 9px 10px;
  font-size: 13px;
}

.geo-input:focus {
  outline: none;
  border-color: var(--border-active);
  box-shadow: var(--neon-cyan-glow);
}

.color-control {
  height: 38px;
  padding: 4px;
}

.geo-textarea {
  min-height: 72px;
  resize: vertical;
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.full-row {
  margin-top: 12px;
}

.preview-meta {
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.action-row {
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.geo-action,
.geo-mini,
.geo-icon-btn,
.strategy-tab,
.geo-pill {
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.geo-action,
.geo-mini,
.geo-icon-btn,
.strategy-tab {
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-spatial);
}

.geo-action {
  min-height: 38px;
  padding: 0 12px;
  background: var(--neon-cyan-dim);
  color: var(--neon-cyan);
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.geo-action.small {
  min-height: 34px;
}

.geo-action.secondary,
.geo-mini {
  background: var(--surface-1);
  color: var(--text-secondary);
}

.geo-icon-btn {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-1);
  color: var(--text-secondary);
}

.geo-mini {
  min-height: 30px;
  padding: 0 10px;
  font-size: 12px;
}

.geo-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 9px;
  color: var(--text-muted);
  background: var(--surface-1);
  font-size: 12px;
  white-space: nowrap;
}

.geo-action:hover:not(:disabled),
.geo-mini:hover:not(:disabled),
.geo-icon-btn:hover:not(:disabled),
.strategy-tab:hover:not(:disabled) {
  color: var(--neon-cyan);
  border-color: var(--border-active);
  transform: translateY(-1px);
  box-shadow: var(--neon-cyan-glow);
}

.geo-action:disabled,
.geo-mini:disabled,
.geo-icon-btn:disabled,
.strategy-tab:disabled {
  opacity: 0.48;
  cursor: not-allowed;
  transform: none;
}

.danger {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.35);
}

.dataset-list,
.job-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.dataset-row,
.layer-row {
  padding: 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.dataset-row.selected {
  border-color: var(--border-active);
  background: var(--neon-cyan-dim);
}

.dataset-select {
  gap: 8px;
  min-width: 0;
  cursor: pointer;
}

.dataset-select span {
  min-width: 0;
}

.dataset-row strong,
.layer-row strong {
  display: block;
  color: var(--text-primary);
  font-size: 13px;
  margin-bottom: 4px;
}

.dataset-row em,
.dataset-row span,
.layer-row span {
  color: var(--text-muted);
  font-size: 12px;
  font-style: normal;
}

.layer-actions {
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.strategy-tabs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.strategy-tab {
  min-height: 44px;
  background: var(--surface-1);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  font-weight: 700;
}

.strategy-tab.active {
  color: var(--neon-cyan);
  background: var(--neon-cyan-dim);
  border-color: var(--border-active);
  box-shadow: var(--neon-cyan-glow);
}

.job-row {
  padding: 10px;
}

.job-meta {
  align-items: flex-start;
}

.empty-line {
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 14px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

@media (max-width: 720px) {
  .geo-summary,
  .form-grid,
  .strategy-tabs {
    grid-template-columns: 1fr;
  }

  .dataset-row,
  .layer-row {
    grid-template-columns: 1fr;
  }

  .layer-actions {
    justify-content: flex-start;
  }
}
</style>
