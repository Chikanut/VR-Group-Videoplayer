import React, { useState, useEffect } from 'react';
import { browseFiles } from '../api';

function formatSize(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function FilePicker({ onSelect, onClose, filter = '', title = 'Select File' }) {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [parentPath, setParentPath] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDirectory = async (path) => {
    setLoading(true);
    setError('');
    try {
      const data = await browseFiles(path, filter);
      if (data.error) {
        setError(data.error);
      } else {
        setCurrentPath(data.path || '');
        setEntries(data.entries || []);
        setParentPath(data.parent || '');
      }
    } catch (e) {
      setError('Failed to browse files');
    }
    setLoading(false);
  };

  useEffect(() => {
    loadDirectory('');
  }, []);

  const handleEntryClick = (entry) => {
    if (entry.type === 'directory') {
      loadDirectory(entry.path);
    } else {
      onSelect(entry.path);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal file-picker-modal" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-header">
          <h2>{title}</h2>
          <button className="btn-close" onClick={onClose}>x</button>
        </div>

        <div className="file-picker-path">
          {parentPath !== '' && (
            <button className="btn btn-small" onClick={() => loadDirectory(parentPath)}>
              .. Up
            </button>
          )}
          {currentPath === '' && parentPath === '' && (
            <span className="path-label">Select a drive</span>
          )}
          <span className="path-label" title={currentPath}>{currentPath}</span>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <div className="file-picker-list">
          {loading ? (
            <div className="loading-state" style={{ minHeight: 100 }}>
              <div className="spinner" />
            </div>
          ) : entries.length === 0 ? (
            <p className="file-picker-empty">No files found</p>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.path}
                className={`file-picker-entry ${entry.type}`}
                onClick={() => handleEntryClick(entry)}
              >
                <span className="file-icon">
                  {entry.type === 'directory' ? '\uD83D\uDCC1' : '\uD83D\uDCC4'}
                </span>
                <span className="file-name">{entry.name}</span>
                {entry.size > 0 && (
                  <span className="file-size">{formatSize(entry.size)}</span>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
