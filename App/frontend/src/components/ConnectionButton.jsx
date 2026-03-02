import React, { useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';

export default function ConnectionButton() {
  const [open, setOpen] = useState(false);
  const [serverUrl, setServerUrl] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchServerInfo = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/server-info');
      const info = await res.json();
      setServerUrl(info.url || `http://${info.ip}:${info.port}`);
    } catch (e) {
      setServerUrl(window.location.origin);
    }
    setLoading(false);
  };

  const handleOpen = () => {
    setOpen(true);
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
                  <div className="qr-container">
                    <QRCodeSVG
                      value={serverUrl || 'http://localhost:8000'}
                      size={240}
                      level="M"
                      bgColor="#ffffff"
                      fgColor="#000000"
                    />
                  </div>
                  <p className="connection-url">{serverUrl}</p>
                  <p className="connection-hint">
                    Scan QR code with your phone camera or enter the URL in a browser.
                    Make sure both devices are on the same network.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
