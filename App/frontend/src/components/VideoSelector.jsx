import React from 'react';
import useDeviceStore from '../store/deviceStore';
import { playbackOpen } from '../api';

export default function VideoSelector({ targetDeviceIds, onClose }) {
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlinePlayerDevices = devices.filter((d) => d.online && d.playerConnected);
  const videos = config?.requirementVideos || [];

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
    ? devices.filter((d) => targetDeviceIds.includes(d.deviceId) && d.online && d.playerConnected)
    : onlinePlayerDevices;

  const getVideoAvailability = (video) => {
    let available = 0;
    for (const d of targetDevices) {
      if (!d.requirementsDetail) {
        available++;
        continue;
      }
      const req = d.requirementsDetail.find(
        (r) => r.type === 'video' && r.devicePath === video.devicePath
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
        <div className="video-list">
          {videos.map((video) => {
            const { available, total } = getVideoAvailability(video);
            const canPlay = available > 0;
            return (
              <div key={video.id} className="video-item">
                <div className="video-info">
                  <span className="video-name">{video.name}</span>
                  <span className="video-meta">
                    {video.videoType.toUpperCase()} {video.loop ? '| Loop' : ''}
                  </span>
                  <span className={`video-availability ${available < total ? 'partial' : ''}`}>
                    Available on {available}/{total} device(s)
                  </span>
                  {available < total && (
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
                  {canPlay ? (available < total ? 'Play on available' : 'Play') : 'Not available'}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
