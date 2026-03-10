import React, { useEffect, useRef, useState } from 'react';
import useDeviceStore from '../store/deviceStore';
import TopControlPanel from './TopControlPanel';
import DeviceGrid from './DeviceGrid';
import DeviceDialog from './DeviceDialog';
import VideoSelector from './VideoSelector';
import ConnectionButton from './ConnectionButton';
import { useI18n } from '../i18n';

export default function Layout() {
  const { t } = useI18n();
  const { connected, loading } = useDeviceStore();
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [videoSelectorOpen, setVideoSelectorOpen] = useState(false);
  const [videoSelectorDeviceIds, setVideoSelectorDeviceIds] = useState([]);
  const [topPanelHeight, setTopPanelHeight] = useState(80);
  const topPanelRef = useRef(null);

  useEffect(() => {
    if (!topPanelRef.current) return;

    const node = topPanelRef.current;
    const updateHeight = () => {
      setTopPanelHeight(node.offsetHeight || 80);
    };

    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(node);
    window.addEventListener('resize', updateHeight);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', updateHeight);
    };
  }, []);

  const handlePlayAll = () => {
    setVideoSelectorDeviceIds([]);
    setVideoSelectorOpen(true);
  };

  const handlePlaySingle = (deviceId) => {
    setVideoSelectorDeviceIds([deviceId]);
    setVideoSelectorOpen(true);
  };

  return (
    <div className="app-container">
      {!connected && (
        <div className="connection-banner">
          {t('Connection lost. Reconnecting...')}
        </div>
      )}
      <TopControlPanel
        onPlayAll={handlePlayAll}
        panelRef={topPanelRef}
      />
      <main className="main-content" style={{ paddingTop: `${topPanelHeight + 20}px` }}>
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>{t('Connecting to server...')}</p>
          </div>
        ) : (
          <DeviceGrid
            onSelectDevice={setSelectedDeviceId}
          />
        )}
      </main>
      {selectedDeviceId && (
        <DeviceDialog
          deviceId={selectedDeviceId}
          onClose={() => setSelectedDeviceId(null)}
          onPlayVideo={() => handlePlaySingle(selectedDeviceId)}
        />
      )}
      {videoSelectorOpen && (
        <VideoSelector
          targetDeviceIds={videoSelectorDeviceIds}
          onClose={() => setVideoSelectorOpen(false)}
        />
      )}
      <ConnectionButton />
    </div>
  );
}
