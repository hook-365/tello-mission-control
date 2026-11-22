import { useEffect, useRef } from 'react';
import { IDLE_STICKS, useDroneStore, type StickInput } from '@/stores/droneStore';
import * as api from '@/lib/api';
import {
  HOLD_KEYS,
  ZERO,
  isZero,
  keysToSticks,
  readPad,
  sameSticks,
  scaleSticks,
} from '@/lib/sticks';
import type { RcSticks } from '@/types/drone';

/** How often stick positions are streamed to the backend (ms). Backend hovers after 500 ms of silence. */
export const RC_INTERVAL_MS = 50;

function firstGamepad(): Gamepad | null {
  try {
    const pads = typeof navigator.getGamepads === 'function' ? navigator.getGamepads() : [];
    for (const p of pads ?? []) if (p && p.connected) return p;
  } catch {
    // Gamepad API blocked (e.g. permissions policy)
  }
  return null;
}

function isTyping(target: EventTarget | null): boolean {
  const tag = (target as HTMLElement | null)?.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

/**
 * Stick flying: streams game controller (or held keys) to /api/ws/rc.
 *
 * Safety:
 * - Nothing is sent unless a dead-man is held: a controller bumper, or a
 *   movement key in "hold" keyboard mode. Letting go sends one stop (hover).
 * - Tab hidden / window blur / controller unplugged -> stop.
 * - The backend also hovers if updates stop for 0.5 s, and when this socket closes.
 * - Disabled while a sequence runs.
 */
export function useStickControl() {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const previewMode = useDroneStore((s) => s.previewMode);
  const keyboardMode = useDroneStore((s) => s.keyboardMode);

  const wsRef = useRef<WebSocket | null>(null);
  const keysRef = useRef<Set<string>>(new Set());
  const sentZeroRef = useRef(true);
  const edgesRef = useRef({ takeoff: false, land: false, emergency: false });

  const active = connectionStatus === 'connected' && !previewMode;

  // --- RC socket ---
  useEffect(() => {
    if (!active) return;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const open = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/rc`);
      wsRef.current = ws;
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg?.type === 'rc_status') useDroneStore.getState().setRcError(msg.ok ? null : msg.error ?? 'Refused');
        } catch {
          // ignore
        }
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (!closed) retry = setTimeout(open, 2000);
      };
    };
    open();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws) {
        try {
          if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(ZERO));
        } catch {
          // ignore
        }
        ws.close();
      }
      sentZeroRef.current = true;
      useDroneStore.getState().setRcError(null);
    };
  }, [active]);

  // --- Hold-to-fly keys ---
  useEffect(() => {
    const keys = keysRef.current;
    keys.clear();
    if (!active || keyboardMode !== 'hold') return;

    const down = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const k = e.key.toLowerCase();
      if (k in HOLD_KEYS) {
        e.preventDefault();
        keys.add(k);
      }
    };
    const up = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (k in HOLD_KEYS) keys.delete(k);
    };
    const clear = () => keys.clear();
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') keys.clear();
    };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    window.addEventListener('blur', clear);
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
      window.removeEventListener('blur', clear);
      document.removeEventListener('visibilitychange', onVisibility);
      keys.clear();
    };
  }, [active, keyboardMode]);

  // --- Control loop ---
  useEffect(() => {
    if (!active) return;

    const send = (s: RcSticks) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(s));
        return true;
      }
      return false;
    };

    const tick = () => {
      const st = useDroneStore.getState();
      const pad = firstGamepad();
      const name = pad ? pad.id : null;
      if (name !== st.gamepadName) st.setGamepadName(name);

      // Buttons (rising edges only)
      const reading = pad
        ? readPad(pad.axes, (i) => !!pad.buttons[i]?.pressed)
        : null;
      const edges = edgesRef.current;
      const emergency = !!reading?.emergency;
      const land = !!reading?.land;
      const takeoff = !!reading?.takeoff;
      if (emergency && !edges.emergency) {
        void api.emergencyStop();
      } else if (land && !edges.land && st.isFlying) {
        void st.sendCommand(() => api.land()).then((ok) => ok && st.setIsFlying(false));
      } else if (takeoff && !edges.takeoff && !st.isFlying && !st.sequenceProgress) {
        void st.sendCommand(() => api.takeoff()).then((ok) => ok && st.setIsFlying(true));
      }
      edgesRef.current = { emergency, land, takeoff };

      // Sticks
      const visible = typeof document === 'undefined' || document.visibilityState !== 'hidden';
      let input: StickInput = IDLE_STICKS;
      if (visible && reading?.armed) {
        input = { sticks: scaleSticks(reading.sticks, st.stickSpeed), armed: true, source: 'gamepad' };
      } else if (visible && st.keyboardMode === 'hold' && keysRef.current.size > 0) {
        input = { sticks: scaleSticks(keysToSticks(keysRef.current), st.stickSpeed), armed: true, source: 'keyboard' };
      }

      const running = st.sequenceProgress?.status === 'running';
      const canFly = st.isFlying && !running && !emergency;
      if (input.armed && canFly) {
        if (send(input.sticks)) sentZeroRef.current = isZero(input.sticks);
      } else if (!sentZeroRef.current) {
        if (send(ZERO)) sentZeroRef.current = true;
      }

      const prev = st.stickInput;
      if (prev.armed !== input.armed || prev.source !== input.source || !sameSticks(prev.sticks, input.sticks)) {
        st.setStickInput(input);
      }
    };

    const id = setInterval(tick, RC_INTERVAL_MS);
    return () => {
      clearInterval(id);
      useDroneStore.getState().setStickInput(IDLE_STICKS);
    };
  }, [active]);
}
