import React, { useCallback, useEffect, useRef, useState } from 'react';
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
import AppHeader from './AppHeader';
import Icon from './Icons';

export default function TopControlPanel({ onPlayAll, panelRef }) {
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

  const btn = (key, { icon, all, one, onClick, disabled, title, cls = '' }) => (
    <button
      key={key}
      className={`btn btn-lg ${cls}`}
      disabled={disabled}
      title={title ? t(title) : undefined}
      onClick={() => debounce(key, onClick)}
    >
      {icon && <Icon name={icon} />}
      {label(all, one || all)}
    </button>
  );

  return (
    <header className="top-panel" ref={panelRef}>
      <AppHeader>
        <span className="runtime-badge" title={t('Runtime mode detected by backend config')}>
          {isAndroidRuntime ? t('Android') : t('Desktop')}
        </span>
      </AppHeader>

      <div className="command-bar">
        <div className="command-scope">
          <span className="command-scope-title">{t('Commands')}</span>
          {scoped ? (
            <>
              <span className="chip chip-scope">{t('For selected: {count}', { count: selectedDevices.length })}</span>
              <button className="btn btn-dim" onClick={clearSelection} title={t('Commands go to the ticked headsets only')}>
                {t('Clear selection')}
              </button>
            </>
          ) : (
            <span className="chip chip-offline">
              {t('Whole class')} · {t('{online}/{total} online', { online: onlineDevices.length, total: devices.length })}
            </span>
          )}
          {autostartResult && <span className="command-result">{autostartResult}</span>}
          {agentResult && <span className="command-result">{agentResult}</span>}
        </div>

        <div className="command-groups">
          <div className="cmd-group">
            <span className="group-label">{t('Playback')}</span>
            <div className="cmd-group-buttons">
              {btn('playAll', { icon: 'play', all: 'Play All', one: 'Play', cls: 'btn-primary', disabled: !hasCommandTargets, onClick: () => onPlayAll(scopeIds) })}
              {btn('pauseAll', { icon: 'pause', all: 'Pause All', one: 'Pause', disabled: !hasCommandTargets, onClick: () => playbackCommand('pause', scopeIds) })}
              {btn('resumeAll', { icon: 'resume', all: 'Resume All', one: 'Resume', disabled: !hasCommandTargets, onClick: () => playbackCommand('play', scopeIds) })}
              {btn('stopAll', { icon: 'stop', all: 'Stop All', one: 'Stop', cls: 'btn-danger', disabled: !hasCommandTargets, onClick: () => playbackCommand('stop', scopeIds) })}
              {btn('recenterAll', { icon: 'recenter', all: 'Recenter All', one: 'Recenter', disabled: !hasCommandTargets, onClick: () => playbackCommand('recenter', scopeIds) })}
            </div>
          </div>
          <div className="cmd-group">
            <span className="group-label">{t('Headsets')}</span>
            <div className="cmd-group-buttons">
              {btn('sleepAll', { icon: 'sleep', all: 'Sleep All', one: 'Sleep', title: 'Sleep hint', disabled: !hasCommandTargets && !hasAgentTargets, onClick: () => playbackCommand('sleep', scopeIds) })}
              {btn('wakeAll', { icon: 'wake', all: 'Wake All', one: 'Wake', title: 'Wake hint', onClick: () => playbackCommand('wake', scopeIds) })}
            </div>
          </div>
          <div className="cmd-group">
            <span className="group-label">{t('Player')}</span>
            <div className="cmd-group-buttons">
              {btn('launchPlayer', { all: 'Open player', title: 'Open player hint', disabled: !hasAgentTargets, onClick: () => runPlayerAction('launch', 'Open sent') })}
              {btn('restartPlayer', { all: 'Restart player', title: 'Restart player hint', disabled: !hasAgentTargets, onClick: () => runPlayerAction('restart', 'Restart sent') })}
              {btn('closePlayer', { all: 'Close player', title: 'Close player hint', disabled: !hasAgentTargets, onClick: () => runPlayerAction('close', 'Close sent') })}
            </div>
          </div>
          <div className="cmd-group">
            <span className="group-label">{t('Autostart · content')}</span>
            <div className="cmd-group-buttons">
              {btn('autostartOn', { icon: 'power', all: 'Enable autostart', title: 'Autostart hint', onClick: () => switchAutostart(true) })}
              {btn('autostartOff', { all: 'Disable autostart', title: 'Autostart hint', onClick: () => switchAutostart(false) })}
              {btn('syncContent', { icon: 'sync', all: 'Sync content', title: 'Sync content hint', disabled: !hasAgentTargets, onClick: runSync })}
            </div>
          </div>
        </div>

        <div className="command-sliders">
          <div className="slider-field">
            <div className="slider-head">
              <label htmlFor="global-volume-slider" className="group-label">{t('Global volume')}</label>
              <span className="slider-value">{Math.round(globalVolume * 100)}%</span>
            </div>
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
          </div>
          <div className="slider-field">
            <div className="slider-head">
              <label htmlFor="global-seek-slider" className="group-label">{t('Seek')}</label>
              <span className="slider-value">{formatTime(seekValue)} / {formatTime(seekDuration)}</span>
            </div>
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
          </div>
        </div>
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
