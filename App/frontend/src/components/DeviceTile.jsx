import React from 'react';
import { pingDevice } from '../api';
import { useI18n } from '../i18n';
import useDeviceStore from '../store/deviceStore';

function getBorderClass(device) {
  if (!device.online) {
    return 'tile-offline';
  }
  if (device.requirementsMet === false) {
    return 'tile-error';
  }
  const config = useDeviceStore.getState().config;
  const threshold = config?.batteryThreshold || 20;
  if (device.battery >= 0 && device.battery <= threshold) {
    return 'tile-warning';
  }
  return 'tile-ok';
}

function BatteryIcon({ level, charging }) {
  if (level <= 0) {
    return null;
  }
  let icon = '🔋';
  if (charging) {
    icon = '⚡';
  } else if (level <= 10) {
    icon = '🪫';
  }
  return <span className="battery-icon">{icon} {level}%</span>;
}

function ConnectionBadge({ device, t }) {
  if (!device.online) {
    return <span className="badge badge-offline">{t('Offline')}</span>;
  }
  if (device.playerConnected) {
    return <span className="badge badge-ok" title={t('Connected via WebSocket')}>WS</span>;
  }
  return <span className="badge badge-offline">{t('Player offline')}</span>;
}

export default function DeviceTile({ device, onClick }) {
  const { t } = useI18n();
  const config = useDeviceStore((state) => state.config);
  const threshold = config?.batteryThreshold || 20;
  const isLowBattery = device.battery > 0 && device.battery <= threshold;
  const isPlaying = device.playbackState === 'playing' || device.playbackState === 'paused';

  const handlePing = (event) => {
    event.stopPropagation();
    pingDevice(device.deviceId);
  };

  return (
    <div className={`device-tile ${getBorderClass(device)}`} onClick={onClick}>
      <div className="tile-header">
        <span className="tile-name" title={device.name || device.deviceId}>{device.name || device.deviceId}</span>
        <span className={`tile-status-dot ${device.online ? 'dot-online' : 'dot-offline'}`} />
      </div>

      <div className="tile-info">
        <span className="tile-ip">{device.ip}</span>
        <BatteryIcon level={device.battery} charging={device.batteryCharging} />
      </div>

      <div className="tile-status-row">
        <ConnectionBadge device={device} t={t} />
      </div>

      {device.online && (
        <div className="tile-requirements">
          {device.requirementsMet === null && <span className="req-checking">{t('Checking...')}</span>}
          {device.requirementsMet === true && <span className="req-ok">{t('Requirements met')}</span>}
          {device.requirementsMet === false && <span className="req-fail">{t('Requirements missing')}</span>}
        </div>
      )}

      {isPlaying && (
        <div className="tile-playback">
          <span className="playback-file" title={device.currentVideo}>
            {device.playbackState === 'playing' ? '▶' : '⏸'} {device.currentVideo || ''}
          </span>
          {device.playbackDuration > 0 && (
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${(device.playbackTime / device.playbackDuration) * 100}%`, transition: 'width 1s linear' }}
              />
            </div>
          )}
        </div>
      )}

      <div className="tile-actions">
        <button className="btn-small" disabled={!device.online || !device.playerConnected} onClick={handlePing}>
          {t('Ping')}
        </button>
      </div>

      {isLowBattery && <div className="low-battery-indicator" title={t('Low battery')} />}
    </div>
  );
}
