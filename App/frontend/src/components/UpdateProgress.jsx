import React from 'react';

export default function UpdateProgress({ progress, compact = false }) {
  if (!progress) return null;

  const { stage, progress: pct, message, file } = progress;
  const isFailed = stage === 'failed' || stage === 'push_video_failed' || stage === 'install_apk_failed';
  const isComplete = stage === 'completed' || stage === 'completed_with_errors';

  if (compact) {
    return (
      <div className={`update-progress compact ${isFailed ? 'failed' : ''}`}>
        <div className="progress-bar small">
          <div
            className={`progress-fill ${isFailed ? 'error' : ''}`}
            style={{ width: `${pct || 0}%` }}
          />
        </div>
        <span className="progress-label">{file || stage}</span>
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
    </div>
  );
}
