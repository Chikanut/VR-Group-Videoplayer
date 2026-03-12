import React from 'react';
import useDeviceStore from '../store/deviceStore';
import { playbackOpen } from '../api';
import { useI18n } from '../i18n';

export default function VideoSelector({ targetDeviceIds, onClose }) {
  const { t } = useI18n();
  const config = useDeviceStore((state) => state.config);
  const devices = useDeviceStore((state) => state.getDeviceList());
  const videos = config?.requirementVideos || [];

  const targetDevices = targetDeviceIds.length > 0
    ? devices.filter((device) => targetDeviceIds.includes(device.deviceId) && device.online && device.playerConnected)
    : devices.filter((device) => device.online && device.playerConnected);

  if (videos.length === 0) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal video-selector" onClick={(event) => event.stopPropagation()}>
          <div className="dialog-header">
            <h2>{t('Select Video')}</h2>
            <button className="btn-close" onClick={onClose}>x</button>
          </div>
          <div className="empty-state">
            <p>{t('No videos configured. Go to Settings to add videos.')}</p>
          </div>
        </div>
      </div>
    );
  }

  const getVideoAvailability = (video) => {
    let available = 0;
    for (const device of targetDevices) {
      if (!device.requirementsDetail || device.requirementsDetail.length === 0) {
        available += 1;
        continue;
      }

      const requirement = device.requirementsDetail.find(
        (item) => item.type === 'video' && (item.id === video.id || item.filename === video.filename),
      );
      if (!requirement || requirement.present) {
        available += 1;
      }
    }
    return { available, total: targetDevices.length };
  };

  const handlePlay = async (video) => {
    const result = await playbackOpen(video.id, targetDeviceIds);
    if (result.missing && result.missing.length > 0) {
      const names = result.missing.map((item) => item.name || item.deviceId).join(', ');
      alert(
        `${t('Video missing on {count} device(s): {names}.', { count: result.missing.length, names })}\n` +
        t('Playing on {count} available device(s).', { count: (result.success || []).length }),
      );
    }
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal video-selector" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          <h2>{t('Select Video')}</h2>
          <button className="btn-close" onClick={onClose}>x</button>
        </div>

        <div className="video-list">
          {videos.map((video) => {
            const { available, total } = getVideoAvailability(video);
            const canPlay = total > 0 && available > 0;

            return (
              <div key={video.id} className="video-item">
                <div className="video-info">
                  <span className="video-name">{video.name}</span>
                  <span className="video-meta">
                    {video.videoType.toUpperCase()} {video.loop ? `| ${t('Loop')}` : ''}
                  </span>
                  <span className={`video-availability ${available < total ? 'partial' : ''}`}>
                    {t('Available on {available}/{total} device(s)', { available, total })}
                  </span>
                  {available < total && (
                    <span className="video-missing-note">
                      {t('{count} device(s) missing this video', { count: total - available })}
                    </span>
                  )}
                </div>
                <button className="btn btn-success" disabled={!canPlay} onClick={() => handlePlay(video)}>
                  {canPlay
                    ? (available < total ? t('Play on available') : t('Play'))
                    : t('Not available')}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
