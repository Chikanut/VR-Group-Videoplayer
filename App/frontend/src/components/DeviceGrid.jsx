import React, { useState } from 'react';
import useDeviceStore from '../store/deviceStore';
import DeviceTile, { needsAttention } from './DeviceTile';
import { useI18n } from '../i18n';

const FILTERS = {
  all: () => true,
  online: (device) => device.online,
  problems: needsAttention,
  offline: (device) => !device.online,
};

export default function DeviceGrid({ onSelectDevice }) {
  const devices = useDeviceStore((s) => s.getDeviceList());
  const selectedIds = useDeviceStore((s) => s.selectedIds);
  const selectAll = useDeviceStore((s) => s.selectAll);
  const clearSelection = useDeviceStore((s) => s.clearSelection);
  const { t } = useI18n();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');

  if (devices.length === 0) {
    return (
      <div className="empty-state">
        <h2>{t('No devices found')}</h2>
        <p>{t('Scanning network...')}</p>
      </div>
    );
  }

  const count = (key) => devices.filter(FILTERS[key]).length;
  const selectedCount = devices.filter((d) => selectedIds[d.deviceId]).length;
  const allSelected = selectedCount === devices.length;
  const playing = devices.filter((d) => d.online && d.playbackState === 'playing').length;
  const contentReady = devices.filter((d) => d.online && d.requirementsMet === true).length;
  const needle = query.trim().toLowerCase();
  const shown = devices.filter(FILTERS[filter]).filter((d) => !needle
    || `${d.name} ${d.deviceId} ${d.ip}`.toLowerCase().includes(needle));

  return (
    <>
      <section className="stats-row" aria-label={t('Class status')}>
        <div className="stat">
          <span className="group-label">{t('Online')}</span>
          <span className="stat-value">{count('online')} <small>/ {devices.length}</small></span>
        </div>
        <div className="stat stat-ok">
          <span className="group-label">{t('Playing')}</span>
          <span className="stat-value">{playing}</span>
        </div>
        <div className={`stat${count('problems') ? ' stat-warn' : ''}`}>
          <span className="group-label">{t('Need attention')}</span>
          <span className="stat-value">{count('problems')}</span>
        </div>
        <div className="stat">
          <span className="group-label">{t('Content')}</span>
          <span className="stat-value">{contentReady} <small>{t('ready')}</small></span>
        </div>
      </section>

      <div className="grid-toolbar">
        <h2 className="grid-title">{t('Headsets')}</h2>
        <div className="seg" role="group" aria-label={t('Filter')}>
          {[['all', 'All'], ['online', 'Online'], ['problems', 'Problems'], ['offline', 'Offline']].map(([key, text]) => (
            <button
              key={key}
              type="button"
              className={filter === key ? 'on' : ''}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {t(text)} {count(key)}
            </button>
          ))}
        </div>
        <div className="app-bar-spacer" />
        <label className="check-label">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={() => (allSelected ? clearSelection() : selectAll())}
          />
          {selectedCount > 0 && !allSelected
            ? t('Selected: {count}', { count: `${selectedCount} / ${devices.length}` })
            : t('Select all')}
        </label>
        <input
          type="search"
          className="search-input"
          aria-label={t('Search by number or IP')}
          placeholder={t('Search by number or IP')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>

      <div className="device-grid">
        {shown.map((device) => (
          <DeviceTile
            key={device.deviceId}
            device={device}
            onClick={() => onSelectDevice(device.deviceId)}
          />
        ))}
      </div>
      {shown.length === 0 && <p className="device-count">{t('No headsets match the filter')}</p>}
    </>
  );
}
