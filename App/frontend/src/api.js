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

export async function browseFiles(path = '', filter = '') {
  const params = new URLSearchParams();
  if (path) params.set('path', path);
  if (filter) params.set('filter', filter);
  return request(`/browse?${params.toString()}`);
}

export async function getUsbDevices() {
  return request('/usb-devices');
}

export async function updateUsbDevice(serial, options = {}) {
  return request(`/usb-devices/${serial}/update`, {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export async function launchPlayer(deviceIds = []) {
  return request('/devices/launch-player', {
    method: 'POST',
    body: JSON.stringify({ deviceIds }),
  });
}

export async function launchPlayerSingle(deviceId) {
  return request(`/devices/${deviceId}/launch-player`, { method: 'POST' });
}

export async function toggleDeviceDebug(deviceId) {
  return request(`/devices/${deviceId}/debug`, { method: 'POST' });
}

export async function restartApp(deviceId) {
  return request(`/devices/${deviceId}/restart-app`, { method: 'POST' });
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

export async function setDeviceVolume(deviceId, volume) {
  return request(`/devices/${deviceId}/volume`, {
    method: 'POST',
    body: JSON.stringify({ volume }),
  });
}
