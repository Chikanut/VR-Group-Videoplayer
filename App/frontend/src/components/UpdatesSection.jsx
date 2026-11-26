import React, { useEffect, useRef, useState } from 'react';
import { getUpdates, startUpdate } from '../api';
import { useI18n } from '../i18n';
import useDeviceStore from '../store/deviceStore';
import Icon from './Icons';

function formatMb(bytes) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function jobText(job, t) {
  if (!job) return '';
  if (job.stage === 'downloading') {
    const total = job.total > 0 ? ` / ${formatMb(job.total)}` : '';
    return `${t('Downloading')} ${formatMb(job.downloaded)}${total}`;
  }
  if (job.stage === 'failed') return `${t('Update failed')}: ${job.error}`;
  const sent = job.sent != null ? `: ${job.sent}` : '';
  return `${t(job.message || job.stage)}${sent}`;
}

const isOlder = (a, b) => a.localeCompare(b, undefined, { numeric: true }) < 0;

function inline(text) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`')) return <code key={i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

// Release notes are bilingual markdown ("## English" / "## Українська"): show the UI language's half.
// shortcut: headings, bullets, bold and code only, which is all the release notes use.
function ReleaseNotes({ notes, language }) {
  const halves = notes.split(/^## /m).filter((s) => s.trim());
  const half = halves.length > 1
    ? halves.find((s) => (language === 'uk') === /Українськ/.test(s.split('\n')[0])) || halves[0]
    : notes;
  const lines = halves.length > 1 ? half.split('\n').slice(1) : half.split('\n');
  const blocks = [];
  let list = null;
  lines.forEach((raw) => {
    const line = raw.trim();
    if (/^[-*] /.test(line)) {
      if (!list) blocks.push(list = []);
      list.push(line.slice(2));
      return;
    }
    list = null;
    if (!line || line === '---') return;
    blocks.push(line.startsWith('#') ? { h: line.replace(/^#+\s*/, '') } : { p: line });
  });
  return (
    <div className="release-notes-body">
      {blocks.map((b, i) => (Array.isArray(b)
        ? <ul key={i}>{b.map((item, j) => <li key={j}>{inline(item)}</li>)}</ul>
        : b.h ? <h4 key={i}>{inline(b.h)}</h4> : <p key={i}>{inline(b.p)}</p>))}
    </div>
  );
}

export default function UpdatesSection({ checkUpdates, onToggleCheck }) {
  const { t, language } = useI18n();
  const devices = useDeviceStore((s) => s.getDeviceList());
  const [info, setInfo] = useState(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  const load = async (refresh) => {
    setChecking(refresh);
    try {
      setInfo(await getUpdates(refresh));
    } catch {
      setInfo(null);
    }
    setChecking(false);
  };

  useEffect(() => {
    load(false);
    return () => clearTimeout(pollRef.current);
  }, []);

  // While a download runs the server reports its progress; poll until it ends.
  const job = info?.job;
  const running = job && (job.stage === 'downloading' || job.stage === 'installing');
  useEffect(() => {
    if (!running) return undefined;
    pollRef.current = setTimeout(() => load(false), 1000);
    return () => clearTimeout(pollRef.current);
  }, [info]);

  const run = async (kind) => {
    setError('');
    try {
      const result = await startUpdate(kind);
      if (result.success === false) setError(t(result.error || 'Command failed'));
    } catch {
      setError(t('Command failed'));
    }
    load(false);
  };

  const latest = info?.latest;
  const versions = {};
  devices.forEach((device) => {
    const version = device.playerVersion || device.agentVersion;
    if (version) versions[version] = (versions[version] || 0) + 1;
  });
  const versionText = Object.entries(versions)
    .sort(([a], [b]) => b.localeCompare(a, undefined, { numeric: true }))
    .map(([version, count]) => `${count} × ${version}`)
    .join(' · ') || '—';
  const playersBehind = !!latest && Object.keys(versions).some((v) => isOlder(v, latest.version));

  return (
    <section id="updates" className="settings-section">
      <div className="section-head">
        <h2>{t('Updates from GitHub')}</h2>
        {info?.panelUpdateAvailable && (
          <span className="chip chip-info">{t('Available {version}', { version: latest.version })}</span>
        )}
        {latest && !info.panelUpdateAvailable && <span className="chip chip-ok">{t('Up to date')}</span>}
        <div className="app-bar-spacer" />
        <button className="btn" onClick={() => load(true)} disabled={checking}>
          <Icon name="sync" />
          {checking ? t('Checking...') : t('Check now')}
        </button>
      </div>

      {info?.error && <div className="alert alert-error">{t('No answer from GitHub')}: {info.error}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="update-cards">
        <div className="update-card">
          <span className="update-card-label">{t('Control panel')}</span>
          <span className="update-card-version">
            {info?.current || '—'}
            {info?.panelUpdateAvailable && <> → <em>{latest.version}</em></>}
          </span>
          {info?.panelCanSelfUpdate ? (
            <button
              className="btn btn-primary"
              disabled={!info?.panelUpdateAvailable || running}
              onClick={() => run('panel')}
            >
              <Icon name="download" />
              {t('Download and restart')}
            </button>
          ) : (
            latest && <a className="btn" href={latest.url} target="_blank" rel="noreferrer">{t('Open the release')}</a>
          )}
          {info?.panelHint && <span className="form-hint">{t(info.panelHint)}</span>}
        </div>
        <div className="update-card">
          <span className="update-card-label">{t('Player on the headsets')}</span>
          <span className="update-card-version">
            {versionText}
            {playersBehind && <> → <em>{latest.version}</em></>}
          </span>
          <button className="btn" disabled={!latest?.hasPlayer || !playersBehind || running} onClick={() => run('player')}>
            <Icon name="download" />
            {t('Update all headsets')}
          </button>
          <span className="form-hint">{t('Player update from GitHub hint')}</span>
        </div>
      </div>

      {job && (
        <div className={`alert ${job.stage === 'failed' ? 'alert-error' : 'alert-success'}`}>
          {jobText(job, t)}
          {job.stage === 'downloading' && job.total > 0 && (
            <div className="progress-bar" style={{ marginTop: 8 }}>
              <div className="progress-fill" style={{ width: `${(job.downloaded / job.total) * 100}%` }} />
            </div>
          )}
        </div>
      )}

      {latest && (
        <div className="release-notes">
          <strong>{t("What's new in {version}", { version: latest.version })}</strong>
          {latest.notes && <ReleaseNotes notes={latest.notes} language={language} />}
          <a href={latest.url} target="_blank" rel="noreferrer">{t('Open the release on GitHub')}</a>
        </div>
      )}

      <div className="toggle-row">
        <div className="toggle-row-text">
          <span>{t('Check for updates on start')}</span>
          <span className="form-hint">{t('Check for updates hint')}</span>
        </div>
        <button
          type="button"
          className="switch"
          role="switch"
          aria-checked={checkUpdates}
          aria-label={t('Check for updates on start')}
          onClick={() => onToggleCheck(!checkUpdates)}
        />
      </div>
    </section>
  );
}
