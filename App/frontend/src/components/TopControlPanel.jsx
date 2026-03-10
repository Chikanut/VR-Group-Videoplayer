import React, { useRef, useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { playbackCommand, getGlobalVolume, setGlobalVolume } from '../api';

export default function TopControlPanel({ onPlayAll }) {
  const navigate = useNavigate();
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlineDevices = devices.filter((d) => d.online);
  const ignoreReq = config?.ignoreRequirements || false;
  const hasCommandTargets = onlineDevices.some((d) => d.playerConnected || (ignoreReq && d.adbConnected));
  const debounceRef = useRef({});
  const volumeDebounceRef = useRef(null);
  const [globalVolume, setGlobalVolumeValue] = useState(1);

  const debounce = useCallback((key, fn) => {
    if (debounceRef.current[key]) return;
    debounceRef.current[key] = true;
    fn();
    setTimeout(() => { debounceRef.current[key] = false; }, 1000);
  }, []);

  useEffect(() => {
    const loadGlobalVolume = async () => {
      try {
        const data = await getGlobalVolume();
        if (typeof data.globalVolume === 'number') {
          setGlobalVolumeValue(data.globalVolume);
        }
      } catch {}
    };
    loadGlobalVolume();
  }, []);

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
          className="btn btn-success"
          disabled={!hasCommandTargets}
          onClick={() => debounce('playAll', onPlayAll)}
        >
          Play All
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('pauseAll', () => playbackCommand('pause'))}
        >
          Pause All
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('resumeAll', () => playbackCommand('play'))}
        >
          Resume All
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('stopAll', () => playbackCommand('stop'))}
        >
          Stop All
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('recenterAll', () => playbackCommand('recenter'))}
        >
          Recenter All
        </button>
        <div className="volume-control global-volume-control">
          <label htmlFor="global-volume-slider">Global volume</label>
          <input
            id="global-volume-slider"
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={globalVolume}
            onChange={(e) => {
              const value = Number(e.target.value);
              setGlobalVolumeValue(value);
              if (volumeDebounceRef.current) clearTimeout(volumeDebounceRef.current);
              volumeDebounceRef.current = setTimeout(() => setGlobalVolume(value), 150);
            }}
          />
          <span>{Math.round(globalVolume * 100)}%</span>
        </div>
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
