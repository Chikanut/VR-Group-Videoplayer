import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getConfig, updateConfig } from '../api';

function generateId() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    const data = await getConfig();
    setConfig(data);
  };

  const handleSave = async () => {
    setError('');
    setSuccess('');
    setSaving(true);

    // Validate: no duplicate video names/paths
    const videos = config.requirementVideos || [];
    const names = videos.map((v) => v.name).filter(Boolean);
    const paths = videos.map((v) => v.localPath).filter(Boolean);
    if (new Set(names).size !== names.length) {
      setError('Duplicate video names found');
      setSaving(false);
      return;
    }
    if (new Set(paths).size !== paths.length) {
      setError('Duplicate video paths found');
      setSaving(false);
      return;
    }

    try {
      await updateConfig(config);
      setSuccess('Settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (e) {
      setError('Failed to save settings');
    }
    setSaving(false);
  };

  const updateField = (field, value) => {
    setConfig({ ...config, [field]: value });
  };

  const addVideo = () => {
    const videos = [...(config.requirementVideos || [])];
    videos.push({
      id: generateId(),
      name: '',
      localPath: '',
      devicePath: '',
      loop: false,
      videoType: '360',
    });
    updateField('requirementVideos', videos);
  };

  const removeVideo = (index) => {
    const videos = [...(config.requirementVideos || [])];
    videos.splice(index, 1);
    updateField('requirementVideos', videos);
  };

  const updateVideo = (index, field, value) => {
    const videos = [...(config.requirementVideos || [])];
    videos[index] = { ...videos[index], [field]: value };
    updateField('requirementVideos', videos);
  };

  if (!config) {
    return (
      <div className="settings-page">
        <p>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <button className="btn" onClick={() => navigate('/')}>
          Back
        </button>
        <h1>Settings</h1>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <section className="settings-section">
        <h2>APK Configuration</h2>
        <div className="form-group">
          <label>APK File Path (on server PC)</label>
          <input
            type="text"
            value={config.apkPath || ''}
            onChange={(e) => updateField('apkPath', e.target.value)}
            placeholder="/path/to/player.apk"
          />
        </div>
        <div className="form-group">
          <label>Package ID</label>
          <input
            type="text"
            value={config.packageId || ''}
            onChange={(e) => updateField('packageId', e.target.value)}
            placeholder="com.vrclassroom.player"
          />
        </div>
      </section>

      <section className="settings-section">
        <h2>Requirement Videos</h2>
        <div className="video-requirements-list">
          {(config.requirementVideos || []).map((video, idx) => (
            <div key={video.id || idx} className="video-requirement-row">
              <div className="video-req-fields">
                <div className="form-group">
                  <label>Name</label>
                  <input
                    type="text"
                    value={video.name || ''}
                    onChange={(e) => updateVideo(idx, 'name', e.target.value)}
                    placeholder="Lesson 01"
                  />
                </div>
                <div className="form-group">
                  <label>Local Path (on server PC)</label>
                  <input
                    type="text"
                    value={video.localPath || ''}
                    onChange={(e) => updateVideo(idx, 'localPath', e.target.value)}
                    placeholder="/path/to/lesson01.mp4"
                  />
                </div>
                <div className="form-group">
                  <label>Device Path (on Quest)</label>
                  <input
                    type="text"
                    value={video.devicePath || ''}
                    onChange={(e) => updateVideo(idx, 'devicePath', e.target.value)}
                    placeholder="/sdcard/VRClassroom/lesson01.mp4"
                  />
                </div>
                <div className="form-group form-group-small">
                  <label>Type</label>
                  <select
                    value={video.videoType || '360'}
                    onChange={(e) => updateVideo(idx, 'videoType', e.target.value)}
                  >
                    <option value="360">360</option>
                    <option value="2d">2D</option>
                  </select>
                </div>
                <div className="form-group form-group-small">
                  <label>Loop</label>
                  <input
                    type="checkbox"
                    checked={video.loop || false}
                    onChange={(e) => updateVideo(idx, 'loop', e.target.checked)}
                  />
                </div>
              </div>
              <button
                className="btn btn-danger btn-small"
                onClick={() => removeVideo(idx)}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
        <button className="btn" onClick={addVideo}>
          + Add Video
        </button>
      </section>

      <section className="settings-section">
        <h2>System Settings</h2>
        <div className="settings-grid">
          <div className="form-group">
            <label>Battery Warning Threshold (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={config.batteryThreshold || 20}
              onChange={(e) => updateField('batteryThreshold', parseInt(e.target.value) || 0)}
            />
          </div>
          <div className="form-group">
            <label>Network Scan Interval (seconds)</label>
            <input
              type="number"
              min="5"
              max="300"
              value={config.scanInterval || 30}
              onChange={(e) => updateField('scanInterval', parseInt(e.target.value) || 30)}
            />
          </div>
          <div className="form-group">
            <label>Network Subnet (auto-detected if empty)</label>
            <input
              type="text"
              value={config.networkSubnet || ''}
              onChange={(e) => updateField('networkSubnet', e.target.value)}
              placeholder="192.168.1"
            />
          </div>
          <div className="form-group">
            <label>Player HTTP Port</label>
            <input
              type="number"
              value={config.playerPort || 8080}
              onChange={(e) => updateField('playerPort', parseInt(e.target.value) || 8080)}
            />
          </div>
          <div className="form-group">
            <label>Device Offline Timeout (seconds)</label>
            <input
              type="number"
              min="10"
              max="300"
              value={config.deviceOfflineTimeout || 30}
              onChange={(e) => updateField('deviceOfflineTimeout', parseInt(e.target.value) || 30)}
            />
          </div>
          <div className="form-group">
            <label>Status Poll Interval (seconds)</label>
            <input
              type="number"
              min="1"
              max="60"
              value={config.statusPollInterval || 5}
              onChange={(e) => updateField('statusPollInterval', parseInt(e.target.value) || 5)}
            />
          </div>
          <div className="form-group">
            <label>Update Concurrency</label>
            <input
              type="number"
              min="1"
              max="20"
              value={config.updateConcurrency || 5}
              onChange={(e) => updateField('updateConcurrency', parseInt(e.target.value) || 5)}
            />
          </div>
        </div>
      </section>
    </div>
  );
}
