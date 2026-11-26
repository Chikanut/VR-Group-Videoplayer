import React from 'react';
import { pingDevice } from '../api';
import { contentText, updateText } from './DeviceDialog';
import { useI18n } from '../i18n';
import useDeviceStore from '../store/deviceStore';
import Icon from './Icons';

function batteryThreshold() {
  return useDeviceStore.getState().config?.batteryThreshold || 20;
}

export function isLowBattery(device) {
  return device.battery > 0 && device.battery <= batteryThreshold();
}

// Headset problems the instructor should look at; used by the tile and the "Problems" filter.
export function needsAttention(device) {
  if (!device.online) return false;
  return device.requirementsMet === false
    || device.launchBlockedSec > 0
    || isLowBattery(device)
    || device.content?.state === 'error'
    || (device.updateStatus || '').startsWith('failed');
}

// One status chip per headset: [i18n key, chip variant, tooltip key].
export function deviceStatus(device) {
  if (!device.online) return ['Offline', 'offline'];
  if (device.playbackState === 'playing') return ['Playing', 'ok'];
  if (device.playbackState === 'paused') return ['Paused', 'info'];
  if (device.playbackState === 'loading') return ['Loading', 'info'];
  if (device.agentConnected && !device.playerConnected) {
    // Player 1.9.0+: the headset agent answers with the player closed.
    return ['Player closed', 'warn', 'Headset is on, the player app is closed'];
  }
  if (!device.playerConnected) return ['Player offline', 'offline'];
  const via = device.agentConnected ? 'Connected via the headset agent'
    : device.wsConnected ? 'Connected via WebSocket' : 'Connected via HTTP';
  return ['Ready', 'info', via];
}

function Battery({ device, t }) {
  if (device.battery <= 0) return null;
  const low = isLowBattery(device);
  return (
    <span className={`battery${low ? ' low' : ''}`} title={low ? t('Low battery') : t('Battery')}>
      <span className="battery-shape"><span style={{ width: `${device.battery}%` }} /></span>
      {device.batteryCharging && <span aria-label={t('Charging')}>⚡</span>}
      {device.battery}%
    </span>
  );
}

export default function DeviceTile({ device, onClick }) {
  const { t } = useI18n();
  const selected = useDeviceStore((state) => !!state.selectedIds[device.deviceId]);
  const toggleSelected = useDeviceStore((state) => state.toggleSelected);
  const isPlaying = device.playbackState === 'playing' || device.playbackState === 'paused';
  const [statusKey, statusKind, statusTitle] = deviceStatus(device);

  const handlePing = (event) => {
    event.stopPropagation();
    pingDevice(device.deviceId);
  };

  const notes = [];
  if (device.online) {
    if (device.launchBlockedSec > 0) {
      notes.push(['error', t('Player will not open: {minutes} min', { minutes: Math.max(1, Math.round(device.launchBlockedSec / 60)) }), t('Launch blocked hint')]);
    }
    if (device.content?.state && device.content.state !== 'idle') {
      notes.push([device.content.state === 'error' ? 'error' : 'info', `${t('Content')}: ${contentText(device.content, t)}`]);
    }
    if (device.updateStatus && device.updateStatus !== 'up to date') {
      notes.push([device.updateStatus.startsWith('failed') ? 'error' : 'info', `${t('Player update')}: ${updateText(device.updateStatus, t)}`]);
    }
    if (isLowBattery(device) && !device.batteryCharging) {
      notes.push(['warn', t('Low battery')]);
    }
  }

  return (
    <div
      className={`device-tile${device.online ? '' : ' tile-offline'}${device.online && device.requirementsMet === false ? ' tile-error' : ''}${selected ? ' tile-selected' : ''}`}
      onClick={onClick}
    >
      <div className="tile-header">
        <input
          type="checkbox"
          className="tile-select"
          checked={selected}
          title={t('Select for commands')}
          aria-label={t('Select for commands')}
          onClick={(event) => event.stopPropagation()}
          onChange={() => toggleSelected(device.deviceId)}
        />
        <span className="tile-name" title={`${device.name || device.deviceId} (${device.deviceId})`}>
          {device.name || device.deviceId}
          {device.nameSource === 'pending' && (
            <span className="tile-name-pending" title={t('Not saved on the headset yet')}> ⏳</span>
          )}
          {device.nameSource === 'server' && device.playerConnected && (
            <span className="tile-name-pending" title={t('Name stored only on the server (older player build)')}> *</span>
          )}
        </span>
        <span className={`chip chip-${statusKind}`} title={statusTitle ? t(statusTitle) : undefined}>
          <span className="chip-dot" />{t(statusKey)}
        </span>
      </div>

      <div className="tile-info">
        <span className="tile-ip">
          {device.ip}
          {(device.playerVersion || device.agentVersion) && (
            <span className="tile-version"> · v{device.playerVersion || device.agentVersion}</span>
          )}
        </span>
        <Battery device={device} t={t} />
      </div>

      {isPlaying && (
        <div className="tile-playback">
          <div className="tile-playback-head">
            <span className="playback-file" title={device.currentVideo}>{device.currentVideo || ''}</span>
            {device.playbackDuration > 0 && (
              <span className="mono">{formatTime(device.playbackTime)} / {formatTime(device.playbackDuration)}</span>
            )}
          </div>
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

      {notes.map(([kind, text, title]) => (
        <div key={text} className={`tile-note tile-note-${kind}`} title={title || text}>{text}</div>
      ))}

      <div className="tile-footer">
        <span className="tile-requirements" style={{ fontSize: 12 }}>
          {device.online && device.requirementsMet === null && <span className="req-checking">{t('Checking...')}</span>}
          {device.online && device.requirementsMet === true && <span className="req-ok">{t('Requirements met')}</span>}
          {device.online && device.requirementsMet === false && <span className="req-fail">{t('Requirements missing')}</span>}
        </span>
        <button
          className="btn-small"
          disabled={!device.online || !device.playerConnected}
          onClick={handlePing}
          title={t('Ping')}
        >
          <Icon name="sound" size={14} />
          {t('Ping')}
        </button>
      </div>
    </div>
  );
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(total / 60)}:${(total % 60).toString().padStart(2, '0')}`;
}
