import React, { useRef, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useDeviceStore from '../store/deviceStore';
import { playbackCommand, updateAllDevices, getUsbDevices, updateUsbDevice } from '../api';

export default function TopControlPanel({ onPlayAll }) {
  const navigate = useNavigate();
  const config = useDeviceStore((s) => s.config);
  const devices = useDeviceStore((s) => s.getDeviceList());
  const onlineDevices = devices.filter((d) => d.online);
  const hasOnline = onlineDevices.length > 0;
  const ignoreReq = config?.ignoreRequirements || false;
  const hasCommandTargets = onlineDevices.some((d) => d.playerConnected || (ignoreReq && d.adbConnected));
  const debounceRef = useRef({});
  const [usbScanning, setUsbScanning] = useState(false);

  const debounce = useCallback((key, fn) => {
    if (debounceRef.current[key]) return;
    debounceRef.current[key] = true;
    fn();
    setTimeout(() => { debounceRef.current[key] = false; }, 1000);
  }, []);

  const needsUpdate = onlineDevices.filter(
    (d) => d.adbConnected && d.requirementsMet === false
  );

  const handleUsbInit = async () => {
    setUsbScanning(true);
    try {
      const data = await getUsbDevices();
      const serials = data.devices || [];
      if (serials.length === 0) {
        alert('No USB devices found. Connect a Quest headset via USB cable.');
      } else {
        for (const serial of serials) {
          await updateUsbDevice(serial);
        }
        alert(`Started initialization for ${serials.length} USB device(s). Check progress below.`);
      }
    } catch (e) {
      alert('Failed to scan USB devices');
    }
    setUsbScanning(false);
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
        <button
          className="btn"
          onClick={handleUsbInit}
          disabled={usbScanning}
        >
          {usbScanning ? 'Scanning USB...' : 'USB Init'}
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
