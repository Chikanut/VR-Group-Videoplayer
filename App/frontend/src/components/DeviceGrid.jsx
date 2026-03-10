import React from 'react';
import useDeviceStore from '../store/deviceStore';
import DeviceTile from './DeviceTile';
import { useI18n } from '../i18n';

export default function DeviceGrid({ onSelectDevice }) {
  const devices = useDeviceStore((s) => s.getDeviceList());
  const { t } = useI18n();

  if (devices.length === 0) {
    return (
      <div className="empty-state">
        <h2>{t('No devices found')}</h2>
        <p>{t('Scanning network...')}</p>
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
