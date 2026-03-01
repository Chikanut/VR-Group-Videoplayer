import React from 'react';
import useDeviceStore from '../store/deviceStore';
import { pingDevice, updateDevice } from '../api';
import UpdateProgress from './UpdateProgress';

function getBorderClass(device) {
  if (!device.online) return 'tile-offline';
  if (device.requirementsMet === false) return 'tile-error';
  const config = useDeviceStore.getState().config;
  const threshold = config?.batteryThreshold || 20;
  if (device.battery >= 0 && device.battery <= threshold) return 'tile-warning';
  return 'tile-ok';
}

function BatteryIcon({ level, charging }) {
  if (level < 0) return <span className="battery-unknown">?</span>;
  let icon = '🔋';
  if (charging) icon = '⚡';
  else if (level <= 10) icon = '🪫';
  return <span className="battery-icon">{icon} {level}%</span>;
}

export default function DeviceTile({ device, onClick }) {
  const config = useDeviceStore((s) => s.config);
  const threshold = config?.batteryThreshold || 20;
  const isLowBattery = device.battery >= 0 && device.battery <= threshold;
  const isPlaying = device.playbackState === 'playing' || device.playbackState === 'paused';

  const handlePing = (e) => {
    e.stopPropagation();
    pingDevice(device.deviceId);
  };

  const handleUpdate = (e) => {
    e.stopPropagation();
    updateDevice(device.deviceId);
  };

  return (
    <div className={`device-tile ${getBorderClass(device)}`} onClick={onClick}>
      <div className="tile-header">
        <span className="tile-name" title={device.name || device.deviceId}>
          {device.name || device.deviceId}
        </span>
        <span className={`tile-status-dot ${device.online ? 'dot-online' : 'dot-offline'}`} />
      </div>

      <div className="tile-info">
        <span className="tile-ip">{device.ip}</span>
        <BatteryIcon level={device.battery} charging={device.batteryCharging} />
      </div>

      <div className="tile-status-row">
        {device.online ? (
          <>
            {device.adbConnected ? (
              <span className="badge badge-ok">ADB</span>
            ) : (
              <span className="badge badge-warn" title="ADB not connected. Install/Push unavailable">
                No ADB
              </span>
            )}
            {device.playerConnected ? (
              <span className="badge badge-ok">Player</span>
            ) : (
              <span className="badge badge-warn">No Player</span>
            )}
          </>
        ) : (
          <span className="badge badge-offline">Offline</span>
        )}
      </div>

      {device.online && (
        <div className="tile-requirements">
          {device.requirementsMet === null ? (
            <span className="req-checking">Checking...</span>
          ) : device.requirementsMet ? (
            <span className="req-ok">Requirements met</span>
          ) : (
            <span className="req-fail">
              Requirements missing
              {device.adbConnected && (
                <button className="btn-small btn-update" onClick={handleUpdate}>
                  Update
                </button>
              )}
            </span>
          )}
        </div>
      )}

      {isPlaying && (
        <div className="tile-playback">
          <span className="playback-file" title={device.currentVideo}>
            {device.playbackState === 'playing' ? '▶' : '⏸'}{' '}
            {device.currentVideo ? device.currentVideo.split('/').pop() : ''}
          </span>
          {device.playbackDuration > 0 && (
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${(device.playbackTime / device.playbackDuration) * 100}%` }}
              />
            </div>
          )}
        </div>
      )}

      {device.updateInProgress && device.updateProgress && (
        <UpdateProgress progress={device.updateProgress} compact />
      )}

      <div className="tile-actions">
        <button
          className="btn-small"
          disabled={!device.online || (!device.playerConnected && !device.adbConnected)}
          onClick={handlePing}
        >
          Ping
        </button>
      </div>

      {isLowBattery && <div className="low-battery-indicator" title="Low battery" />}
    </div>
  );
}
