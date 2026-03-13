import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { useI18n } from '../i18n';

const RELEASES_URL = 'https://github.com/Chikanut/VR-Group-Videoplayer/releases';

export default function ConnectionButton() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('server');

  const fetchServerInfo = async () => {
    setLoading(true);
    try {
      const serverRes = await fetch('/api/server-info');
      const info = await serverRes.json();
      setServerUrl(info.url || `http://${info.ip}:${info.port}`);
    } catch {
      setServerUrl(window.location.origin);
    }
    setLoading(false);
  };

  const handleOpen = () => {
    setOpen(true);
    setActiveTab('server');
    fetchServerInfo();
  };

  const qrValue = activeTab === 'mobile'
    ? RELEASES_URL
    : activeTab === 'player'
      ? RELEASES_URL
      : (serverUrl || 'http://localhost:8000');

  return (
    <>
      <button className="connection-btn" onClick={handleOpen} title={t('Show connection QR codes')}>
        {t('Connection')}
      </button>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal connection-modal" onClick={(event) => event.stopPropagation()}>
            <div className="dialog-header">
              <h2 className="dialog-title" style={{ cursor: 'default' }}>{t('Connection Options')}</h2>
              <button className="btn-close" onClick={() => setOpen(false)}>&times;</button>
            </div>

            <div className="connection-qr-content">
              {loading ? (
                <div className="loading-state" style={{ minHeight: 200 }}>
                  <div className="spinner" />
                  <p>{t('Detecting network...')}</p>
                </div>
              ) : (
                <>
                  <div className="connection-tabs">
                    <button
                      type="button"
                      className={`connection-tab ${activeTab === 'server' ? 'active' : ''}`}
                      onClick={() => setActiveTab('server')}
                    >
                      {t('Current Server')}
                    </button>
                    <button
                      type="button"
                      className={`connection-tab ${activeTab === 'mobile' ? 'active' : ''}`}
                      onClick={() => setActiveTab('mobile')}
                    >
                      {t('Phone App')}
                    </button>
                    <button
                      type="button"
                      className={`connection-tab ${activeTab === 'player' ? 'active' : ''}`}
                      onClick={() => setActiveTab('player')}
                    >
                      {t('Player App')}
                    </button>
                  </div>

                  <div className="qr-container">
                    <QRCodeSVG
                      value={qrValue}
                      size={240}
                      level="M"
                      bgColor="#ffffff"
                      fgColor="#000000"
                    />
                  </div>

                  <p className="connection-url">
                    {activeTab === 'mobile'
                      ? RELEASES_URL
                      : activeTab === 'player'
                        ? RELEASES_URL
                        : serverUrl}
                  </p>

                  {activeTab === 'server' ? (
                    <p className="connection-hint">
                      {t('Scan QR code with your phone camera or enter the URL in a browser. Make sure both devices are on the same network.')}
                    </p>
                  ) : activeTab === 'mobile' ? (
                    <p className="connection-hint">
                      {t('Open the releases page to download the mobile control app APK.')}
                    </p>
                  ) : (
                    <p className="connection-hint">
                      {t('Open the releases page to download the player APK and related builds.')}
                    </p>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
