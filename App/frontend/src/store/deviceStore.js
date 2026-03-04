import { create } from 'zustand';

const useDeviceStore = create((set, get) => ({
  devices: {},
  config: null,
  connected: false,
  loading: true,

  setConnected: (connected) => set({ connected }),
  setLoading: (loading) => set({ loading }),

  handleSnapshot: (data) => {
    const devicesMap = {};
    for (const d of data.devices || []) {
      devicesMap[d.deviceId] = d;
    }
    set({
      devices: devicesMap,
      config: data.config || null,
      loading: false,
    });
  },

  handleDeviceUpdate: (data) => {
    set((state) => {
      const devices = { ...state.devices };
      if (data.isNew && data.device) {
        devices[data.deviceId] = data.device;
      } else if (data.device) {
        devices[data.deviceId] = data.device;
      } else if (data.changes && devices[data.deviceId]) {
        devices[data.deviceId] = { ...devices[data.deviceId], ...data.changes };
      }
      return { devices };
    });
  },

  handleDeviceRemoved: (deviceId) => {
    set((state) => {
      const devices = { ...state.devices };
      delete devices[deviceId];
      return { devices };
    });
  },

  handleConfigUpdated: (config) => {
    set({ config });
  },

  handleUpdateProgress: (data) => {
    set((state) => {
      const devices = { ...state.devices };
      const device = devices[data.deviceId];
      if (device) {
        devices[data.deviceId] = {
          ...device,
          updateInProgress: data.stage !== 'completed' && data.stage !== 'failed' && data.stage !== 'completed_with_errors',
          updateProgress: data,
        };
      }
      return { devices };
    });
  },

  getDeviceList: () => {
    return Object.values(get().devices).sort((a, b) => {
      if (a.online !== b.online) return a.online ? -1 : 1;
      return (a.name || a.deviceId).localeCompare(b.name || b.deviceId);
    });
  },

  getOnlineDevices: () => {
    return Object.values(get().devices).filter((d) => d.online);
  },

  getOnlinePlayerDevices: () => {
    return Object.values(get().devices).filter((d) => d.online && d.playerConnected);
  },
}));

export default useDeviceStore;
