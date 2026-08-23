import { supabase } from './supabase';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function withNoCache(path) {
  const joiner = path.includes('?') ? '&' : '?';
  return `${path}${joiner}_ts=${Date.now()}`;
}

async function getAccessToken() {
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  return data.session?.access_token || null;
}

async function request(path, options = {}) {
  const token = await getAccessToken();
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      // Ignore body parse failure and preserve fallback message.
    }
    throw new Error(message);
  }

  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

async function requestBlobUrl(path, { cache } = {}) {
  const token = await getAccessToken();
  const headers = new Headers();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    headers,
    cache: cache ?? 'default',
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      // Keep fallback error message.
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

export const api = {
  baseUrl: API_BASE_URL,
  createProject: (payload) => request('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  saveStory: (projectId, payload) =>
    request(`/api/projects/${projectId}/story`, { method: 'POST', body: JSON.stringify(payload) }),
  previewScript: (projectId, payload = {}) =>
    request(`/api/projects/${projectId}/script/preview`, { method: 'POST', body: JSON.stringify(payload) }),
  runStage1: (projectId) => request(`/api/projects/${projectId}/run-stage1`, { method: 'POST' }),
  getRequirements: (projectId) => request(withNoCache(`/api/projects/${projectId}/requirements`)),
  uploadAsset: (projectId, requirementFolder, file) => {
    const form = new FormData();
    form.append('requirement_folder', requirementFolder);
    form.append('file', file);
    return request(`/api/projects/${projectId}/assets`, { method: 'POST', body: form });
  },
  removeAsset: (projectId, requirementFolder) => {
    const form = new FormData();
    form.append('requirement_folder', requirementFolder);
    return request(`/api/projects/${projectId}/assets/remove`, { method: 'POST', body: form });
  },
  getVoiceMap: (projectId) => request(withNoCache(`/api/projects/${projectId}/voice-map`)),
  getPacing: (projectId) => request(withNoCache(`/api/projects/${projectId}/pacing`)),
  savePacing: (projectId, clips = {}) =>
    request(`/api/projects/${projectId}/pacing`, { method: 'POST', body: JSON.stringify({ clips }) }),
  generateDramaTts: (projectId, { character = '', regenerate = false } = {}) => {
    const form = new FormData();
    if (character) form.append('character', character);
    if (regenerate) form.append('regenerate', 'true');
    return request(`/api/projects/${projectId}/tts-generate`, { method: 'POST', body: form });
  },
  runStage2: (projectId) => request(`/api/projects/${projectId}/run-stage2`, { method: 'POST' }),
  runCredits: (projectId) => request(`/api/projects/${projectId}/run-credits`, { method: 'POST' }),
  getStatus: (projectId) => request(withNoCache(`/api/projects/${projectId}/status`)),
  getOutput: (projectId, unitId = '', unitName = '') => {
    const params = new URLSearchParams();
    if (unitId) params.set('unit_id', unitId);
    if (unitName) params.set('unit_name', unitName);
    const query = params.toString();
    return request(`/api/projects/${projectId}/output${query ? `?${query}` : ''}`);
  },
  getCredits: (projectId) => request(`/api/projects/${projectId}/credits`),
  getOutputAudioBlobUrl: async (projectId, unitId = '', unitName = '') => {
    const output = await api.getOutput(projectId, unitId, unitName);
    const durationSeconds =
      typeof output?.duration_seconds === 'number' && Number.isFinite(output.duration_seconds)
        ? output.duration_seconds
        : null;
    if (!output?.url) {
      return { blobUrl: null, durationSeconds };
    }
    const blobUrl = await requestBlobUrl(output.url, { cache: 'no-store' });
    return { blobUrl, durationSeconds };
  },
  getRequirementAudioBlobUrl: (projectId, requirementId) =>
    requestBlobUrl(`/api/projects/${projectId}/requirements/${requirementId}/audio`),
  getCreditsAudioBlobUrl: async (projectId, slot) => {
    const credits = await request(`/api/projects/${projectId}/credits`);
    const item = (credits?.items || []).find((entry) => entry.slot === slot);
    if (!item?.url) {
      return null;
    }
    return requestBlobUrl(item.url);
  },
};

