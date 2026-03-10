import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';

export default function ConnectionButton() {
  const [open, setOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [apkDownloadUrl, setApkDownloadUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('web');

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
      setApkDownloadUrl(config.apkDownloadUrl || '');
    } catch (e) {
      setServerUrl(window.location.origin);
      setApkDownloadUrl('');
    }
    setLoading(false);
  };

  const handleOpen = () => {
    setOpen(true);
    setActiveTab('web');
    fetchServerInfo();
  };

  const handleClose = () => {
    setOpen(false);
  };

  return (
    <>
      <button
        className="connection-btn"
        onClick={handleOpen}
        title="Show QR code for phone connection"
      >
        CONNECTION
      </button>

      {open && (
        <div className="modal-overlay" onClick={handleClose}>
          <div className="modal connection-modal" onClick={e => e.stopPropagation()}>
            <div className="dialog-header">
              <h2 className="dialog-title" style={{ cursor: 'default' }}>Connect from Phone</h2>
              <button className="btn-close" onClick={handleClose}>&times;</button>
            </div>
            <div className="connection-qr-content">
              {loading ? (
                <div className="loading-state" style={{ minHeight: 200 }}>
                  <div className="spinner" />
                  <p>Detecting network...</p>
                </div>
              ) : (
                <>
                  <div className="connection-tabs">
                    <button
                      type="button"
                      className={`connection-tab ${activeTab === 'web' ? 'active' : ''}`}
                      onClick={() => setActiveTab('web')}
                    >
                      Web Control
                    </button>
                    <button
                      type="button"
                      className={`connection-tab ${activeTab === 'apk' ? 'active' : ''}`}
                      onClick={() => setActiveTab('apk')}
                    >
                      Android APK
                    </button>
                  </div>
                  <div className="qr-container">
                    <QRCodeSVG
                      value={activeTab === 'apk' ? (apkDownloadUrl || 'https://example.com/player.apk') : (serverUrl || 'http://localhost:8000')}
                      size={240}
                      level="M"
                      bgColor="#ffffff"
                      fgColor="#000000"
                    />
                  </div>
                  <p className="connection-url">{activeTab === 'apk' ? (apkDownloadUrl || 'Set APK download URL in Settings') : serverUrl}</p>
                  {activeTab === 'web' ? (
                    <p className="connection-hint">
                      Scan QR code with your phone camera or enter the URL in a browser.
                      Make sure both devices are on the same network.
                    </p>
                  ) : (
                    <p className="connection-hint">
                      Scan QR code to download Android APK. If URL is not configured,
                      open Settings and fill in APK Download URL.
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
