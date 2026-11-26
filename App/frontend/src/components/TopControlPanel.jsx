import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import {
  getGlobalVolume,
  playbackCommand,
  playbackSeek,
  playerAction,
  setAutostart,
  setGlobalVolume,
  syncContent,
} from '../api';
import { useI18n } from '../i18n';

export default function TopControlPanel({ onPlayAll, panelRef }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const config = useDeviceStore((state) => state.config);
  const devices = useDeviceStore((state) => state.getDeviceList());
  const onlineDevices = devices.filter((device) => device.online);
  const selectedIds = useDeviceStore((state) => state.selectedIds);
  const clearSelection = useDeviceStore((state) => state.clearSelection);
  // Ticked tiles narrow every command; none or all ticked = whole class (empty deviceIds).
  const selectedDevices = devices.filter((device) => selectedIds[device.deviceId]);
  const scoped = selectedDevices.length > 0 && selectedDevices.length < devices.length;
  const scopeIds = scoped ? selectedDevices.map((device) => device.deviceId) : [];
  const scopeDevices = scoped ? selectedDevices : devices;
  const commandTargets = scopeDevices.filter((device) => device.online && device.playerConnected);
  const label = (all, one) => (scoped ? `${t(one)} (${selectedDevices.length})` : t(all));
  const [autostartResult, setAutostartResult] = useState('');
  const hasCommandTargets = commandTargets.length > 0;
  // Headset agents (player 1.9.0+) answer with the player closed.
  const agentTargets = scopeDevices.filter((device) => device.online && device.agentConnected);
  const hasAgentTargets = agentTargets.length > 0;
  const [agentResult, setAgentResult] = useState('');

  const showAgentResult = (text) => {
    setAgentResult(text);
    setTimeout(() => setAgentResult(''), 5000);
  };

  const runPlayerAction = async (action, doneLabel) => {
    try {
      const result = await playerAction(action, scopeIds);
      showAgentResult(`${t(doneLabel)}: ${result.success.length}`);
    } catch {
      showAgentResult(t('Command failed'));
    }
  };

  const runSync = async () => {
    try {
      const result = await syncContent(scopeIds);
      if (result.success === false) {
        showAgentResult(t(result.error || 'Command failed'));
        return;
      }
      const missing = result.missingInLibrary?.length
        ? ` · ${t('Not in the library')}: ${result.missingInLibrary.join(', ')}`
        : '';
      showAgentResult(`${t('Sync sent to headsets')}: ${result.sent}${missing}`);
    } catch {
      showAgentResult(t('Command failed'));
    }
  };
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

  const switchAutostart = async (enabled) => {
    try {
      const result = await setAutostart(enabled, scopeIds);
      setAutostartResult(`${t(enabled ? 'Autostart enabled' : 'Autostart disabled')}: ${result.success.length}`);
    } catch {
      setAutostartResult(t('Failed to switch autostart'));
    }
    setTimeout(() => setAutostartResult(''), 5000);
  };

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
          onClick={() => debounce('playAll', () => onPlayAll(scopeIds))}
        >
          {label('Play All', 'Play')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('pauseAll', () => playbackCommand('pause', scopeIds))}
        >
          {label('Pause All', 'Pause')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('resumeAll', () => playbackCommand('play', scopeIds))}
        >
          {label('Resume All', 'Resume')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('stopAll', () => playbackCommand('stop', scopeIds))}
        >
          {label('Stop All', 'Stop')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets}
          onClick={() => debounce('recenterAll', () => playbackCommand('recenter', scopeIds))}
        >
          {label('Recenter All', 'Recenter')}
        </button>
        <button
          className="btn"
          disabled={!hasCommandTargets && !hasAgentTargets}
          title={t('Sleep hint')}
          onClick={() => debounce('sleepAll', () => playbackCommand('sleep', scopeIds))}
        >
          {label('Sleep All', 'Sleep')}
        </button>
        <button
          className="btn"
          title={t('Wake hint')}
          onClick={() => debounce('wakeAll', () => playbackCommand('wake', scopeIds))}
        >
          {label('Wake All', 'Wake')}
        </button>

        <button
          className="btn"
          title={t('Autostart hint')}
          onClick={() => debounce('autostartOn', () => switchAutostart(true))}
        >
          {label('Enable autostart', 'Enable autostart')}
        </button>
        <button
          className="btn"
          title={t('Autostart hint')}
          onClick={() => debounce('autostartOff', () => switchAutostart(false))}
        >
          {label('Disable autostart', 'Disable autostart')}
        </button>
        {autostartResult && <span className="device-count">{autostartResult}</span>}

        <button
          className="btn"
          disabled={!hasAgentTargets}
          title={t('Open player hint')}
          onClick={() => debounce('launchPlayer', () => runPlayerAction('launch', 'Open sent'))}
        >
          {label('Open player', 'Open player')}
        </button>
        <button
          className="btn"
          disabled={!hasAgentTargets}
          title={t('Restart player hint')}
          onClick={() => debounce('restartPlayer', () => runPlayerAction('restart', 'Restart sent'))}
        >
          {label('Restart player', 'Restart player')}
        </button>
        <button
          className="btn"
          disabled={!hasAgentTargets}
          title={t('Close player hint')}
          onClick={() => debounce('closePlayer', () => runPlayerAction('close', 'Close sent'))}
        >
          {label('Close player', 'Close player')}
        </button>
        <button
          className="btn"
          disabled={!hasAgentTargets}
          title={t('Sync content hint')}
          onClick={() => debounce('syncContent', runSync)}
        >
          {label('Sync content', 'Sync content')}
        </button>
        {agentResult && <span className="device-count">{agentResult}</span>}
        {scoped && (
          <button className="btn btn-dim" onClick={clearSelection} title={t('Commands go to the ticked headsets only')}>
            {t('Selected: {count}', { count: selectedDevices.length })} ✕
          </button>
        )}

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
              seekDebounceRef.current = setTimeout(async () => {
                try {
                  await playbackSeek(value, scopeIds);
                } catch {}
                setSeekValue(value);
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
