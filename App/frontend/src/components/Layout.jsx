import React, { useState } from 'react';
import useDeviceStore from '../store/deviceStore';
import TopControlPanel from './TopControlPanel';
import DeviceGrid from './DeviceGrid';
import DeviceDialog from './DeviceDialog';
import VideoSelector from './VideoSelector';

export default function Layout() {
  const { connected, loading } = useDeviceStore();
  const [selectedDeviceId, setSelectedDeviceId] = useState(null);
  const [videoSelectorOpen, setVideoSelectorOpen] = useState(false);
  const [videoSelectorDeviceIds, setVideoSelectorDeviceIds] = useState([]);

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
          Connection lost. Reconnecting...
        </div>
      )}
      <TopControlPanel
        onPlayAll={handlePlayAll}
      />
      <main className="main-content">
        {loading ? (
          <div className="loading-state">
            <div className="spinner" />
            <p>Connecting to server...</p>
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
    </div>
  );
}
