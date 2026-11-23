import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useGamepad } from '@/hooks/useGamepad';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  takeoff: vi.fn().mockResolvedValue({ ok: true }),
  land: vi.fn().mockResolvedValue({ ok: true }),
  emergencyStop: vi.fn().mockResolvedValue({ ok: true }),
}));

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.OPEN;
  sent: string[] = [];
  closed = false;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.onclose?.();
  }
}

let pad: { connected: boolean; axes: number[]; buttons: { pressed: boolean }[] } | null;
let frame: ((now: number) => void) | null;
let clock: number;

/** Run one animation frame, advancing the clock past the 20 Hz send interval. */
function step() {
  clock += 60;
  const cb = frame;
  frame = null;
  cb?.(clock);
}

function makePad(axes = [0, 0, 0, 0]) {
  return { connected: true, axes, buttons: Array.from({ length: 16 }, () => ({ pressed: false })) };
}

const frames = () => FakeWebSocket.instances[0].sent.map((s) => JSON.parse(s));

describe('useGamepad', () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    pad = null;
    frame = null;
    clock = 0;
    vi.stubGlobal('WebSocket', FakeWebSocket);
    vi.stubGlobal('requestAnimationFrame', (cb: (now: number) => void) => {
      frame = cb;
      return 1;
    });
    vi.stubGlobal('cancelAnimationFrame', () => {
      frame = null;
    });
    Object.defineProperty(navigator, 'getGamepads', { configurable: true, value: () => [pad] });
    vi.mocked(api.takeoff).mockClear();
    vi.mocked(api.land).mockClear();
    vi.mocked(api.emergencyStop).mockClear();
    useDroneStore.setState({
      connectionStatus: 'connected',
      previewMode: false,
      isFlying: true,
      commandPending: false,
      gamepadConnected: false,
      rcSpeedCap: 50,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('does nothing until the drone is connected', () => {
    useDroneStore.setState({ connectionStatus: 'disconnected' });
    renderHook(() => useGamepad());
    expect(frame).toBeNull();
  });

  it('reports the gamepad and opens the control socket when one appears', () => {
    renderHook(() => useGamepad());
    step();
    expect(useDroneStore.getState().gamepadConnected).toBe(false);
    expect(FakeWebSocket.instances).toHaveLength(0);

    pad = makePad();
    step();
    expect(useDroneStore.getState().gamepadConnected).toBe(true);
    expect(FakeWebSocket.instances[0].url).toMatch(/\/api\/ws\/control$/);
  });

  it('streams stick input scaled by the speed cap while flying', () => {
    pad = makePad([0, 0, 0, -1]); // right stick fully forward
    renderHook(() => useGamepad());
    step();
    step();
    expect(frames()).toEqual([
      { lr: 0, fb: 50, ud: 0, yaw: 0 },
      { lr: 0, fb: 50, ud: 0, yaw: 0 },
    ]);
  });

  it('sends one zero frame on release, then stays quiet', () => {
    pad = makePad([0, 0, 0, -1]);
    renderHook(() => useGamepad());
    step();
    pad.axes = [0, 0, 0, 0];
    step();
    step();
    step();
    expect(frames()).toEqual([
      { lr: 0, fb: 50, ud: 0, yaw: 0 },
      { lr: 0, fb: 0, ud: 0, yaw: 0 },
    ]);
  });

  it('sends nothing while on the ground', () => {
    useDroneStore.setState({ isFlying: false });
    pad = makePad([0, 0, 0, -1]);
    renderHook(() => useGamepad());
    step();
    step();
    expect(frames()).toEqual([]);
  });

  it('maps A to takeoff, B to land and Back to emergency, once per press', () => {
    useDroneStore.setState({ isFlying: false });
    pad = makePad();
    renderHook(() => useGamepad());
    step();

    pad.buttons[0].pressed = true;
    step();
    step(); // still held: no repeat
    expect(api.takeoff).toHaveBeenCalledTimes(1);

    pad.buttons[0].pressed = false;
    useDroneStore.setState({ isFlying: true, commandPending: false });
    pad.buttons[1].pressed = true;
    step();
    expect(api.land).toHaveBeenCalledTimes(1);

    pad.buttons[1].pressed = false;
    pad.buttons[8].pressed = true;
    step();
    expect(api.emergencyStop).toHaveBeenCalledTimes(1);
  });

  it('closes the socket and clears the indicator on unmount', () => {
    pad = makePad();
    const { unmount } = renderHook(() => useGamepad());
    step();
    unmount();
    expect(FakeWebSocket.instances[0].closed).toBe(true);
    expect(useDroneStore.getState().gamepadConnected).toBe(false);
  });
});
