import React from 'react';
import useDeviceStore from '../store/deviceStore';
import { playbackOpen } from '../api';
import { useI18n } from '../i18n';
import { deviceCompatWarnings, formatLabel, isStereoFormat, resolveVideoFormat } from '../videoFormats';

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

  const getCompatWarnings = (video) => {
    const items = [];
    for (const device of targetDevices) {
      const warnings = deviceCompatWarnings(video, device, t);
      if (warnings.length > 0) {
        items.push({ device, warnings });
      }
    }
    return items;
  };

  const handlePlay = async (video) => {
    const result = await playbackOpen(video.id, targetDeviceIds);
    const messages = [];
    if (result.missing && result.missing.length > 0) {
      const names = result.missing.map((item) => item.name || item.deviceId).join(', ');
      messages.push(t('Video missing on {count} device(s): {names}.', { count: result.missing.length, names }));
      messages.push(t('Playing on {count} available device(s).', { count: (result.success || []).length }));
    }
    if (Array.isArray(result.warnings) && result.warnings.length > 0) {
      messages.push(t('Compatibility warnings:'));
      for (const item of result.warnings) {
        messages.push(`${item.name || item.deviceId}: ${(item.warnings || []).join('; ')}`);
      }
    }
    if (messages.length > 0) {
      alert(messages.join('\n'));
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
            const formatId = resolveVideoFormat(video);
            const compat = getCompatWarnings(video);

            return (
              <div key={video.id} className="video-item">
                <div className="video-info">
                  <span className="video-name">{video.name}</span>
                  <span className="video-meta">
                    <span className={`badge ${isStereoFormat(formatId) ? 'badge-info' : 'badge-ok'}`} title={formatId}>
                      {formatLabel(formatId, t)}
                    </span>
                    {video.videoType === 'auto' && <span className="video-meta-auto"> ({t('Auto')})</span>}
                    {video.loop ? ` | ${t('Loop')}` : ''}
                    {video.probe?.width ? ` | ${video.probe.width}x${video.probe.height}` : ''}
                  </span>
                  {compat.length > 0 && (
                    <span
                      className="video-missing-note"
                      title={compat.map((item) => `${item.device.name || item.device.deviceId}: ${item.warnings.join('; ')}`).join('\n')}
                    >
                      ⚠ {t('{count} device(s) may not play this format correctly', { count: compat.length })}
                    </span>
                  )}
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
