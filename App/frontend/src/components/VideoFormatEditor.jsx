import React, { useState } from 'react';
import { probeVideoFile } from '../api';
import { useI18n } from '../i18n';
import useDeviceStore from '../store/deviceStore';
import {
  AUTO,
  detectionSourceLabel,
  formatBytes,
  formatDuration,
  formatIdFromFilename,
  formatLabel,
  joinFormat,
  normalizeFormatId,
  resolveVideoFormat,
  splitFormat,
} from '../videoFormats';

/**
 * Projection / stereo editor for one requirement video, with auto-detection,
 * file probing (technical info + warnings) and the stereo extras (swap eyes, forward yaw).
 *
 * Props:
 *   video   - the requirement video object
 *   onPatch - (patch) => void, merges fields into the video
 */
export default function VideoFormatEditor({ video, onPatch }) {
  const { t } = useI18n();
  const devices = useDeviceStore((state) => state.getDeviceList());
  const [probeOpen, setProbeOpen] = useState(false);
  const [probePath, setProbePath] = useState('');
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState('');
  const [showInfo, setShowInfo] = useState(false);

  const isAuto = (video.videoType || '') === AUTO;
  const effectiveFormat = resolveVideoFormat(video);
  const { projection, stereo } = splitFormat(isAuto ? effectiveFormat : (video.videoType || '360'));
  const probe = video.probe && typeof video.probe === 'object' ? video.probe : null;
  const isStereo = stereo !== 'mono';
  const isSpherical = projection !== 'flat';

  // What auto-detection says (or would say, for a manually set format): probe result first,
  // then the cached detection on the video, then the filename suffix.
  const probeAuto = probe && probe.autoDetectedType ? normalizeFormatId(probe.autoDetectedType) : null;
  const detectedType = probeAuto
    || normalizeFormatId(video.detectedType && video.detectionSource !== 'manual' ? video.detectedType : null)
    || formatIdFromFilename(video.filename)
    || null;
  const detectionSource = probeAuto
    ? probe.autoDetectionSource
    : (video.detectedType && video.detectionSource !== 'manual' ? video.detectionSource : (formatIdFromFilename(video.filename) ? 'filename' : ''));
  const oldPlayers = devices.filter((device) => device.online && device.stereoCapable === false);

  const setManualFormat = (nextProjection, nextStereo) => {
    onPatch({ videoType: joinFormat(nextProjection, nextStereo) });
  };

  const toggleAuto = (checked) => {
    if (checked) {
      const fromName = formatIdFromFilename(video.filename);
      onPatch({
        videoType: AUTO,
        detectedType: probeAuto || fromName || '',
        detectionSource: probeAuto ? probe.autoDetectionSource : (fromName ? 'filename' : ''),
      });
    } else {
      onPatch({ videoType: effectiveFormat });
    }
  };

  const runProbe = async () => {
    const path = probePath.trim();
    if (!path) return;
    setProbing(true);
    setProbeError('');
    try {
      const result = await probeVideoFile(path, {
        filename: video.filename || '',
        videoType: isAuto ? AUTO : (video.videoType || AUTO),
      });
      const { path: _path, format: _format, ...probeInfo } = result;
      const patch = { probe: probeInfo };
      if (isAuto) {
        patch.detectedType = result.autoDetectedType || result.detectedType;
        patch.detectionSource = result.autoDetectionSource || result.detectionSource;
      }
      if (!video.filename) {
        patch.filename = path.split(/[\\/]/).pop();
      }
      onPatch(patch);
      setShowInfo(true);
      setProbeOpen(false);
    } catch (error) {
      setProbeError(`${t('Probe failed')}: ${error.message}`);
    }
    setProbing(false);
  };

  const clearProbe = () => {
    onPatch({ probe: null, detectedType: isAuto ? (formatIdFromFilename(video.filename) || '') : '', detectionSource: isAuto && formatIdFromFilename(video.filename) ? 'filename' : '' });
    setShowInfo(false);
  };

  return (
    <div className="video-format-editor">
      <div className="settings-grid">
        <div className="form-group form-group-small">
          <label>{t('Projection')}</label>
          <select
            value={projection}
            disabled={isAuto}
            onChange={(event) => setManualFormat(event.target.value, stereo)}
          >
            <option value="flat">{t('Flat 2D')}</option>
            <option value="180">180°</option>
            <option value="360">360°</option>
          </select>
        </div>

        <div className="form-group form-group-small">
          <label>{t('Stereo')}</label>
          <select
            value={stereo}
            disabled={isAuto || projection === 'flat'}
            onChange={(event) => setManualFormat(projection, event.target.value)}
          >
            <option value="mono">{t('Mono')}</option>
            <option value="sbs">{t('Side-by-Side (LR)')}</option>
            <option value="tb">{t('Top-Bottom (TB)')}</option>
          </select>
        </div>

        <div className="form-group form-group-small">
          <label>{t('Format')}</label>
          <label className="checkbox-label">
            <input type="checkbox" checked={isAuto} onChange={(event) => toggleAuto(event.target.checked)} />
            <span>{t('Detect automatically')}</span>
          </label>
        </div>
      </div>

      <div className="video-format-status">
        <span className={`badge ${isStereo ? 'badge-info' : 'badge-ok'}`} title={effectiveFormat}>
          {formatLabel(effectiveFormat, t)}
        </span>
        {isAuto && detectedType && (
          <span className="form-hint">
            {t('Detected: {format} ({source})', {
              format: formatLabel(detectedType, t),
              source: detectionSourceLabel(detectionSource || 'filename', t),
            })}
          </span>
        )}
        {isAuto && !detectedType && (
          <span className="form-hint form-hint-warn">
            {t('Name the file <name>_180_LR.mp4 / <name>_360_TB.mp4 so the format is detected automatically.')}
          </span>
        )}
        {!isAuto && detectedType && detectedType !== effectiveFormat && (
          <span className="form-hint form-hint-warn">
            {t('Detected: {format} ({source})', {
              format: formatLabel(detectedType, t),
              source: detectionSourceLabel(detectionSource || 'filename', t),
            })}
            {' '}
            <button type="button" className="btn-link" onClick={() => onPatch({ videoType: detectedType })}>
              {t('Use detected format')}
            </button>
          </span>
        )}
        {!probeOpen && (
          <button type="button" className="btn btn-small" onClick={() => setProbeOpen(true)}>
            {t('Probe file...')}
          </button>
        )}
        {probe && (
          <button type="button" className="btn btn-small btn-dim" onClick={() => setShowInfo((value) => !value)}>
            {t('File info')}
          </button>
        )}
      </div>

      {probeOpen && (
        <div className="video-probe-form">
          <input
            type="text"
            value={probePath}
            placeholder={t('Path to the video file on this computer')}
            onChange={(event) => setProbePath(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') runProbe();
              if (event.key === 'Escape') setProbeOpen(false);
            }}
            autoFocus
          />
          <button type="button" className="btn btn-small btn-primary" disabled={probing || !probePath.trim()} onClick={runProbe}>
            {probing ? t('Probing...') : t('Probe')}
          </button>
          <button type="button" className="btn btn-small" onClick={() => setProbeOpen(false)}>
            {t('Cancel')}
          </button>
          {probeError && <span className="form-hint form-hint-error">{probeError}</span>}
        </div>
      )}

      {probe && showInfo && (
        <div className="video-probe-info">
          <table className="info-table">
            <tbody>
              <tr><td>{t('Resolution')}</td><td>{probe.width}x{probe.height} {probe.fps ? `@ ${probe.fps} fps` : ''}</td></tr>
              <tr>
                <td>{t('Codec')}</td>
                <td>
                  {(probe.codec || '').toUpperCase()} {probe.profile} {probe.level ? `L${probe.level}` : ''} {probe.tier === 'high' ? '(high tier)' : ''}
                </td>
              </tr>
              {probe.bitDepth > 0 && <tr><td>{t('Bit depth')}</td><td>{probe.bitDepth}-bit {probe.chromaFormat}</td></tr>}
              {probe.bitrateMbps > 0 && <tr><td>{t('Bitrate')}</td><td>{probe.bitrateMbps} Mbit/s</td></tr>}
              {probe.durationSec > 0 && <tr><td>{t('Duration')}</td><td>{formatDuration(probe.durationSec)}</td></tr>}
              {probe.sizeBytes > 0 && <tr><td>{t('Size')}</td><td>{formatBytes(probe.sizeBytes)}</td></tr>}
              {probe.audioCodec && (
                <tr><td>{t('Audio')}</td><td>{probe.audioCodec.toUpperCase()} {probe.audioChannels}ch {probe.audioSampleRate ? `${probe.audioSampleRate} Hz` : ''}</td></tr>
              )}
              {(probe.metadataProjection || probe.metadataStereo) && (
                <tr><td>{t('Metadata')}</td><td>{probe.metadataProjection} {probe.metadataStereo} {probe.metadataSource ? `(${probe.metadataSource})` : ''}</td></tr>
              )}
              {probe.autoDetectedType && (
                <tr><td>{t('Format')}</td><td>{formatLabel(probe.autoDetectedType, t)} ({detectionSourceLabel(probe.autoDetectionSource, t)})</td></tr>
              )}
            </tbody>
          </table>
          {Array.isArray(probe.warnings) && probe.warnings.length > 0 && (
            <ul className="video-probe-warnings">
              {probe.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
            </ul>
          )}
          <button type="button" className="btn btn-small btn-dim" onClick={clearProbe}>{t('Clear file info')}</button>
        </div>
      )}

      {isSpherical && (
        <details className="form-group video-advanced-details">
          <summary>{t('Stereo 3D options')}</summary>
          <div className="settings-grid" style={{ marginTop: 12 }}>
            <div className="form-group form-group-small">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={Boolean(video.swapEyes)}
                  disabled={!isStereo}
                  onChange={(event) => onPatch({ swapEyes: event.target.checked })}
                />
                <span>{t('Swap eyes')}</span>
              </label>
              <span className="form-hint">{t('Use if the 3D looks "inside out" (left/right eyes exported reversed).')}</span>
            </div>
            <div className="form-group form-group-small">
              <label>{t('Forward yaw (°)')}</label>
              <input
                type="number"
                step="1"
                min="-360"
                max="360"
                value={Number(video.forwardYaw) || 0}
                onChange={(event) => onPatch({ forwardYaw: parseFloat(event.target.value) || 0 })}
              />
              <span className="form-hint">{t('Which part of the video faces the viewer after recenter (0 = frame centre).')}</span>
            </div>
          </div>
        </details>
      )}

      {(isStereo || projection === '180') && oldPlayers.length > 0 && (
        <div className="form-hint form-hint-warn">
          {t('{count} connected headset(s) run a player without 3D/180° support: {names}', {
            count: oldPlayers.length,
            names: oldPlayers.map((device) => device.name || device.deviceId).join(', '),
          })}
        </div>
      )}
    </div>
  );
}
