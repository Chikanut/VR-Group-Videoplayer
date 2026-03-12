import React, { useEffect, useRef, useState } from 'react';
import useDeviceStore from '../store/deviceStore';
import {
  getRequirements,
  pingDevice,
  playbackCommand,
  setDeviceName,
  setDeviceVolume,
  toggleDeviceDebug,
} from '../api';
import { useI18n } from '../i18n';

export default function DeviceDialog({ deviceId, onClose, onPlayVideo }) {
  const { t } = useI18n();
  const device = useDeviceStore((state) => state.devices[deviceId]);
  const [editName, setEditName] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [requirements, setRequirements] = useState(null);
  const [loadingReqs, setLoadingReqs] = useState(false);
  const [personalVolume, setPersonalVolume] = useState(1);
  const volumeDebounceRef = useRef(null);

  useEffect(() => {
    if (device) {
      setEditName(device.name || device.deviceId);
      setPersonalVolume(typeof device.personalVolume === 'number' ? device.personalVolume : 1);
      setRequirements(device.requirementsDetail || null);
    }
  }, [device]);

  const loadRequirements = async () => {
    setLoadingReqs(true);
    try {
      const data = await getRequirements(deviceId);
      setRequirements(data.requirements || []);
    } catch {
      setRequirements(null);
    }
    setLoadingReqs(false);
  };

  const handleSaveName = async () => {
    if (editName !== device.name) {
      await setDeviceName(deviceId, editName);
    }
    setEditingName(false);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      handleSaveName();
    }
    if (event.key === 'Escape') {
      setEditingName(false);
    }
  };

  if (!device) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal" onClick={(event) => event.stopPropagation()}>
          <p>{t('Device not found')}</p>
          <button className="btn" onClick={onClose}>{t('Close')}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal device-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="dialog-header">
          {editingName ? (
            <input
              className="name-input"
              value={editName}
              onChange={(event) => setEditName(event.target.value)}
              onBlur={handleSaveName}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          ) : (
            <h2 className="dialog-title" onClick={() => setEditingName(true)} title={t('Click to rename')}>
              {device.name || device.deviceId}
            </h2>
          )}
          <button className="btn-close" onClick={onClose}>x</button>
        </div>

        {!device.online && <div className="dialog-warning">{t('Device is offline')}</div>}

        <div className="dialog-section">
          <h3>{t('Device Info')}</h3>
          <table className="info-table">
            <tbody>
              <tr><td>Device ID</td><td>{device.deviceId}</td></tr>
              <tr><td>IP</td><td>{device.ip}</td></tr>
              <tr>
                <td>{t('Battery')}</td>
                <td>{device.battery > 0 ? `${device.battery}%${device.batteryCharging ? ' (charging)' : ''}` : t('Unknown')}</td>
              </tr>
              <tr><td>{t('Uptime')}</td><td>{device.uptimeMinutes} {t('min')}</td></tr>
              <tr>
                <td>{t('Player')}</td>
                <td className={device.playerConnected ? 'text-ok' : 'text-warn'}>
                  {device.playerConnected ? `${t('Connected')} (v${device.playerVersion || '-'})` : t('Player offline')}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="dialog-section">
          <h3>{t('Requirements')}</h3>
          {loadingReqs ? (
            <p>{t('Checking requirements...')}</p>
          ) : requirements ? (
            <div className="req-list">
              {requirements.map((requirement, index) => (
                <div key={index} className={`req-item ${requirement.present ? 'req-item-ok' : 'req-item-fail'}`}>
                  <span>{requirement.present ? '\u2705' : '\u274C'}</span>
                  <span className="req-name">{requirement.name || requirement.filename}</span>
                  <span className="req-type">{requirement.filename}</span>
                </div>
              ))}
              {requirements.length === 0 && <p>{t('No requirements configured')}</p>}
            </div>
          ) : (
            <p>{t('Unable to check requirements')}</p>
          )}
          <button className="btn btn-small" onClick={loadRequirements}>
            {t('Refresh')}
          </button>
        </div>

        <div className="dialog-section">
          <h3>{t('Audio')}</h3>
          <div className="volume-control">
            <label htmlFor="personal-volume-slider">{t('Device volume')}</label>
            <input
              id="personal-volume-slider"
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={personalVolume}
              disabled={!device.online}
              onChange={(event) => {
                const value = Number(event.target.value);
                setPersonalVolume(value);
                if (volumeDebounceRef.current) {
                  clearTimeout(volumeDebounceRef.current);
                }
                volumeDebounceRef.current = setTimeout(() => setDeviceVolume(deviceId, value), 150);
              }}
            />
            <span>{Math.round(personalVolume * 100)}%</span>
          </div>
          <p className="dialog-playback-info">
            {t('Effective volume')}: <strong>{Math.round((device.effectiveVolume ?? personalVolume) * 100)}%</strong>
          </p>
        </div>

        <div className="dialog-section">
          <h3>{t('Playback Controls')}</h3>
          <div className="dialog-controls">
            <button className="btn btn-success" disabled={!device.online || !device.playerConnected} onClick={onPlayVideo}>
              {t('Open Video')}
            </button>
            <button className="btn" disabled={!device.online || !device.playerConnected} onClick={() => playbackCommand('play', [deviceId])}>
              {t('Play')}
            </button>
            <button className="btn" disabled={!device.online || !device.playerConnected} onClick={() => playbackCommand('pause', [deviceId])}>
              {t('Pause')}
            </button>
            <button className="btn" disabled={!device.online || !device.playerConnected} onClick={() => playbackCommand('stop', [deviceId])}>
              {t('Stop')}
            </button>
            <button className="btn" disabled={!device.online || !device.playerConnected} onClick={() => playbackCommand('recenter', [deviceId])}>
              {t('Recenter')}
            </button>
            <button className="btn" disabled={!device.online || !device.playerConnected} onClick={() => pingDevice(deviceId)}>
              {t('Ping')}
            </button>
            <button
              className="btn btn-dim"
              disabled={!device.online || !device.playerConnected}
              onClick={() => toggleDeviceDebug(deviceId)}
              title={t('Toggle debug panel on this device')}
            >
              {t('Debug')}
            </button>
          </div>

          {device.playbackState !== 'idle' && (
            <div className="dialog-playback-info">
              <p>
                {t('State')}: <strong>{device.playbackState}</strong> | {t('Mode')}: <strong>{device.currentMode}</strong>
                {device.loop && ` | ${t('Loop')}`}
              </p>
              {device.currentVideo && <p>{t('File')}: {device.currentVideo}</p>}
              {device.playbackDuration > 0 && (
                <div className="progress-bar large">
                  <div
                    className="progress-fill"
                    style={{ width: `${(device.playbackTime / device.playbackDuration) * 100}%` }}
                  />
                  <span className="progress-text">
                    {formatTime(device.playbackTime)} / {formatTime(device.playbackDuration)}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(seconds) {
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
