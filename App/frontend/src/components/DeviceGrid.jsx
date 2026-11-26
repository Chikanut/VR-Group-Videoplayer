import React from 'react';
import useDeviceStore from '../store/deviceStore';
import DeviceTile from './DeviceTile';
import { useI18n } from '../i18n';

export default function DeviceGrid({ onSelectDevice }) {
  const devices = useDeviceStore((s) => s.getDeviceList());
  const selectedCount = useDeviceStore((s) => devices.filter((d) => s.selectedIds[d.deviceId]).length);
  const selectAll = useDeviceStore((s) => s.selectAll);
  const clearSelection = useDeviceStore((s) => s.clearSelection);
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
    <>
    <div className="grid-toolbar">
      <button className="btn-small" onClick={selectAll} disabled={selectedCount === devices.length}>
        {t('Select all')}
      </button>
      <button className="btn-small" onClick={clearSelection} disabled={selectedCount === 0}>
        {t('Clear selection')}
      </button>
      <span className="device-count">{t('Selected: {count}', { count: `${selectedCount} / ${devices.length}` })}</span>
    </div>
    <div className="device-grid">
      {devices.map((device) => (
        <DeviceTile
          key={device.deviceId}
          device={device}
          onClick={() => onSelectDevice(device.deviceId)}
        />
      ))}
    </div>
    </>
  );
}
