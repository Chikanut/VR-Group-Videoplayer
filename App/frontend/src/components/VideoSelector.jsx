import React from 'react';
import useDeviceStore from '../store/deviceStore';
import { playbackOpen } from '../api';

export default function VideoSelector({ targetDeviceIds, onClose }) {
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const ignoreReq = config?.ignoreRequirements || false;
  const adbAvailable = config?.adbAvailable !== false;
  const adbEnabled = config?.adbEnabled !== false && adbAvailable;
  const videos = config?.requirementVideos || [];

  // When ignoreRequirements is on, include ADB-connected devices as valid targets
  const isCommandTarget = (d) =>
    d.online && (d.playerConnected || (ignoreReq && adbEnabled && d.adbConnected));

  const onlineCommandDevices = devices.filter(isCommandTarget);

  if (videos.length === 0) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal video-selector" onClick={(e) => e.stopPropagation()}>
          <div className="dialog-header">
            <h2>Select Video</h2>
            <button className="btn-close" onClick={onClose}>x</button>
          </div>
          <div className="empty-state">
            <p>No videos configured. Go to Settings to add videos.</p>
          </div>
        </div>
      </div>
    );
  }

  const targetDevices = targetDeviceIds.length > 0
    ? devices.filter((d) => targetDeviceIds.includes(d.deviceId) && isCommandTarget(d))
    : onlineCommandDevices;

  const getVideoAvailability = (video) => {
    let available = 0;
    for (const d of targetDevices) {
      // When ignoring requirements, count all target devices as available
      if (ignoreReq) {
        available++;
        continue;
      }
      if (!d.requirementsDetail) {
        available++;
        continue;
      }
      const req = d.requirementsDetail.find(
        (r) => r.type === 'video' && (r.id === video.id || r.name === video.name)
      );
      if (!req || req.present) available++;
    }
    return { available, total: targetDevices.length };
  };

  const handlePlay = async (video) => {
    const result = await playbackOpen(video.id, targetDeviceIds);
    if (result.missing && result.missing.length > 0) {
      const names = result.missing.map((m) => m.name || m.deviceId).join(', ');
      alert(
        `Video missing on ${result.missing.length} device(s): ${names}.\n` +
        `Playing on ${(result.success || []).length} available device(s).`
      );
    }
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal video-selector" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2>Select Video</h2>
          <button className="btn-close" onClick={onClose}>x</button>
        </div>
        {ignoreReq && adbEnabled && targetDevices.some((d) => !d.playerConnected) && (
          <div className="dialog-warning" style={{ margin: '0 1rem' }}>
            Some devices have no player HTTP connection. Commands will be sent via ADB.
          </div>
        )}
        <div className="video-list">
          {videos.map((video) => {
            const { available, total } = getVideoAvailability(video);
            // When ignoring requirements, allow play even if availability is uncertain
            const canPlay = ignoreReq ? total > 0 : available > 0;
            return (
              <div key={video.id} className="video-item">
                <div className="video-info">
                  <span className="video-name">{video.name}</span>
                  <span className="video-meta">
                    {video.videoType.toUpperCase()} {video.loop ? '| Loop' : ''}
                  </span>
                  <span className={`video-availability ${available < total ? 'partial' : ''}`}>
                    {ignoreReq ? `${total} device(s) targeted` : `Available on ${available}/${total} device(s)`}
                  </span>
                  {!ignoreReq && available < total && (
                    <span className="video-missing-note">
                      {total - available} device(s) missing this video
                    </span>
                  )}
                </div>
                <button
                  className="btn btn-success"
                  disabled={!canPlay}
                  onClick={() => handlePlay(video)}
                >
                  {canPlay
                    ? (ignoreReq ? 'Force Play' : (available < total ? 'Play on available' : 'Play'))
                    : 'Not available'}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
