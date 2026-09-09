/**
 * Video format helpers shared by the settings editor, video selector and device views.
 * Mirrors App/server/video_format.py: canonical formatId = projection + stereo.
 *
 *   projection: 'flat' | '180' | '360'
 *   stereo:     'mono' | 'sbs' | 'tb'
 *   formatId:   '2d' | '360' | '360_sbs' | '360_tb' | '180' | '180_sbs' | '180_tb' | 'auto'
 */

export const PROJECTIONS = ['flat', '180', '360'];
export const STEREO_LAYOUTS = ['mono', 'sbs', 'tb'];
export const AUTO = 'auto';
export const DEFAULT_FORMAT = '360';

const CANONICAL = {
  '2d': ['flat', 'mono'],
  '360': ['360', 'mono'],
  '360_sbs': ['360', 'sbs'],
  '360_tb': ['360', 'tb'],
  '180': ['180', 'mono'],
  '180_sbs': ['180', 'sbs'],
  '180_tb': ['180', 'tb'],
};

const PROJECTION_TOKENS = {
  '2d': 'flat', flat: 'flat',
  '180': '180', vr180: '180',
  '360': '360', sphere: '360',
};

const STEREO_TOKENS = {
  mono: 'mono',
  sbs: 'sbs', lr: 'sbs', '3dh': 'sbs',
  tb: 'tb', ou: 'tb', '3dv': 'tb',
};

export const FORMAT_IDS = Object.keys(CANONICAL);

export function joinFormat(projection, stereo = 'mono') {
  if (projection === 'flat') return '2d';
  const proj = PROJECTIONS.includes(projection) ? projection : '360';
  const st = STEREO_LAYOUTS.includes(stereo) ? stereo : 'mono';
  return st === 'mono' ? proj : `${proj}_${st}`;
}

export function normalizeFormatId(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return null;
  if (text === AUTO) return AUTO;
  if (CANONICAL[text]) return text;
  const tokens = text.split(/[\s_\-.]+/).filter(Boolean);
  let projection = null;
  let stereo = null;
  for (const token of tokens) {
    if (projection === null && PROJECTION_TOKENS[token]) projection = PROJECTION_TOKENS[token];
    else if (stereo === null && STEREO_TOKENS[token]) stereo = STEREO_TOKENS[token];
  }
  return projection ? joinFormat(projection, stereo || 'mono') : null;
}

export function splitFormat(formatId) {
  const normalized = normalizeFormatId(formatId);
  const key = normalized && normalized !== AUTO ? normalized : DEFAULT_FORMAT;
  const [projection, stereo] = CANONICAL[key];
  return { projection, stereo };
}

export function isStereoFormat(formatId) {
  return splitFormat(formatId).stereo !== 'mono';
}

/** Human label, e.g. "180° 3D SBS". `t` is the i18n function (optional). */
export function formatLabel(formatId, t = (s) => s) {
  const normalized = normalizeFormatId(formatId);
  if (!normalized) return t('Unknown');
  if (normalized === AUTO) return t('Auto');
  const { projection, stereo } = splitFormat(normalized);
  if (projection === 'flat') return t('2D');
  const geometry = projection === '180' ? '180°' : '360°';
  if (stereo === 'sbs') return `${geometry} 3D SBS`;
  if (stereo === 'tb') return `${geometry} 3D TB`;
  return geometry;
}

/** Label for what a device reports (projection/stereo from /status; falls back to legacy mode). */
export function deviceFormatLabel(device, t = (s) => s) {
  if (!device) return '';
  if (device.currentProjection) {
    if (device.currentProjection === 'none') return '';
    return formatLabel(joinFormat(device.currentProjection, device.currentStereo || 'mono'), t);
  }
  return formatLabel(device.currentMode || DEFAULT_FORMAT, t);
}

/**
 * Filename convention: <name>_<projection>_<stereo>.<ext>. Only the end of the stem counts.
 * Returns { projection, stereo } (either may be null) or null when nothing was found.
 */
