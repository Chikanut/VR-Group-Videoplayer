import React from 'react';
import useDeviceStore from '../store/deviceStore';
import DeviceTile from './DeviceTile';

export default function DeviceGrid({ onSelectDevice }) {
  const devices = useDeviceStore((s) => s.getDeviceList());

  if (devices.length === 0) {
    return (
      <div className="empty-state">
        <h2>No devices found</h2>
        <p>Scanning network...</p>
      </div>
    );
  }

  return (
    <div className="device-grid">
      {devices.map((device) => (
        <DeviceTile
          key={device.deviceId}
          device={device}
          onClick={() => onSelectDevice(device.deviceId)}
        />
      ))}
    </div>
  );
}
