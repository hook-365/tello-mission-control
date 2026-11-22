import { useEffect, useRef } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import type { CommandLogEntry, MediaEvent, SequenceProgress, TelemetryData, WsMessage } from '@/types/drone';

const MAX_BACKOFF = 16000;

export function useWebSocket() {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const previewMode = useDroneStore((s) => s.previewMode);
  const setTelemetry = useDroneStore((s) => s.setTelemetry);
  const addCommandLog = useDroneStore((s) => s.addCommandLog);
  const setSequenceProgress = useDroneStore((s) => s.setSequenceProgress);
  const setIsFlying = useDroneStore((s) => s.setIsFlying);
  const applyMediaEvent = useDroneStore((s) => s.applyMediaEvent);

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef(1000);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Don't connect WebSocket in preview mode — no backend available
    if (connectionStatus !== 'connected' || previewMode) {
      // Clean up on disconnect
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      return;
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/telemetry`);
      wsRef.current = ws;

      ws.onopen = () => {
        backoffRef.current = 1000; // Reset backoff on success
      };

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data);

          switch (msg.type) {
            case 'telemetry': {
              const data = msg.data as TelemetryData;
              setTelemetry(data);
              // Infer flying state from height
              if (data.height > 0) {
                setIsFlying(true);
              }
              break;
            }
            case 'command_log':
              addCommandLog(msg.data as CommandLogEntry);
              break;
            case 'media':
              applyMediaEvent(msg.data as MediaEvent);
              break;
            case 'sequence_progress': {
              const progress = msg.data as SequenceProgress;
              setSequenceProgress(progress);
              if (progress.status !== 'running') {
                // Keep the final state visible briefly, unless a new run has started since
                setIsFlying(false);
                setTimeout(() => {
                  const current = useDroneStore.getState().sequenceProgress;
                  if (current?.run_id === progress.run_id && current?.status !== 'running') {
                    setSequenceProgress(null);
                  }
                }, 6000);
              } else if (progress.current_step > 0) {
                setIsFlying(true);
              }
              break;
            }
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        // Only reconnect if still connected
        if (useDroneStore.getState().connectionStatus === 'connected') {
          reconnectTimerRef.current = setTimeout(() => {
            backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
            connect();
          }, backoffRef.current);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [connectionStatus, previewMode, setTelemetry, addCommandLog, setSequenceProgress, setIsFlying, applyMediaEvent]);
}
