import React from 'react';
import { useI18n } from '../i18n';
import { formatBytes } from '../videoFormats';

function formatEta(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (total <= 0) return '';
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`;
}

/**
 * Progress payload fields (all optional besides stage/progress):
 *   stage, progress (0-100), message, file,
 *   bytesDone, bytesTotal, bytesPerSec, etaSec  — for multi-gigabyte pushes
 */
export default function UpdateProgress({ progress, compact = false }) {
  const i18n = useI18n();
  const t = i18n?.t || ((text) => text);
  if (!progress) return null;

  const { stage, progress: pct, message, file, bytesDone, bytesTotal, bytesPerSec, etaSec } = progress;
  const isFailed = stage === 'failed' || stage === 'push_video_failed' || stage === 'install_apk_failed';
  const isComplete = stage === 'completed' || stage === 'completed_with_errors';

  const transferParts = [];
  if (bytesTotal > 0) {
    transferParts.push(`${formatBytes(bytesDone || 0)} / ${formatBytes(bytesTotal)}`);
  }
  if (bytesPerSec > 0) {
    transferParts.push(`${(bytesPerSec / 1e6).toFixed(1)} MB/s`);
  }
  if (etaSec > 0 && !isComplete && !isFailed) {
    transferParts.push(`${t('ETA')} ${formatEta(etaSec)}`);
  }
  const transferText = transferParts.join(' · ');

  if (compact) {
    return (
      <div className={`update-progress compact ${isFailed ? 'failed' : ''}`}>
        <div className="progress-bar small">
          <div
            className={`progress-fill ${isFailed ? 'error' : ''}`}
            style={{ width: `${pct || 0}%` }}
          />
        </div>
        <span className="progress-label">{file || stage}{transferText ? ` · ${transferText}` : ''}</span>
      </div>
    );
  }

  return (
    <div className={`update-progress ${isFailed ? 'failed' : ''} ${isComplete ? 'complete' : ''}`}>
      <div className="progress-bar">
        <div
          className={`progress-fill ${isFailed ? 'error' : ''} ${isComplete ? 'success' : ''}`}
          style={{ width: `${pct || 0}%` }}
        />
        <span className="progress-text">{pct || 0}%</span>
      </div>
      <p className="progress-message">{message}</p>
      {transferText && <p className="progress-message progress-transfer">{transferText}</p>}
    </div>
  );
}
