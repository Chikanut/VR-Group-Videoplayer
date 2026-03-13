import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getConfig, getDeviceNames, replaceDeviceNames, updateConfig } from '../api';
import { useI18n } from '../i18n';
import packageJson from '../../package.json';

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
      topCrop: 0,
      bottomCrop: 0,
    },
  };
}

function cloneAdvancedSettings(settings) {
  return JSON.parse(JSON.stringify(settings || createDefaultAdvancedSettings()));
}

function stripRuntimeFields(config) {
  if (!config) {
    return {};
  }
  const { isAndroidRuntime, ...rest } = config;
  return rest;
}

function downloadJson(filename, data) {
  const payload = JSON.stringify(data, null, 2);

  if (window.AndroidBridge?.saveJsonFile) {
    const saved = window.AndroidBridge.saveJsonFile(filename, payload);
    if (saved) {
      return true;
    }
  }

  const blob = new Blob([payload], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

function createUniqueVideoName(videos, sourceName) {
  const existingNames = new Set(videos.map((video) => video.name).filter(Boolean));
  const baseName = sourceName || 'Video';
  const copyBase = `${baseName} Copy`;
  if (!existingNames.has(copyBase)) {
    return copyBase;
  }

  let index = 2;
  while (existingNames.has(`${copyBase} ${index}`)) {
    index += 1;
  }
  return `${copyBase} ${index}`;
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const { t, language, setLanguage } = useI18n();
  const [config, setConfig] = useState(null);
  const [deviceNames, setDeviceNames] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const configImportRef = useRef(null);
  const deviceNamesImportRef = useRef(null);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    setError('');
    try {
      const [configData, deviceNamesData] = await Promise.all([
        getConfig(),
        getDeviceNames(),
      ]);
      setConfig(configData);
      setDeviceNames(deviceNamesData || {});
    } catch {
      setError(t('Failed to load settings'));
    }
  };

  const showSuccess = (message) => {
    setSuccess(message);
    setTimeout(() => setSuccess(''), 3000);
  };

  const handleSave = async () => {
    setError('');
    setSuccess('');
    setSaving(true);

    const videos = config.requirementVideos || [];
    const names = videos.map((video) => video.name?.trim()).filter(Boolean);
    const filenames = videos.map((video) => video.filename?.trim()).filter(Boolean);

    if (new Set(names).size !== names.length) {
      setError(t('Duplicate video names found'));
      setSaving(false);
      return;
    }

    if (new Set(filenames).size !== filenames.length) {
      setError(t('Duplicate video filenames found'));
      setSaving(false);
      return;
    }

    try {
      const updated = await updateConfig(stripRuntimeFields(config));
      setConfig(updated);
      showSuccess(t('Settings saved successfully'));
    } catch {
      setError(t('Failed to save settings'));
    }

    setSaving(false);
  };

  const updateField = (field, value) => {
    setConfig((current) => ({ ...current, [field]: value }));
  };

  const addVideo = () => {
    const videos = [...(config.requirementVideos || [])];
    videos.push({
      id: generateId(),
      name: '',
      filename: '',
      loop: false,
      videoType: '360',
      placementMode: 'default',
      advancedSettings: createDefaultAdvancedSettings(),
    });
    updateField('requirementVideos', videos);
  };

  const duplicateVideo = (index) => {
    const videos = [...(config.requirementVideos || [])];
    const source = videos[index];
    const duplicate = {
      ...JSON.parse(JSON.stringify(source)),
      id: generateId(),
      name: createUniqueVideoName(videos, source?.name),
      advancedSettings: cloneAdvancedSettings(source?.advancedSettings),
    };
    videos.splice(index + 1, 0, duplicate);
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

  const handleImportFile = async (event, type) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      if (type === 'config') {
        const updated = await updateConfig(data);
        setConfig(updated);
        showSuccess(t('Config imported successfully'));
        return;
      }

      const updatedNames = await replaceDeviceNames(data);
      setDeviceNames(updatedNames || {});
      showSuccess(t('Device names imported successfully'));
    } catch {
      setError(type === 'config' ? t('Failed to import config') : t('Failed to import device names'));
    }
  };

  if (!config) {
    return (
      <div className="settings-page">
        <p>{t('Loading settings...')}</p>
      </div>
    );
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <button className="btn" onClick={() => navigate('/')}>
          {t('Back')}
        </button>
        <h1>{t('Settings')}</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {success && <div className="alert alert-success">{success}</div>}

      <section className="settings-section">
        <h2>{t('General')}</h2>
        <div className="settings-grid">
          <div className="form-group">
            <label>{t('Language')}</label>
            <select value={language} onChange={(event) => setLanguage(event.target.value)}>
              <option value="uk">{t('Ukrainian')}</option>
              <option value="en">{t('English')}</option>
            </select>
          </div>

          <div className="form-group">
            <label>{t('Phone Control App Link')}</label>
            <input
              type="text"
              value={config.mobileAppUrl || ''}
              onChange={(event) => updateField('mobileAppUrl', event.target.value)}
              placeholder="https://example.com/control-panel.apk"
            />
            <span className="form-hint">{t('Used in the Connection popup as a QR code and direct download link for the mobile control panel app.')}</span>
          </div>

          <div className="form-group">
            <label>{t('Player App Link')}</label>
            <input
              type="text"
              value={config.playerAppUrl || ''}
              onChange={(event) => updateField('playerAppUrl', event.target.value)}
              placeholder="https://example.com/player.apk"
            />
            <span className="form-hint">{t('Used in the Connection popup as a QR code and direct download link for the headset player app.')}</span>
          </div>
        </div>

        <div className="settings-action-row">
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? t('Saving...') : t('Save')}
          </button>
          <button className="btn" onClick={() => downloadJson('config.json', stripRuntimeFields(config))}>
            {t('Export Config')}
          </button>
          <button className="btn" onClick={() => downloadJson('device_names.json', deviceNames)}>
            {t('Export Device Names')}
          </button>
          <button className="btn" onClick={() => configImportRef.current?.click()}>
            {t('Import Config')}
          </button>
          <button className="btn" onClick={() => deviceNamesImportRef.current?.click()}>
            {t('Import Device Names')}
          </button>
        </div>

        <input
          ref={configImportRef}
          type="file"
          accept=".json,application/json"
          className="hidden-file-input"
          onChange={(event) => handleImportFile(event, 'config')}
        />
        <input
          ref={deviceNamesImportRef}
          type="file"
          accept=".json,application/json"
          className="hidden-file-input"
          onChange={(event) => handleImportFile(event, 'deviceNames')}
        />
      </section>

      <section className="settings-section">
        <h2>{t('Requirement Videos')}</h2>
        <p className="settings-note">
          {t('Save only the video filename. The app sends that filename to the player, and the player opens it from /sdcard/Movies/.')}
        </p>

        <div className="video-requirements-list">
          {(config.requirementVideos || []).map((video, index) => {
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
              <div key={video.id || index} className="video-requirement-row">
                <div className="video-card-header">
                  <strong>{video.name || t('New video')}</strong>
                  <div className="video-card-actions">
                    <button className="btn btn-small" onClick={() => duplicateVideo(index)}>
                      {t('Duplicate')}
                    </button>
                    <button className="btn btn-danger btn-small" onClick={() => removeVideo(index)}>
                      {t('Remove')}
                    </button>
                  </div>
                </div>

                <div className="settings-grid">
                  <div className="form-group">
                    <label>{t('Name')}</label>
                    <input
                      type="text"
                      value={video.name || ''}
                      onChange={(event) => updateVideo(index, 'name', event.target.value)}
                      placeholder="Lesson 01"
                    />
                  </div>

                  <div className="form-group">
                    <label>{t('Filename')}</label>
                    <input
                      type="text"
                      value={video.filename || ''}
                      onChange={(event) => updateVideo(index, 'filename', event.target.value)}
                      placeholder="lesson_01.mp4"
                    />
                  </div>

                  <div className="form-group form-group-small">
                    <label>{t('Type')}</label>
                    <select
                      value={video.videoType || '360'}
                      onChange={(event) => updateVideo(index, 'videoType', event.target.value)}
                    >
                      <option value="360">360</option>
                      <option value="2d">2D</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label>{t('Placement')}</label>
                    <select
                      value={video.placementMode || 'default'}
                      onChange={(event) => updateVideo(index, 'placementMode', event.target.value)}
                    >
                      <option value="default">{t('Default')}</option>
                      <option value="locked">{t('Locked to camera')}</option>
                      <option value="free">{t('Free in space')}</option>
                    </select>
                    <span className="form-hint">{t('Older player versions ignore this and keep their default behavior.')}</span>
                  </div>

                  <div className="form-group form-group-small">
                    <label>{t('Loop')}</label>
                    <input
                      type="checkbox"
                      checked={video.loop || false}
                      onChange={(event) => updateVideo(index, 'loop', event.target.checked)}
                    />
                  </div>
                </div>

                <details className="form-group video-advanced-details">
                  <summary>{t('Advanced Settings')}</summary>

                  <div className="form-group" style={{ marginTop: 12 }}>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={advancedSettings.overrideTransformSettings}
                        onChange={(event) => updateVideoAdvancedSetting(index, ['overrideTransformSettings'], event.target.checked)}
                      />
                      <span>{t('Override Transform Settings')}</span>
                    </label>
                  </div>

                  {advancedSettings.overrideTransformSettings && (
                    <div className="settings-grid">
                      <div className="form-group">
                        <label>{t('Position X')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localPosition.x}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localPosition', 'x'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Position Y')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localPosition.y}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localPosition', 'y'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Position Z')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localPosition.z}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localPosition', 'z'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Rotation X')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localRotation.x}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localRotation', 'x'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Rotation Y')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localRotation.y}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localRotation', 'y'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Rotation Z')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localRotation.z}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localRotation', 'z'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Scale X')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localScale.x}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localScale', 'x'], parseFloat(event.target.value) || 1)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Scale Y')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localScale.y}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localScale', 'y'], parseFloat(event.target.value) || 1)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Scale Z')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.transformSettings.localScale.z}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['transformSettings', 'localScale', 'z'], parseFloat(event.target.value) || 1)}
                        />
                      </div>
                    </div>
                  )}

                  <div className="form-group" style={{ marginTop: 12 }}>
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={advancedSettings.overrideMaterialSettings}
                        onChange={(event) => updateVideoAdvancedSetting(index, ['overrideMaterialSettings'], event.target.checked)}
                      />
                      <span>{t('Override Material Settings')}</span>
                    </label>
                  </div>

                  {advancedSettings.overrideMaterialSettings && (
                    <div className="settings-grid">
                      <div className="form-group">
                        <label>{t('Tint R')}</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={advancedSettings.materialSettings.tint.r}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'tint', 'r'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Tint G')}</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={advancedSettings.materialSettings.tint.g}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'tint', 'g'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Tint B')}</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={advancedSettings.materialSettings.tint.b}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'tint', 'b'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Tint A')}</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={advancedSettings.materialSettings.tint.a}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'tint', 'a'], parseFloat(event.target.value) || 1)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Brightness')}</label>
                        <input
                          type="number"
                          min="0"
                          max="2"
                          step="0.01"
                          value={advancedSettings.materialSettings.brightness}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'brightness'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Tiling X')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.materialSettings.textureTiling.x}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'textureTiling', 'x'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Tiling Y')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.materialSettings.textureTiling.y}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'textureTiling', 'y'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Offset X')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.materialSettings.textureOffset.x}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'textureOffset', 'x'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Offset Y')}</label>
                        <input
                          type="number"
                          step="0.01"
                          value={advancedSettings.materialSettings.textureOffset.y}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'textureOffset', 'y'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Top Crop')}</label>
                        <input
                          type="number"
                          min="0"
                          max="0.49"
                          step="0.001"
                          value={advancedSettings.materialSettings.topCrop}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'topCrop'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                      <div className="form-group">
                        <label>{t('Bottom Crop')}</label>
                        <input
                          type="number"
                          min="0"
                          max="0.49"
                          step="0.001"
                          value={advancedSettings.materialSettings.bottomCrop}
                          onChange={(event) => updateVideoAdvancedSetting(index, ['materialSettings', 'bottomCrop'], parseFloat(event.target.value) || 0)}
                        />
                      </div>
                    </div>
                  )}
                </details>
              </div>
            );
          })}
        </div>

        <button className="btn" onClick={addVideo}>
          + {t('Add Video')}
        </button>
      </section>

      <section className="settings-section">
        <h2>{t('System Settings')}</h2>
        <div className="settings-grid">
          <div className="form-group">
            <label>{t('Battery Warning Threshold (%)')}</label>
            <input
              type="number"
              min="0"
              max="100"
              value={config.batteryThreshold || 20}
              onChange={(event) => updateField('batteryThreshold', parseInt(event.target.value, 10) || 0)}
            />
          </div>

          <div className="form-group">
            <label>{t('Network Scan Interval (seconds)')}</label>
            <input
              type="number"
              min="5"
              max="300"
              value={config.scanInterval || 30}
              onChange={(event) => updateField('scanInterval', parseInt(event.target.value, 10) || 30)}
            />
          </div>

          <div className="form-group">
            <label>{t('Network Subnet')}</label>
            <input
              type="text"
              value={config.networkSubnet || ''}
              onChange={(event) => updateField('networkSubnet', event.target.value)}
              placeholder="192.168.1"
            />
            <span className="form-hint">{t('Leave empty to auto-detect the local subnet.')}</span>
          </div>

          <div className="form-group">
            <label>{t('Device Offline Timeout (seconds)')}</label>
            <input
              type="number"
              min="10"
              max="300"
              value={config.deviceOfflineTimeout || 30}
              onChange={(event) => updateField('deviceOfflineTimeout', parseInt(event.target.value, 10) || 30)}
            />
          </div>
        </div>
      </section>

      <footer className="settings-footer">
        <span>Version: {packageJson.version}</span>
        <span>Автор: Войтович Євген</span>
        <a href="https://github.com/Chikanut" target="_blank" rel="noreferrer">
          GitHub: https://github.com/Chikanut
        </a>
      </footer>
    </div>
  );
}
