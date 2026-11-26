import React, { useEffect, useRef, useState } from 'react';
import useDeviceStore from '../store/deviceStore';
import {
  getAutostart,
  setAutostart,
  getRequirements,
  pingDevice,
  setDeviceName,
  setDeviceVolume,
  toggleDeviceDebug,
} from '../api';
import { useI18n } from '../i18n';

export default function DeviceDialog({ deviceId, onClose }) {
  const { t } = useI18n();
  const device = useDeviceStore((state) => state.devices[deviceId]);
  const [editName, setEditName] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [nameStatus, setNameStatus] = useState(null); // { kind: 'ok'|'pending'|'error'|'sending', text }
  const [requirements, setRequirements] = useState(null);
  const [loadingReqs, setLoadingReqs] = useState(false);
  const [personalVolume, setPersonalVolume] = useState(1);
  const volumeDebounceRef = useRef(null);
  const [autostart, setAutostartState] = useState(undefined); // undefined = asking, null = unknown

  // Asked from the headset's watchdog each time the card opens: it answers even with the player closed.
  useEffect(() => {
    let cancelled = false;
    setAutostartState(undefined);
    getAutostart(deviceId)
      .then((result) => { if (!cancelled) setAutostartState(result.autostart ?? null); })
      .catch(() => { if (!cancelled) setAutostartState(null); });
    return () => { cancelled = true; };
  }, [deviceId]);

  const toggleAutostart = async () => {
    const wanted = !autostart;
    setAutostartState(undefined);
    try {
      const result = await setAutostart(wanted, [deviceId]);
      setAutostartState(result.success.length ? wanted : null);
    } catch {
      setAutostartState(null);
    }
  };

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
    const nextName = editName.trim();
    setEditingName(false);
    if (nextName === (device.name || '') || (nextName === '' && device.nameSource === 'id')) {
      return;
    }
    setNameStatus({ kind: 'sending', text: t('Name is being sent to the headset...') });
    try {
      const result = await setDeviceName(deviceId, nextName);
      if (result?.error) {
        setNameStatus({ kind: 'error', text: t('Failed to save name') });
      } else if (result?.pushed) {
        setNameStatus({ kind: 'ok', text: t('Name saved on the headset') });
      } else {
        setNameStatus({
          kind: 'pending',
          text: t('Name saved on the server; will be sent to the headset when it reconnects'),
        });
      }
    } catch {
      setNameStatus({ kind: 'error', text: t('Failed to save name') });
    }
  };

  // Once the headset confirms the name, the server flips nameSource to "device".
  useEffect(() => {
    if (nameStatus && nameStatus.kind !== 'error' && device?.nameSource === 'device') {
      setNameStatus({ kind: 'ok', text: t('Name saved on the headset') });
    }
  }, [device?.nameSource, device?.reportedName]); // eslint-disable-line react-hooks/exhaustive-deps

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
        {nameStatus && (
          <div className={`name-status name-status-${nameStatus.kind}`}>{nameStatus.text}</div>
        )}

        <div className="dialog-section">
          <h3>{t('Device Info')}</h3>
          <table className="info-table">
            <tbody>
              <tr>
                <td>{t('Name / number')}</td>
                <td>
                  {device.name}{' '}
                  <button className="btn-link" onClick={() => setEditingName(true)}>{t('Rename')}</button>
                </td>
              </tr>
              <tr>
                <td>{t('Name on device')}</td>
                <td className={device.nameSource === 'device' ? 'text-ok' : 'text-warn'}>
                  {device.reportedName || t('(none)')}
                  {device.nameSource === 'pending' && ` — ${t('Not saved on the headset yet')}`}
                </td>
              </tr>
              <tr><td>Device ID</td><td className="mono">{device.deviceId}</td></tr>
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
              <tr>
                <td>{t('Player autostart')}</td>
                <td className={autostart === true ? 'text-ok' : 'text-warn'}>
                  {autostart === undefined ? '…' : t(autostart === null ? 'Autostart unknown' : autostart ? 'Autostart on' : 'Autostart off')}
                  {typeof autostart === 'boolean' && (
                    <button className="btn btn-dim" style={{ marginLeft: 8 }} onClick={toggleAutostart}>
                      {t(autostart ? 'Disable' : 'Enable')}
                    </button>
                  )}
                </td>
              </tr>
              {device.settingsProfile && (
                <tr>
                  <td>{t('Headset system settings')}</td>
                  <td className={device.settingsProfile === 'ok' ? 'text-ok' : 'text-warn'}>
                    {t(`settingsProfile ${device.settingsProfile}`)}
                  </td>
                </tr>
              )}
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
          <h3>{t('Playback')}</h3>
          <p className="dialog-playback-info">
            {t('State')}: <strong>{device.playbackState}</strong>
            {device.playbackState !== 'idle' && <> | {t('Mode')}: <strong>{device.currentMode}</strong>{device.loop && ` | ${t('Loop')}`}</>}
          </p>
          {device.currentVideo && device.playbackState !== 'idle' && (
            <p className="dialog-playback-info">
              {t('File')}: {device.currentVideo}
              {device.playbackDuration > 0 && ` (${formatTime(device.playbackTime || 0)} / ${formatTime(device.playbackDuration)})`}
            </p>
          )}
          <p className="dialog-playback-info">{t('Commands hint')}</p>
          <div className="dialog-controls">
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
