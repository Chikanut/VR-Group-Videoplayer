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

export async function getDeviceNames() {
  return request('/device-names');
}

export async function replaceDeviceNames(deviceNames) {
  return request('/device-names', {
    method: 'PUT',
    body: JSON.stringify(deviceNames),
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

export async function pingDevice(id) {
  return request(`/devices/${id}/ping`, { method: 'POST' });
}

export async function playbackOpen(videoId, deviceIds = []) {
  return request('/playback/open', {
    method: 'POST',
    body: JSON.stringify({ videoId, deviceIds }),
  });
}

export async function playbackCommand(command, deviceIds = []) {
  return request(`/playback/${command}`, {
    method: 'POST',
    body: JSON.stringify({ deviceIds }),
  });
}

export async function playbackSeek(time, deviceIds = []) {
  return request('/playback/seek', {
    method: 'POST',
    body: JSON.stringify({ time, deviceIds }),
  });
}

export async function toggleDeviceDebug(deviceId) {
  return request(`/devices/${deviceId}/debug`, { method: 'POST' });
}

export async function getGlobalVolume() {
  return request('/playback/volume/global');
}

export async function setGlobalVolume(volume) {
  return request('/playback/volume/global', {
    method: 'POST',
    body: JSON.stringify({ volume }),
  });
}

export async function getVideoFormats() {
  return request('/video-formats');
}

/** Filename-only format detection (no file access on the server). */
export async function detectVideoFormat(filename, videoType = 'auto') {
  return request('/videos/detect', {
    method: 'POST',
    body: JSON.stringify({ filename, videoType }),
  });
}

/** Read the headers of a video file on the control-panel machine and auto-detect its format. */
export async function probeVideoFile(path, { filename = '', videoType = 'auto' } = {}) {
  const res = await fetch(`${API_BASE}/videos/probe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, filename, videoType }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error || `HTTP ${res.status}`);
  }
  return data;
}

export async function getVideoCompatibility(videoId) {
  return request(`/videos/${videoId}/compatibility`);
}

export async function setDeviceVolume(deviceId, volume) {
  return request(`/devices/${deviceId}/volume`, {
    method: 'POST',
    body: JSON.stringify({ volume }),
  });
}
