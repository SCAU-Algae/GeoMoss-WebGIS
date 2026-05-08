import backendAPI from './backend';

export async function apiFengshuiStatus() {
  return backendAPI.get('/api/fengshui/status');
}

export async function apiAnalyzeFengshui(payload = {}) {
  return backendAPI.post('/api/fengshui/analyze', payload, { timeout: 180000 });
}
