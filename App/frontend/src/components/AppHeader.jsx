import React, { useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { getUpdates } from '../api';
import { useI18n } from '../i18n';
import Icon from './Icons';
import packageJson from '../../package.json';

// One check per page load: the server caches the GitHub answer, the banner only needs "is there a newer one".
let updateInfoPromise = null;

export function useUpdateInfo() {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    updateInfoPromise = updateInfoPromise || getUpdates().catch(() => null);
    let alive = true;
    updateInfoPromise.then((data) => alive && setInfo(data));
    return () => { alive = false; };
  }, []);
  return info;
}

export default function AppHeader({ sticky = false, children }) {
  const { t } = useI18n();
  const updates = useUpdateInfo();
  const latest = updates?.latest?.version;

  return (
    <div className={`app-bar${sticky ? ' sticky' : ''}`}>
      <Link to="/" className="brand">
        <span className="brand-mark"><Icon name="logo" size={20} /></span>
        <span className="brand-text">
          <span className="brand-title">VR Classroom</span>
          <span className="brand-sub">{t('Control panel')} · v{packageJson.version}</span>
        </span>
      </Link>
      <nav className="app-nav" aria-label={t('Sections')}>
        <NavLink to="/" end>{t('Dashboard')}</NavLink>
        <NavLink to="/settings">{t('Settings')}</NavLink>
      </nav>
      <div className="app-bar-spacer" />
      {updates?.panelUpdateAvailable && (
        <Link to="/settings#updates" className="update-banner">
          <Icon name="download" />
          {t('Version {version} is available', { version: latest })} <strong>{t('Update')}</strong>
        </Link>
      )}
      {children}
    </div>
  );
}
