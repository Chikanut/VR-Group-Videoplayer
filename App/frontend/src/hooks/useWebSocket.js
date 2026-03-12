import { useEffect, useRef } from 'react';
import useDeviceStore from '../store/deviceStore';

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000];

export function useWebSocket() {
  const wsRef = useRef(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef(null);

  const {
    setConnected,
    setLoading,
    handleSnapshot,
    handleDeviceUpdate,
    handleDeviceRemoved,
    handleConfigUpdated,
    handleUpdateProgress,
  } = useDeviceStore();

  useEffect(() => {
    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const url = `${protocol}//${host}/ws`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttempt.current = 0;
        setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          switch (msg.type) {
            case 'snapshot':
              handleSnapshot(msg);
              break;
            case 'device_update':
              handleDeviceUpdate(msg);
              break;
            case 'device_removed':
              handleDeviceRemoved(msg.deviceId);
              break;
            case 'config_updated':
              handleConfigUpdated(msg.config);
              break;
            case 'update_progress':
              handleUpdateProgress(msg);
              break;
          }
        } catch (e) {
          console.error('WebSocket message parse error:', e);
        }
      };
    }

    function scheduleReconnect() {
      const delay = RECONNECT_DELAYS[Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)];
      reconnectAttempt.current++;
      reconnectTimer.current = setTimeout(connect, delay);
    }

    function reconnectNow() {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }

      reconnectAttempt.current = 0;

      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }

      setLoading(true);
      connect();
    }

    function onFocusOrVisible() {
      if (document.visibilityState === 'visible') {
        reconnectNow();
      }
    }

    connect();
    document.addEventListener('visibilitychange', onFocusOrVisible);
    window.addEventListener('focus', onFocusOrVisible);

    return () => {
      document.removeEventListener('visibilitychange', onFocusOrVisible);
      window.removeEventListener('focus', onFocusOrVisible);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [
    setConnected,
    setLoading,
    handleSnapshot,
    handleDeviceUpdate,
    handleDeviceRemoved,
    handleConfigUpdated,
    handleUpdateProgress,
  ]);
}
