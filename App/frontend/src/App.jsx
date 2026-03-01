import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import SettingsPage from './components/SettingsPage';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  useWebSocket();

  return (
    <Routes>
      <Route path="/" element={<Layout />} />
      <Route path="/settings" element={<SettingsPage />} />
    </Routes>
  );
}
