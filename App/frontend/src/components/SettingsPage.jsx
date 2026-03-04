import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getConfig, updateConfig } from '../api';
import FilePicker from './FilePicker';

function generateId() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

function createDefaultAdvancedSettings() {
  return {
    overrideTransformSettings: false,
    overrideMaterialSettings: false,
    transformSettings: {
      localPosition: { x: 0, y: 0, z: 0 },
      localRotation: { x: 0, y: 0, z: 0 },
      localScale: { x: 1, y: 1, z: 1 },
    },
    materialSettings: {
      tint: { r: 1, g: 1, b: 1, a: 1 },
      brightness: 1,
      textureTiling: { x: 1, y: 1 },
      textureOffset: { x: 0, y: 0 },
    },
  };
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [filePicker, setFilePicker] = useState(null); // { target, filter, title }

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
      loop: false,
      videoType: '360',
      advancedSettings: createDefaultAdvancedSettings(),
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

  const updateVideoAdvancedSetting = (index, path, value) => {
    const videos = [...(config.requirementVideos || [])];
    const video = { ...videos[index] };
    const advancedSettings = {
      ...createDefaultAdvancedSettings(),
      ...(video.advancedSettings || {}),
      transformSettings: {
        ...createDefaultAdvancedSettings().transformSettings,
        ...(video.advancedSettings?.transformSettings || {}),
        localPosition: {
          ...createDefaultAdvancedSettings().transformSettings.localPosition,
          ...(video.advancedSettings?.transformSettings?.localPosition || {}),
        },
        localRotation: {
          ...createDefaultAdvancedSettings().transformSettings.localRotation,
          ...(video.advancedSettings?.transformSettings?.localRotation || {}),
        },
        localScale: {
          ...createDefaultAdvancedSettings().transformSettings.localScale,
          ...(video.advancedSettings?.transformSettings?.localScale || {}),
        },
      },
      materialSettings: {
        ...createDefaultAdvancedSettings().materialSettings,
        ...(video.advancedSettings?.materialSettings || {}),
        tint: {
          ...createDefaultAdvancedSettings().materialSettings.tint,
          ...(video.advancedSettings?.materialSettings?.tint || {}),
        },
        textureTiling: {
          ...createDefaultAdvancedSettings().materialSettings.textureTiling,
          ...(video.advancedSettings?.materialSettings?.textureTiling || {}),
        },
        textureOffset: {
          ...createDefaultAdvancedSettings().materialSettings.textureOffset,
          ...(video.advancedSettings?.materialSettings?.textureOffset || {}),
        },
      },
    };

    let node = advancedSettings;
    for (let i = 0; i < path.length - 1; i += 1) {
      node[path[i]] = { ...node[path[i]] };
      node = node[path[i]];
    }
    node[path[path.length - 1]] = value;

    video.advancedSettings = advancedSettings;
    videos[index] = video;
    updateField('requirementVideos', videos);
  };

  const openFilePicker = (target, filter, title) => {
    setFilePicker({ target, filter, title });
  };

  const handleFileSelected = (path) => {
    const { target } = filePicker;
    if (target === 'apkPath') {
      updateField('apkPath', path);
    } else if (target.startsWith('video_')) {
      const idx = parseInt(target.split('_')[1]);
      updateVideo(idx, 'localPath', path);
      const videos = config.requirementVideos || [];
      if (videos[idx] && !videos[idx].name) {
        const name = path.split(/[/\\]/).pop().replace(/\.[^.]+$/, '');
        updateVideo(idx, 'name', name);
      }
    }
    setFilePicker(null);
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
          <div className="input-with-button">
            <input
              type="text"
              value={config.apkPath || ''}
              readOnly
              placeholder="Click Browse to select APK file"
            />
            <button
              className="btn btn-small"
              onClick={() => openFilePicker('apkPath', '.apk', 'Select APK File')}
            >
              Browse
            </button>
          </div>
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
        <p className="settings-note">
          Videos are automatically saved to /sdcard/Movies/ on the device.
        </p>
        <div className="video-requirements-list">
          {(config.requirementVideos || []).map((video, idx) => {
            const advancedSettings = {
              ...createDefaultAdvancedSettings(),
              ...(video.advancedSettings || {}),
              transformSettings: {
                ...createDefaultAdvancedSettings().transformSettings,
                ...(video.advancedSettings?.transformSettings || {}),
                localPosition: {
                  ...createDefaultAdvancedSettings().transformSettings.localPosition,
                  ...(video.advancedSettings?.transformSettings?.localPosition || {}),
                },
                localRotation: {
                  ...createDefaultAdvancedSettings().transformSettings.localRotation,
                  ...(video.advancedSettings?.transformSettings?.localRotation || {}),
                },
                localScale: {
                  ...createDefaultAdvancedSettings().transformSettings.localScale,
                  ...(video.advancedSettings?.transformSettings?.localScale || {}),
                },
              },
              materialSettings: {
                ...createDefaultAdvancedSettings().materialSettings,
                ...(video.advancedSettings?.materialSettings || {}),
                tint: {
                  ...createDefaultAdvancedSettings().materialSettings.tint,
                  ...(video.advancedSettings?.materialSettings?.tint || {}),
                },
                textureTiling: {
                  ...createDefaultAdvancedSettings().materialSettings.textureTiling,
                  ...(video.advancedSettings?.materialSettings?.textureTiling || {}),
                },
                textureOffset: {
                  ...createDefaultAdvancedSettings().materialSettings.textureOffset,
                  ...(video.advancedSettings?.materialSettings?.textureOffset || {}),
                },
              },
            };

            return (
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
                    <label>Source File (on server PC)</label>
                    <div className="input-with-button">
                      <input
                        type="text"
                        value={video.localPath || ''}
                        readOnly
                        placeholder="Click Browse to select video"
                      />
                      <button
                        className="btn btn-small"
                        onClick={() => openFilePicker(`video_${idx}`, '.mp4,.mkv,.avi,.mov,.webm', 'Select Video File')}
                      >
                        Browse
                      </button>
                    </div>
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

                  <details className="form-group" style={{ width: '100%' }}>
                    <summary style={{ cursor: 'pointer', fontWeight: 600 }}>Advanced Settings</summary>

                    <div className="form-group" style={{ marginTop: 12 }}>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={advancedSettings.overrideTransformSettings}
                          onChange={(e) =>
                            updateVideoAdvancedSetting(idx, ['overrideTransformSettings'], e.target.checked)
                          }
                        />
                        <span>Override Transform Settings</span>
                      </label>
                    </div>

                    {advancedSettings.overrideTransformSettings && (
                      <>
                        <div className="settings-grid">
                          <div className="form-group">
                            <label>Position X</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localPosition.x}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localPosition', 'x'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Position Y</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localPosition.y}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localPosition', 'y'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Position Z</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localPosition.z}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localPosition', 'z'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Rotation X</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localRotation.x}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localRotation', 'x'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Rotation Y</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localRotation.y}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localRotation', 'y'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Rotation Z</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localRotation.z}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localRotation', 'z'], parseFloat(e.target.value) || 0)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Scale X</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localScale.x}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localScale', 'x'], parseFloat(e.target.value) || 1)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Scale Y</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localScale.y}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localScale', 'y'], parseFloat(e.target.value) || 1)}
                            />
                          </div>
                          <div className="form-group">
                            <label>Scale Z</label>
                            <input
                              type="number"
                              step="0.01"
                              value={advancedSettings.transformSettings.localScale.z}
                              onChange={(e) => updateVideoAdvancedSetting(idx, ['transformSettings', 'localScale', 'z'], parseFloat(e.target.value) || 1)}
                            />
                          </div>
                        </div>
                      </>
                    )}

                    <div className="form-group" style={{ marginTop: 12 }}>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={advancedSettings.overrideMaterialSettings}
                          onChange={(e) =>
                            updateVideoAdvancedSetting(idx, ['overrideMaterialSettings'], e.target.checked)
                          }
                        />
                        <span>Override Material Settings</span>
                      </label>
                    </div>

                    {advancedSettings.overrideMaterialSettings && (
                      <div className="settings-grid">
                        <div className="form-group">
                          <label>Tint R</label>
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={advancedSettings.materialSettings.tint.r}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'tint', 'r'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Tint G</label>
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={advancedSettings.materialSettings.tint.g}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'tint', 'g'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Tint B</label>
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={advancedSettings.materialSettings.tint.b}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'tint', 'b'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Tint A</label>
                          <input
                            type="number"
                            min="0"
                            max="1"
                            step="0.01"
                            value={advancedSettings.materialSettings.tint.a}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'tint', 'a'], parseFloat(e.target.value) || 1)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Brightness</label>
                          <input
                            type="number"
                            min="0"
                            max="2"
                            step="0.01"
                            value={advancedSettings.materialSettings.brightness}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'brightness'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Tiling X</label>
                          <input
                            type="number"
                            step="0.01"
                            value={advancedSettings.materialSettings.textureTiling.x}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'textureTiling', 'x'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Tiling Y</label>
                          <input
                            type="number"
                            step="0.01"
                            value={advancedSettings.materialSettings.textureTiling.y}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'textureTiling', 'y'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Offset X</label>
                          <input
                            type="number"
                            step="0.01"
                            value={advancedSettings.materialSettings.textureOffset.x}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'textureOffset', 'x'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                        <div className="form-group">
                          <label>Offset Y</label>
                          <input
                            type="number"
                            step="0.01"
                            value={advancedSettings.materialSettings.textureOffset.y}
                            onChange={(e) => updateVideoAdvancedSetting(idx, ['materialSettings', 'textureOffset', 'y'], parseFloat(e.target.value) || 0)}
                          />
                        </div>
                      </div>
                    )}
                  </details>
                </div>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => removeVideo(idx)}
                >
                  Remove
                </button>
              </div>
            );
          })}
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
            <label>Requirements Poll Interval (seconds)</label>
            <input
              type="number"
              min="5"
              max="120"
              value={config.requirementsPollInterval || 15}
              onChange={(e) => updateField('requirementsPollInterval', parseInt(e.target.value) || 15)}
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
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.fastResyncOnFocus ?? true}
                onChange={(e) => updateField('fastResyncOnFocus', e.target.checked)}
              />
              <span>Fast Resync on Focus</span>
            </label>
            <span className="form-hint">
              Reconnect UI updates and force a quick device status sync when app/tab regains focus
            </span>
          </div>

          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={config.ignoreRequirements || false}
                onChange={(e) => updateField('ignoreRequirements', e.target.checked)}
              />
              <span>Ignore Requirements</span>
            </label>
            <span className="form-hint">
              Allow playback commands even if videos/APK are not confirmed on device
            </span>
          </div>
        </div>
      </section>

      {filePicker && (
        <FilePicker
          title={filePicker.title}
          filter={filePicker.filter}
          onSelect={handleFileSelected}
          onClose={() => setFilePicker(null)}
        />
      )}
    </div>
  );
}