export function detectFromFilename(filename) {
  if (!filename) return null;
  const base = String(filename).split(/[\\/]/).pop();
  const stem = base.replace(/\.[^.]+$/, '');
  const tokens = stem.toLowerCase().split(/[\s_\-.]+/).filter(Boolean);
  if (tokens.length === 0) return null;

  let projection = null;
  let stereo = null;
  const last = tokens[tokens.length - 1];
  if (STEREO_TOKENS[last]) {
    stereo = STEREO_TOKENS[last];
    const prev = tokens.length >= 2 ? tokens[tokens.length - 2] : null;
    if (prev && PROJECTION_TOKENS[prev]) projection = PROJECTION_TOKENS[prev];
  } else if (PROJECTION_TOKENS[last]) {
    projection = PROJECTION_TOKENS[last];
  }

  if (!projection && !stereo) return null;
  return { projection, stereo };
}

export function formatIdFromFilename(filename) {
  const hint = detectFromFilename(filename);
  if (!hint || !hint.projection) return null;
  return joinFormat(hint.projection, hint.stereo || 'mono');
}

/** Effective format for a configured video (manual > cached detection > filename > default). */
export function resolveVideoFormat(video) {
  if (!video) return DEFAULT_FORMAT;
  const manual = normalizeFormatId(video.videoType);
  if (manual && manual !== AUTO) return manual;
  const detected = normalizeFormatId(video.detectedType);
  if (detected && detected !== AUTO) return detected;
  return formatIdFromFilename(video.filename) || DEFAULT_FORMAT;
}

export function detectionSourceLabel(source, t = (s) => s) {
  switch (source) {
    case 'manual': return t('manual');
    case 'filename': return t('from filename');
    case 'aspect+metadata': return t('from aspect ratio and metadata');
    case 'aspect': return t('from aspect ratio');
    case 'metadata': return t('from file metadata');
    case 'default': return t('default (not determined)');
    default: return source || '';
  }
}

export function formatBytes(bytes) {
  const value = Number(bytes) || 0;
  if (value <= 0) return '';
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)} GB`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)} MB`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(0)} KB`;
  return `${value} B`;
}

export function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  if (total <= 0) return '';
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}

/**
 * Client-side mirror of App/server/format_compat.py: warnings for playing `video` on `device`.
 * Uses the device's decoderCaps / stereoCapable from /status and the video's cached probe.
 */
export function deviceCompatWarnings(video, device, t = (s) => s) {
  const warnings = [];
  if (!video || !device) return warnings;

  const formatId = resolveVideoFormat(video);
  const { projection, stereo } = splitFormat(formatId);

  if (device.stereoCapable === false) {
    if (stereo !== 'mono') {
      warnings.push(t('Player predates stereo 3D: 3D videos will play as mono'));
    } else if (projection === '180') {
      warnings.push(t('Player predates 180° support: video will be stretched over a full sphere'));
    }
  }

  const caps = device.decoderCaps && typeof device.decoderCaps === 'object' ? device.decoderCaps : null;
  const probe = video.probe && typeof video.probe === 'object' ? video.probe : null;
  if (!caps || !probe) return warnings;

  const width = Number(probe.width) || 0;
  const height = Number(probe.height) || 0;
  const codec = String(probe.codec || '').toLowerCase();
  const prefix = { hevc: 'hevc', h264: 'avc', av1: 'av1', vp9: 'vp9' }[codec] || codec;
  const maxWidth = Number(caps[`${prefix}MaxWidth`]) || 0;
  const maxHeight = Number(caps[`${prefix}MaxHeight`]) || 0;
  if ((width && maxWidth && width > maxWidth) || (height && maxHeight && height > maxHeight)) {
    warnings.push(t('Video {w}x{h} exceeds decoder limit {mw}x{mh}', { w: width, h: height, mw: maxWidth, mh: maxHeight }));
  }

  if (codec === 'hevc' && Number(probe.bitDepth) > 8 && caps.hevcMain10 === false) {
    warnings.push(t('10-bit HEVC (Main10) not supported by this headset'));
  }

  const fps = Number(probe.fps) || 0;
  const maxFps8k = Number(caps.hevcMaxFrameRateAt8K) || 0;
  if (codec === 'hevc' && width >= 7680 && fps && maxFps8k && fps > maxFps8k + 0.5) {
    warnings.push(t('{fps} fps at 8K exceeds decoder limit {max} fps', { fps: Math.round(fps), max: maxFps8k }));
  }

  const free = Number(caps.storageFreeBytes) || 0;
  const size = Number(probe.sizeBytes) || 0;
  if (free > 0 && size > 0 && size > free) {
    warnings.push(t('File {size} exceeds free storage {free}', { size: formatBytes(size), free: formatBytes(free) }));
  }

  return warnings;
}
