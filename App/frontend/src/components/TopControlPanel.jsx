import React, { useRef, useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { playbackCommand, updateAllDevices, getUsbDevices, updateUsbDevice, launchPlayer, getGlobalVolume, setGlobalVolume } from '../api';
import { useI18n } from '../i18n';

export default function TopControlPanel({ onPlayAll, panelRef }) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlineDevices = devices.filter((d) => d.online);
  const hasOnline = onlineDevices.length > 0;
  const ignoreReq = config?.ignoreRequirements || false;
  const adbAvailable = config?.adbAvailable !== false;
  const adbEnabled = config?.adbEnabled !== false && adbAvailable;
  const isAndroidRuntime = config?.isAndroidRuntime === true;
  const hasCommandTargets = onlineDevices.some((d) => d.playerConnected || (ignoreReq && adbEnabled && d.adbConnected));
  const hasAdbDevices = adbEnabled && onlineDevices.some((d) => d.adbConnected);
  const adbNoPlayer = adbEnabled ? onlineDevices.filter((d) => d.adbConnected && !d.playerConnected) : [];
  const debounceRef = useRef({});
  const [usbScanning, setUsbScanning] = useState(false);
  const [usbMenuOpen, setUsbMenuOpen] = useState(false);
  const [usbOptions, setUsbOptions] = useState({
    enableWirelessAdb: true,
    updateApp: true,
    updateContent: true,
  });
  const usbMenuRef = useRef(null);
  const volumeDebounceRef = useRef(null);
  const [globalVolume, setGlobalVolumeValue] = useState(1);

  const debounce = useCallback((key, fn) => {
    if (debounceRef.current[key]) return;
    debounceRef.current[key] = true;
    fn();
    setTimeout(() => { debounceRef.current[key] = false; }, 1000);
  }, []);

  useEffect(() => {
    if (!usbMenuOpen) return;
    const handleClick = (e) => {
      if (usbMenuRef.current && !usbMenuRef.current.contains(e.target)) {
        setUsbMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [usbMenuOpen]);

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

  useEffect(() => {
    if (!config) return;
    console.info('[VR Classroom] Runtime mode', {
      isAndroidRuntime: config.isAndroidRuntime,
      adbAvailable: config.adbAvailable,
      adbEnabled: config.adbEnabled,
      networkSubnet: config.networkSubnet,
    });
  }, [config]);

  const needsUpdate = onlineDevices.filter(
    (d) => (adbEnabled ? d.adbConnected : d.playerConnected) && d.requirementsMet === false
  );
  const showAdbControls = !isAndroidRuntime;

  const handleUsbInit = async () => {
    const hasAnySelected = usbOptions.enableWirelessAdb || usbOptions.updateApp || usbOptions.updateContent;
    if (!hasAnySelected) {
      alert(t('Select at least one initialization option.'));
      return;
    }

    setUsbScanning(true);
    setUsbMenuOpen(false);
    try {
      const data = await getUsbDevices();
      const serials = data.devices || [];
      if (serials.length === 0) {
        alert(t('No USB devices found. Connect a Quest headset via USB cable.'));
      } else {
        for (const serial of serials) {
          await updateUsbDevice(serial, usbOptions);
        }
        alert(t('Started initialization for {count} USB device(s). Check progress below.', { count: serials.length }));
      }
    } catch (e) {
      alert(t('Failed to scan USB devices'));
    }
    setUsbScanning(false);
  };

  const toggleOption = (key) => {
    setUsbOptions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

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
        {showAdbControls && (
        <button
          className="btn btn-primary"
          disabled={!hasOnline}
          onClick={() => debounce('updateAll', async () => {
            if (needsUpdate.length === 0) {
              alert(t('All devices up to date'));
              return;
            }
            if (adbEnabled) {
              const noAdb = onlineDevices.filter((d) => !d.adbConnected);
              if (noAdb.length > 0) {
                const proceed = confirm(
                  t('{count} device(s) without ADB will be skipped. Continue?', { count: noAdb.length })
                );
                if (!proceed) return;
              }
            }
            await updateAllDevices();
          })}
        >
          {t('Update All')} {needsUpdate.length > 0 && `(${needsUpdate.length})`}
        </button>
        )}
        {showAdbControls && adbEnabled && (
        <div className="usb-init-wrapper" ref={usbMenuRef}>
          <button
            className="btn"
            onClick={() => !usbScanning && setUsbMenuOpen(!usbMenuOpen)}
            disabled={usbScanning}
          >
            {usbScanning ? t('Scanning USB...') : t('USB Init')}
          </button>
          {usbMenuOpen && (
            <div className="usb-init-menu">
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.enableWirelessAdb}
                  onChange={() => toggleOption('enableWirelessAdb')}
                />
                <span>{t('Wireless ADB')}</span>
              </label>
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.updateApp}
                  onChange={() => toggleOption('updateApp')}
                />
                <span>{t('Update App')}</span>
              </label>
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.updateContent}
                  onChange={() => toggleOption('updateContent')}
                />
                <span>{t('Update Content')}</span>
              </label>
              <button
                className="btn btn-primary usb-init-start"
                onClick={handleUsbInit}
              >
                {t('Start')}
              </button>
            </div>
          )}
        </div>
        )}
        {showAdbControls && adbEnabled && (
        <button
          className="btn"
          disabled={!hasAdbDevices}
          title={adbNoPlayer.length > 0 ? t('{count} device(s) without player', { count: adbNoPlayer.length }) : t('Launch player on all ADB devices')}
          onClick={() => debounce('launchPlayer', async () => {
            const result = await launchPlayer();
            if (result.error && (!result.success || result.success.length === 0)) {
              alert(result.error);
            } else if (result.success) {
              alert(t('Player launch command sent to {count} device(s).', { count: result.success.length }));
            }
          })}
        >
          {t('Launch Player')} {adbNoPlayer.length > 0 && `(${adbNoPlayer.length})`}
        </button>
        )}
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
          {t('Settings')}
        </button>
      </div>
    </header>
  );
}
