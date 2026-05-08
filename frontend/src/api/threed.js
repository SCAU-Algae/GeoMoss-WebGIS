import { getAuthToken } from '../utils/auth';

const backendBase = String(import.meta.env.VITE_BACKEND_URL || '').replace(/\/$/, '');

function apiUrl(path) {
  const normalizedPath = String(path || '').startsWith('/') ? path : `/${path}`;
  return `${backendBase}${normalizedPath}`;
}

async function readJsonResponse(response, fallbackMessage) {
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = payload?.detail || payload?.message || fallbackMessage || `请求失败 (${response.status})`;
    throw new Error(detail);
  }

  return payload;
}

function parseJsonPayload(rawText, fallbackMessage) {
  try {
    return rawText ? JSON.parse(rawText) : null;
  } catch {
    throw new Error(fallbackMessage || '服务器返回内容无法解析');
  }
}

export async function previewShpZip(file, options = {}) {
  const formData = new FormData();
  formData.append('file', file);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.open('POST', apiUrl('/api/3d/preview-shp'));

    xhr.upload.onprogress = (event) => {
      if (typeof options.onUploadProgress !== 'function') return;
      const total = Number(event.total || file?.size || 0);
      const loaded = Number(event.loaded || 0);
      const percent = total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
      options.onUploadProgress({ loaded, total, percent });
    };

    xhr.onload = () => {
      try {
        const payload = parseJsonPayload(xhr.responseText, 'SHP 字段解析失败');
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(payload?.detail || payload?.message || `SHP 字段解析失败 (${xhr.status})`));
          return;
        }
        resolve(payload);
      } catch (error) {
        reject(error);
      }
    };

    xhr.onerror = () => reject(new Error('SHP 压缩包上传失败，请检查网络连接'));
    xhr.ontimeout = () => reject(new Error('SHP 压缩包上传超时，请稍后重试'));
    xhr.timeout = Number(options.timeout || 0) || 0;

    xhr.send(formData);
  });
}

export async function startShpTo3DJob(config = {}) {
  const token = getAuthToken();
  if (!token) {
    throw new Error('请先登录后再上传 3D 数据');
  }

  const response = await fetch(apiUrl('/api/3d/upload-shp'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      file_token: config.fileToken,
      height_field: config.heightField || '',
      base_color: config.baseColor || '#68c282',
      opacity: Number(config.opacity || 1),
      classification_field: config.classificationField || '',
      color_ramp: config.colorRamp || 'greens',
    }),
  });

  return readJsonResponse(response, 'SHP 转换任务提交失败');
}

export async function getShpTo3DJob(jobId) {
  const response = await fetch(apiUrl(`/api/3d/job/${encodeURIComponent(jobId)}`));
  return readJsonResponse(response, 'SHP 转换进度获取失败');
}

export async function cancelShpTo3DJob(jobId) {
  const token = getAuthToken();
  if (!token) {
    throw new Error('请先登录后再操作转换任务');
  }

  const response = await fetch(apiUrl(`/api/3d/job/${encodeURIComponent(jobId)}/cancel`), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return readJsonResponse(response, 'SHP 转换任务取消失败');
}

export async function listPublishedThreeDLayers() {
  const response = await fetch(apiUrl('/api/3d/layers/published'));
  return readJsonResponse(response, '3D 图层列表获取失败');
}

export async function listPublishedTerrainLayers() {
  const response = await fetch(apiUrl('/api/terrain/layers/published'));
  return readJsonResponse(response, '地形图层列表获取失败');
}

export function resolveThreeDTilesUrl(path) {
  const raw = String(path || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw) || raw.startsWith('blob:')) return raw;
  return apiUrl(raw);
}

export function resolveTerrainTileUrlTemplate(path) {
  const raw = String(path || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw) || raw.startsWith('blob:')) return raw;
  return apiUrl(raw);
}
