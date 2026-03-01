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
  const [videoSelectorIgnoreRequirements, setVideoSelectorIgnoreRequirements] = useState(false);

  const handlePlayAll = () => {
    setVideoSelectorDeviceIds([]);
    setVideoSelectorIgnoreRequirements(false);
    setVideoSelectorOpen(true);
  };

  const handlePlaySingle = (deviceId, ignoreRequirements = false) => {
    setVideoSelectorDeviceIds([deviceId]);
    setVideoSelectorIgnoreRequirements(ignoreRequirements);
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
          onPlayVideo={(ignoreRequirements) => handlePlaySingle(selectedDeviceId, ignoreRequirements)}
        />
      )}
      {videoSelectorOpen && (
        <VideoSelector
          targetDeviceIds={videoSelectorDeviceIds}
          ignoreRequirements={videoSelectorIgnoreRequirements}
          onClose={() => setVideoSelectorOpen(false)}
        />
      )}
    </div>
  );
}
