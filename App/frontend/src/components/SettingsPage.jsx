import React, { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getConfig, updateConfig, uploadLocalFile } from '../api';

function generateId() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

function getDevicePath(video) {
  const localPath = (video.localPath || '').trim();
  if (!localPath) return '/sdcard/Movies/<file-name>';
  const parts = localPath.split(/[/\\]/);
  const filename = parts[parts.length - 1] || '<file-name>';
  return `/sdcard/Movies/${filename}`;
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const apkPickerRef = useRef(null);
  const videoPickerRefs = useRef({});

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

  const handleApkPick = async (event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;
    const result = await uploadLocalFile(selected);
    if (result?.ok && result?.path) {
      updateField('apkPath', result.path);
    } else {
      setError('APK upload failed');
    }
    event.target.value = '';
  };

  const handleVideoPick = async (index, event) => {
    const selected = event.target.files?.[0];
    if (!selected) return;
    const result = await uploadLocalFile(selected);
    if (result?.ok && result?.path) {
      updateVideo(index, 'localPath', result.path);
    } else {
      setError('Video upload failed');
    }
    event.target.value = '';
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
        <button className="btn" onClick={() => navigate('/')}>Back</button>
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
          <label>APK File (upload from your PC)</label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input type="text" value={config.apkPath || ''} readOnly placeholder="Select APK file" />
            <button className="btn" onClick={() => apkPickerRef.current?.click()}>Choose file</button>
          </div>
          <input
            ref={apkPickerRef}
            type="file"
            accept=".apk"
            onChange={handleApkPick}
            style={{ display: 'none' }}
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
                  <label>Video file (upload from your PC)</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input type="text" value={video.localPath || ''} readOnly placeholder="Select video file" />
                    <button
                      className="btn"
                      onClick={() => videoPickerRefs.current[idx]?.click()}
                    >
                      Choose file
                    </button>
                  </div>
                  <input
                    ref={(el) => { videoPickerRefs.current[idx] = el; }}
                    type="file"
                    accept="video/*"
                    onChange={(e) => handleVideoPick(idx, e)}
                    style={{ display: 'none' }}
                  />
                </div>
                <div className="form-group">
                  <label>Device Path (auto)</label>
                  <input type="text" value={getDevicePath(video)} readOnly />
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
              <button className="btn btn-danger btn-small" onClick={() => removeVideo(idx)}>
                Remove
              </button>
            </div>
          ))}
        </div>
        <button className="btn" onClick={addVideo}>+ Add Video</button>
      </section>

      <section className="settings-section">
        <h2>System Settings</h2>
        <div className="settings-grid">
          <div className="form-group">
            <label>Battery Warning Threshold (%)</label>
            <input type="number" min="0" max="100" value={config.batteryThreshold || 20}
              onChange={(e) => updateField('batteryThreshold', parseInt(e.target.value) || 0)} />
          </div>
          <div className="form-group">
            <label>Network Scan Interval (seconds)</label>
            <input type="number" min="5" max="300" value={config.scanInterval || 30}
              onChange={(e) => updateField('scanInterval', parseInt(e.target.value) || 30)} />
          </div>
          <div className="form-group">
            <label>Network Subnet (auto-detected if empty)</label>
            <input type="text" value={config.networkSubnet || ''}
              onChange={(e) => updateField('networkSubnet', e.target.value)} placeholder="192.168.1" />
          </div>
          <div className="form-group">
            <label>Player HTTP Port</label>
            <input type="number" value={config.playerPort || 8080}
              onChange={(e) => updateField('playerPort', parseInt(e.target.value) || 8080)} />
          </div>
          <div className="form-group">
            <label>Device Offline Timeout (seconds)</label>
            <input type="number" min="10" max="300" value={config.deviceOfflineTimeout || 30}
              onChange={(e) => updateField('deviceOfflineTimeout', parseInt(e.target.value) || 30)} />
          </div>
          <div className="form-group">
            <label>Status Poll Interval (seconds)</label>
            <input type="number" min="1" max="60" value={config.statusPollInterval || 5}
              onChange={(e) => updateField('statusPollInterval', parseInt(e.target.value) || 5)} />
          </div>
          <div className="form-group">
            <label>Update Concurrency</label>
            <input type="number" min="1" max="20" value={config.updateConcurrency || 5}
              onChange={(e) => updateField('updateConcurrency', parseInt(e.target.value) || 5)} />
          </div>
        </div>
      </section>
    </div>
  );
}
