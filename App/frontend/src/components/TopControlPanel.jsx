import React, { useRef, useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { playbackCommand, updateAllDevices, getUsbDevices, updateUsbDevice, launchPlayer, getGlobalVolume, setGlobalVolume } from '../api';

export default function TopControlPanel({ onPlayAll }) {
  const navigate = useNavigate();
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlineDevices = devices.filter((d) => d.online);
  const hasOnline = onlineDevices.length > 0;
  const ignoreReq = config?.ignoreRequirements || false;
  const hasCommandTargets = onlineDevices.some((d) => d.playerConnected || (ignoreReq && d.adbConnected));
  const hasAdbDevices = onlineDevices.some((d) => d.adbConnected);
  const adbNoPlayer = onlineDevices.filter((d) => d.adbConnected && !d.playerConnected);
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

  const needsUpdate = onlineDevices.filter(
    (d) => d.adbConnected && d.requirementsMet === false
  );

  const handleUsbInit = async () => {
    const hasAnySelected = usbOptions.enableWirelessAdb || usbOptions.updateApp || usbOptions.updateContent;
    if (!hasAnySelected) {
      alert('Select at least one initialization option.');
      return;
    }

    setUsbScanning(true);
    setUsbMenuOpen(false);
    try {
      const data = await getUsbDevices();
      const serials = data.devices || [];
      if (serials.length === 0) {
        alert('No USB devices found. Connect a Quest headset via USB cable.');
      } else {
        for (const serial of serials) {
          await updateUsbDevice(serial, usbOptions);
        }
        alert(`Started initialization for ${serials.length} USB device(s). Check progress below.`);
      }
    } catch (e) {
      alert('Failed to scan USB devices');
    }
    setUsbScanning(false);
  };

  const toggleOption = (key) => {
    setUsbOptions((prev) => ({ ...prev, [key]: !prev[key] }));
  };

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
        <div className="usb-init-wrapper" ref={usbMenuRef}>
          <button
            className="btn"
            onClick={() => !usbScanning && setUsbMenuOpen(!usbMenuOpen)}
            disabled={usbScanning}
          >
            {usbScanning ? 'Scanning USB...' : 'USB Init'}
          </button>
          {usbMenuOpen && (
            <div className="usb-init-menu">
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.enableWirelessAdb}
                  onChange={() => toggleOption('enableWirelessAdb')}
                />
                <span>Wireless ADB</span>
              </label>
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.updateApp}
                  onChange={() => toggleOption('updateApp')}
                />
                <span>Update App</span>
              </label>
              <label className="usb-init-option">
                <input
                  type="checkbox"
                  checked={usbOptions.updateContent}
                  onChange={() => toggleOption('updateContent')}
                />
                <span>Update Content</span>
              </label>
              <button
                className="btn btn-primary usb-init-start"
                onClick={handleUsbInit}
              >
                Start
              </button>
            </div>
          )}
        </div>
        <button
          className="btn"
          disabled={!hasAdbDevices}
          title={adbNoPlayer.length > 0 ? `${adbNoPlayer.length} device(s) without player` : 'Launch player on all ADB devices'}
          onClick={() => debounce('launchPlayer', async () => {
            const result = await launchPlayer();
            if (result.error && (!result.success || result.success.length === 0)) {
              alert(result.error);
            } else if (result.success) {
              alert(`Player launch command sent to ${result.success.length} device(s).`);
            }
          })}
        >
          Launch Player {adbNoPlayer.length > 0 && `(${adbNoPlayer.length})`}
        </button>
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
