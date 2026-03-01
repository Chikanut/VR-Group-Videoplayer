const API_BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return res.json();
}

export async function getConfig() {
  return request('/config');
}

export async function updateConfig(config) {
  return request('/config', {
    method: 'PUT',
    body: JSON.stringify(config),
  });
}

export async function getDevices() {
  return request('/devices');
}

export async function getDevice(id) {
  return request(`/devices/${id}`);
}

export async function setDeviceName(id, name) {
  return request(`/devices/${id}/name`, {
    method: 'PUT',
    body: JSON.stringify({ name }),
  });
}

export async function removeDevice(id) {
  return request(`/devices/${id}`, { method: 'DELETE' });
}

export async function getRequirements(id) {
  return request(`/devices/${id}/requirements`);
}

export async function updateDevice(id) {
  return request(`/devices/${id}/update`, { method: 'POST' });
}

export async function updateAllDevices() {
  return request('/devices/update-all', { method: 'POST' });
}

export async function pingDevice(id) {
  return request(`/devices/${id}/ping`, { method: 'POST' });
}

export async function playbackOpen(videoId, deviceIds = [], ignoreRequirements = false) {
  return request('/playback/open', {
    method: 'POST',
    body: JSON.stringify({ videoId, deviceIds, ignoreRequirements }),
  });
}

export async function playbackCommand(command, deviceIds = []) {
  return request(`/playback/${command}`, {
    method: 'POST',
    body: JSON.stringify({ deviceIds }),
  });
}


export async function uploadLocalFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/files/upload`, {
    method: 'POST',
    body: formData,
  });
  return res.json();
}
