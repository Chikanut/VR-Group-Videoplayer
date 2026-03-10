import React, { createContext, useContext, useMemo, useState } from 'react';

const dictionaries = {
  en: {
    language: 'Language',
    ukrainian: 'Ukrainian',
    english: 'English',
    settings: 'Settings',
    save: 'Save',
    saving: 'Saving...',
    back: 'Back',
    loadingSettings: 'Loading settings...',
    duplicateVideoNames: 'Duplicate video names found',
    duplicateVideoFilenames: 'Duplicate video filenames found',
    duplicateVideoPaths: 'Duplicate video paths found',
    settingsSaved: 'Settings saved successfully',
    settingsSaveFailed: 'Failed to save settings',
    connectionLost: 'Connection lost. Reconnecting...',
    connectingServer: 'Connecting to server...',
    noDevicesFound: 'No devices found',
    scanningNetwork: 'Scanning network...',
    onlineCount: '{online}/{total} online',
    mode: 'Mode',
    android: 'Android',
    desktop: 'Desktop',
    playAll: 'Play All',
    pauseAll: 'Pause All',
    resumeAll: 'Resume All',
    stopAll: 'Stop All',
    recenterAll: 'Recenter All',
    globalVolume: 'Global volume',
    // keep defaults for many legacy strings
  },
  uk: {
    language: 'Мова',
    ukrainian: 'Українська',
    english: 'Англійська',
    settings: 'Налаштування',
    save: 'Зберегти',
    saving: 'Збереження...',
    back: 'Назад',
    loadingSettings: 'Завантаження налаштувань...',
    duplicateVideoNames: 'Знайдено дублікати назв відео',
    duplicateVideoFilenames: 'Знайдено дублікати імен файлів відео',
    duplicateVideoPaths: 'Знайдено дублікати шляхів до відео',
    settingsSaved: 'Налаштування успішно збережено',
    settingsSaveFailed: 'Не вдалося зберегти налаштування',
    connectionLost: 'Звʼязок втрачено. Повторне підключення...',
    connectingServer: 'Підключення до сервера...',
    noDevicesFound: 'Пристрої не знайдено',
    scanningNetwork: 'Сканування мережі...',
    onlineCount: 'онлайн {online}/{total}',
    mode: 'Режим',
    android: 'Android',
    desktop: 'Desktop',
    playAll: 'Відтворити всі',
    pauseAll: 'Пауза для всіх',
    resumeAll: 'Продовжити для всіх',
    stopAll: 'Зупинити всі',
    recenterAll: 'Центрувати всі',
    globalVolume: 'Глобальна гучність',
  },
};

const I18nContext = createContext(null);

export function I18nProvider({ children }) {
  const [language, setLanguage] = useState(() => localStorage.getItem('uiLanguage') || 'uk');

  const value = useMemo(() => ({
    language,
    setLanguage: (lang) => {
      setLanguage(lang);
      localStorage.setItem('uiLanguage', lang);
    },
    t: (key, vars = {}) => {
      const dict = dictionaries[language] || dictionaries.en;
      let text = dict[key] || dictionaries.en[key] || key;
      Object.entries(vars).forEach(([k, v]) => {
        text = text.replaceAll(`{${k}}`, String(v));
      });
      return text;
    },
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
