import React, { useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { playbackCommand, updateAllDevices } from '../api';

export default function TopControlPanel({ onPlayAll }) {
  const navigate = useNavigate();
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlineDevices = devices.filter((d) => d.online);
  const hasOnline = onlineDevices.length > 0;
  const hasPlayerDevices = onlineDevices.some((d) => d.playerConnected);
  const debounceRef = useRef({});

  const debounce = useCallback((key, fn) => {
    if (debounceRef.current[key]) return;
    debounceRef.current[key] = true;
    fn();
    setTimeout(() => { debounceRef.current[key] = false; }, 1000);
  }, []);

  const needsUpdate = onlineDevices.filter(
    (d) => d.adbConnected && d.requirementsMet === false
  );

  return (
    <header className="top-panel">
      <div className="top-panel-left">
        <h1 className="top-panel-title">VR Classroom</h1>
        <span className="device-count">
          {onlineDevices.length}/{devices.length} online
        </span>
      </div>
      <div className="top-panel-controls">
        <button
          className="btn btn-primary"
          disabled={!hasOnline}
          onClick={() => debounce('updateAll', async () => {
            if (needsUpdate.length === 0) {
              alert('All devices up to date');
              return;
            }
            const noAdb = onlineDevices.filter((d) => !d.adbConnected);
            if (noAdb.length > 0) {
              const proceed = confirm(
                `${noAdb.length} device(s) without ADB will be skipped. Continue?`
              );
              if (!proceed) return;
            }
            await updateAllDevices();
          })}
        >
          Update All {needsUpdate.length > 0 && `(${needsUpdate.length})`}
        </button>
        <button
          className="btn btn-success"
          disabled={!hasPlayerDevices}
          onClick={() => debounce('playAll', onPlayAll)}
        >
          Play All
        </button>
        <button
          className="btn"
          disabled={!hasPlayerDevices}
          onClick={() => debounce('pauseAll', () => playbackCommand('pause'))}
        >
          Pause All
        </button>
        <button
          className="btn"
          disabled={!hasPlayerDevices}
          onClick={() => debounce('stopAll', () => playbackCommand('stop'))}
        >
          Stop All
        </button>
        <button
          className="btn"
          disabled={!hasPlayerDevices}
          onClick={() => debounce('recenterAll', () => playbackCommand('recenter'))}
        >
          Recenter All
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => navigate('/settings')}
        >
          Settings
        </button>
      </div>
    </header>
  );
}
