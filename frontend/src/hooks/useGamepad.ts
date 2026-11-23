import { useEffect, useRef } from 'react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { axesToRc, GAMEPAD_BUTTON, isZeroRc, type RcFrame } from '@/lib/gamepad';

/** Stick frames per second. The backend hovers the drone if frames stop for 500 ms. */
const SEND_HZ = 20;

/**
 * Fly with a gamepad: sticks stream RC frames over /api/ws/control, face buttons
 * trigger takeoff / land / emergency.
 *
 * Polling runs on requestAnimationFrame, which browsers pause in background tabs —
 * so switching away stops the frames and the backend's dead-man timer hovers the drone.
 */
export function useGamepad() {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const previewMode = useDroneStore((s) => s.previewMode);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (connectionStatus !== 'connected' || previewMode) return;
    if (typeof navigator === 'undefined' || !navigator.getGamepads) return;

    const { setGamepadConnected } = useDroneStore.getState();
    let raf = 0;
    let lastSendAt = 0;
    let lastSentZero = true;
    let prevButtons: boolean[] = [];
    let stopped = false;

    function openSocket() {
      if (wsRef.current || stopped) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/control`);
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
      };
      ws.onerror = () => ws.close();
      wsRef.current = ws;
    }

    function closeSocket() {
      wsRef.current?.close();
      wsRef.current = null;
    }

    function send(rc: RcFrame) {
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(rc));
        lastSentZero = isZeroRc(rc);
      }
    }

    function handleButtons(pad: Gamepad) {
      const pressed = pad.buttons.map((b) => b.pressed);
      const justPressed = (i: number) => pressed[i] && !prevButtons[i];
      const { isFlying, sendCommand, setIsFlying } = useDroneStore.getState();

      if (justPressed(GAMEPAD_BUTTON.emergency)) {
        api.emergencyStop();
        setIsFlying(false);
      } else if (justPressed(GAMEPAD_BUTTON.takeoff) && !isFlying) {
        sendCommand(() => api.takeoff()).then((ok) => ok && setIsFlying(true));
      } else if (justPressed(GAMEPAD_BUTTON.land) && isFlying) {
        sendCommand(() => api.land()).then((ok) => ok && setIsFlying(false));
      }
      prevButtons = pressed;
    }

    function tick(now: number) {
      if (stopped) return;
      raf = requestAnimationFrame(tick);

      const pad = Array.from(navigator.getGamepads()).find((p) => p?.connected) ?? null;
      const store = useDroneStore.getState();
      if (store.gamepadConnected !== !!pad) setGamepadConnected(!!pad);

      if (!pad) {
        closeSocket();
        prevButtons = [];
        return;
      }
      openSocket();
      handleButtons(pad);

      if (now - lastSendAt < 1000 / SEND_HZ) return;
      lastSendAt = now;

      const rc = store.isFlying ? axesToRc(pad.axes, store.rcSpeedCap) : null;
      // Keep refreshing live input; after release send a single zero frame, then go quiet.
      if (rc && (!isZeroRc(rc) || !lastSentZero)) send(rc);
    }

    raf = requestAnimationFrame(tick);

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      closeSocket(); // the backend zeroes the sticks when the socket closes
      setGamepadConnected(false);
    };
  }, [connectionStatus, previewMode]);
}
