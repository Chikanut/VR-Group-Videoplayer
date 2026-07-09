import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { getGlobalVolume, playbackCommand, playbackSeek, setGlobalVolume } from '../api';
import { useI18n } from '../i18n';

export default function TopControlPanel({ onPlayAll, panelRef }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const config = useDeviceStore((state) => state.config);
  const devices = useDeviceStore((state) => state.getDeviceList());
  const onlineDevices = devices.filter((device) => device.online);
  const commandTargets = onlineDevices.filter((device) => device.playerConnected);
  const hasCommandTargets = commandTargets.length > 0;
  const isAndroidRuntime = config?.isAndroidRuntime === true;
  const debounceRef = useRef({});
  const volumeDebounceRef = useRef(null);
  const seekDebounceRef = useRef(null);
  const [globalVolume, setGlobalVolumeValue] = useState(1);
  const [seekValue, setSeekValue] = useState(0);
  const [seeking, setSeeking] = useState(false);

  // Representative device for the global seek slider: the command target with the
  // longest known duration. Empty deviceIds on seek fans out to all players anyway.
  const seekTargets = commandTargets.filter((device) => device.playbackDuration > 0);
  const seekReference = seekTargets.reduce(
    (best, device) => (!best || device.playbackDuration > best.playbackDuration ? device : best),
    null,
  );
  const seekDuration = seekReference ? seekReference.playbackDuration : 0;
  const seekCurrent = seekReference ? seekReference.playbackTime : 0;
  const canSeek = seekTargets.length > 0;

  const debounce = useCallback((key, fn) => {
    if (debounceRef.current[key]) {
      return;
    }
    debounceRef.current[key] = true;
    fn();
    setTimeout(() => {
      debounceRef.current[key] = false;
    }, 1000);
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

  // Keep the slider following live playback unless the user is actively dragging it.
  useEffect(() => {
    if (!seeking) {
      setSeekValue(seekCurrent);
    }
  }, [seekCurrent, seeking]);

  return (
    <header className="top-panel" ref={panelRef}>
      <div className="top-panel-left">
        <h1 className="top-panel-title">VR Classroom</h1>
        <span className="device-count">
          {t('{online}/{total} online', { online: onlineDevices.length, total: devices.length })}
        </span>
        <span className="runtime-badge" title={t('Runtime mode detected by backend config')}>
          {t('Mode')}: {isAndroidRuntime ? t('Android') : t('Desktop')}
        </span>
      </div>

      <div className="top-panel-controls">
        <button
          className="btn btn-success"
          disabled={!hasCommandTargets}
          onClick={() => debounce('playAll', onPlayAll)}
        >
          {t('Play All')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('pauseAll', () => playbackCommand('pause'))}
        >
          {t('Pause All')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('resumeAll', () => playbackCommand('play'))}
        >
          {t('Resume All')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('stopAll', () => playbackCommand('stop'))}
        >
          {t('Stop All')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('recenterAll', () => playbackCommand('recenter'))}
        >
          {t('Recenter All')}
        </button>

        <div className="volume-control global-volume-control">
          <label htmlFor="global-volume-slider">{t('Global volume')}</label>
          <input
            id="global-volume-slider"
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={globalVolume}
            onChange={(event) => {
              const value = Number(event.target.value);
              setGlobalVolumeValue(value);
              if (volumeDebounceRef.current) {
                clearTimeout(volumeDebounceRef.current);
              }
              volumeDebounceRef.current = setTimeout(() => setGlobalVolume(value), 150);
            }}
          />
          <span>{Math.round(globalVolume * 100)}%</span>
        </div>

        <div className="seek-control global-seek-control">
          <label htmlFor="global-seek-slider">{t('Seek')}</label>
          <input
            id="global-seek-slider"
            type="range"
            min="0"
            max={seekDuration || 1}
            step="0.1"
            value={seekValue}
            disabled={!canSeek}
            onChange={(event) => {
              const value = Number(event.target.value);
              setSeeking(true);
              setSeekValue(value);
              if (seekDebounceRef.current) {
                clearTimeout(seekDebounceRef.current);
              }
              seekDebounceRef.current = setTimeout(() => {
                playbackSeek(value);
                setSeeking(false);
              }, 200);
            }}
          />
          <span>{formatTime(seekValue)} / {formatTime(seekDuration)}</span>
        </div>

        <button className="btn btn-secondary" onClick={() => navigate('/settings')}>
          {t('Settings')}
        </button>
      </div>
    </header>
  );
}

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
