import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { useI18n } from '../i18n';

export default function ConnectionButton() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [mobileAppUrl, setMobileAppUrl] = useState('');
  const [playerAppUrl, setPlayerAppUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('server');

  const fetchServerInfo = async () => {
    setLoading(true);
    try {
      const [serverRes, configRes] = await Promise.all([
        fetch('/api/server-info'),
        fetch('/api/config'),
      ]);
      const info = await serverRes.json();
      const config = await configRes.json();
      setServerUrl(info.url || `http://${info.ip}:${info.port}`);
      setMobileAppUrl(config.mobileAppUrl || '');
      setPlayerAppUrl(config.playerAppUrl || '');
    } catch {
      setServerUrl(window.location.origin);
      setMobileAppUrl('');
      setPlayerAppUrl('');
    }
    setLoading(false);
  };

  const handleOpen = () => {
    setOpen(true);
    setActiveTab('server');
    fetchServerInfo();
  };

  const qrValue = activeTab === 'mobile'
    ? (mobileAppUrl || 'https://example.com/control-panel-app')
    : activeTab === 'player'
      ? (playerAppUrl || 'https://example.com/player-app')
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
                      ? (mobileAppUrl || t('Set Phone Control App Link in Settings'))
                      : activeTab === 'player'
                        ? (playerAppUrl || t('Set Player App Link in Settings'))
                        : serverUrl}
                  </p>

                  {activeTab === 'server' ? (
                    <p className="connection-hint">
                      {t('Scan QR code with your phone camera or enter the URL in a browser. Make sure both devices are on the same network.')}
                    </p>
                  ) : activeTab === 'mobile' ? (
                    <p className="connection-hint">
                      {t('Open this tab to download the mobile control app. If the link is empty, add Phone Control App Link in Settings first.')}
                    </p>
                  ) : (
                    <p className="connection-hint">
                      {t('Open this tab to download the player app for the headset. If the link is empty, add Player App Link in Settings first.')}
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
