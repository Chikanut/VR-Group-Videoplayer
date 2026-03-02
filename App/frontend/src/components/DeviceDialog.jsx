import React, { useState, useEffect } from 'react';
import useDeviceStore from '../store/deviceStore';
import {
  setDeviceName,
  pingDevice,
  updateDevice,
  getRequirements,
  playbackCommand,
  launchPlayerSingle,
  toggleDeviceDebug,
} from '../api';
import UpdateProgress from './UpdateProgress';

export default function DeviceDialog({ deviceId, onClose, onPlayVideo }) {
  const device = useDeviceStore((s) => s.devices[deviceId]);
  const [editName, setEditName] = useState('');
  const [editingName, setEditingName] = useState(false);
  const [requirements, setRequirements] = useState(null);
  const [loadingReqs, setLoadingReqs] = useState(false);

  useEffect(() => {
    if (device) {
      setEditName(device.name || device.deviceId);
      loadRequirements();
    }
  }, [deviceId]);

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

  if (!device) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal" onClick={(e) => e.stopPropagation()}>
          <p>Device not found</p>
          <button className="btn" onClick={onClose}>Close</button>
        </div>
      </div>
    );
  }

  const handleSaveName = async () => {
    if (editName && editName !== device.name) {
      await setDeviceName(deviceId, editName);
    }
    setEditingName(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSaveName();
    if (e.key === 'Escape') setEditingName(false);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal device-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          {editingName ? (
            <input
              className="name-input"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              onBlur={handleSaveName}
              onKeyDown={handleKeyDown}
              autoFocus
            />
          ) : (
            <h2
              className="dialog-title"
              onClick={() => setEditingName(true)}
              title="Click to rename"
            >
              {device.name || device.deviceId}
            </h2>
          )}
          <button className="btn-close" onClick={onClose}>x</button>
        </div>

        {!device.online && (
          <div className="dialog-warning">Device is offline</div>
        )}

        <div className="dialog-section">
          <h3>Device Info</h3>
          <table className="info-table">
            <tbody>
              <tr><td>Device ID</td><td>{device.deviceId}</td></tr>
              <tr><td>IP</td><td>{device.ip}</td></tr>
              <tr>
                <td>Battery</td>
                <td>{device.battery >= 0 ? `${device.battery}%${device.batteryCharging ? ' (charging)' : ''}` : 'Unknown'}</td>
              </tr>
              <tr><td>Uptime</td><td>{device.uptimeMinutes} min</td></tr>
              <tr>
                <td>ADB</td>
                <td className={device.adbConnected ? 'text-ok' : 'text-warn'}>
                  {device.adbConnected ? 'Connected' : 'Not connected'}
                </td>
              </tr>
              <tr>
                <td>Player</td>
                <td className={device.playerConnected ? 'text-ok' : 'text-warn'}>
                  {device.playerConnected ? `Connected (v${device.playerVersion})` : 'Not connected'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="dialog-section">
          <h3>Requirements</h3>
          {loadingReqs ? (
            <p>Checking requirements...</p>
          ) : requirements ? (
            <div className="req-list">
              {requirements.map((r, i) => (
                <div key={i} className={`req-item ${r.present ? 'req-item-ok' : 'req-item-fail'}`}>
                  <span>{r.present ? '\u2705' : '\u274C'}</span>
                  <span className="req-name">{r.name || r.devicePath}</span>
                  <span className="req-type">{r.type}</span>
                </div>
              ))}
              {requirements.length === 0 && <p>No requirements configured</p>}
            </div>
          ) : (
            <p>Unable to check requirements</p>
          )}
          {device.online && device.adbConnected && (device.requirementsMet === false || device.requirementsMet === null) && (
            <button
              className="btn btn-primary"
              onClick={() => updateDevice(deviceId)}
              disabled={device.updateInProgress}
            >
              {device.updateInProgress ? 'Updating...' : 'Update Device'}
            </button>
          )}
          <button className="btn btn-small" onClick={loadRequirements}>
            Refresh
          </button>
        </div>

        {device.updateInProgress && device.updateProgress && (
          <div className="dialog-section">
            <h3>Update Progress</h3>
            <UpdateProgress progress={device.updateProgress} />
          </div>
        )}

        {device.online && device.adbConnected && !device.playerConnected && (
          <div className="dialog-section">
            <h3>Player</h3>
            <p className="text-warn">Player not connected. You can try to launch it via ADB.</p>
            <button
              className="btn btn-primary"
              onClick={async () => {
                const result = await launchPlayerSingle(deviceId);
                if (result.error && (!result.success || result.success.length === 0)) {
                  alert(result.error);
                } else if (result.success && result.success.length > 0) {
                  const s = result.success[0];
                  alert(s.playerConnected ? 'Player launched and HTTP connected!' : 'Player launched but HTTP not responding yet.');
                }
              }}
            >
              Launch Player via ADB
            </button>
          </div>
        )}

        <div className="dialog-section">
          <h3>Playback Controls</h3>
          <div className="dialog-controls">
            <button
              className="btn btn-success"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={onPlayVideo}
            >
              Open Video
            </button>
            <button
              className="btn"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => playbackCommand('play', [deviceId])}
            >
              Play
            </button>
            <button
              className="btn"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => playbackCommand('pause', [deviceId])}
            >
              Pause
            </button>
            <button
              className="btn"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => playbackCommand('stop', [deviceId])}
            >
              Stop
            </button>
            <button
              className="btn"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => playbackCommand('recenter', [deviceId])}
            >
              Recenter
            </button>
            <button
              className="btn"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => pingDevice(deviceId)}
            >
              Ping
            </button>
            <button
              className="btn btn-dim"
              disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
              onClick={() => toggleDeviceDebug(deviceId)}
              title="Toggle debug panel on this device"
            >
              Debug
            </button>
          </div>
          {device.playbackState !== 'idle' && (
            <div className="dialog-playback-info">
              <p>
                State: <strong>{device.playbackState}</strong> | Mode: <strong>{device.currentMode}</strong>
                {device.loop && ' | Loop'}
              </p>
              {device.currentVideo && (
                <p>File: {device.currentVideo}</p>
              )}
              {device.playbackDuration > 0 && (
                <div className="progress-bar large">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${(device.playbackTime / device.playbackDuration) * 100}%`,
                    }}
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
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}
