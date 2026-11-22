import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStickControl, RC_INTERVAL_MS } from '@/hooks/useStickControl';
import { IDLE_STICKS, useDroneStore } from '@/stores/droneStore';
import { PAD } from '@/lib/sticks';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  emergencyStop: vi.fn().mockResolvedValue({ ok: true }),
  land: vi.fn().mockResolvedValue({ ok: true }),
  takeoff: vi.fn().mockResolvedValue({ ok: true }),
}));

class FakeWS {
  static OPEN = 1;
  static instances: FakeWS[] = [];
  readyState = 1;
  sent: unknown[] = [];
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    FakeWS.instances.push(this);
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.readyState = 3;
  }
}

let pad: { id: string; connected: boolean; axes: number[]; buttons: { pressed: boolean }[] } | null;
const setButtons = (...ids: number[]) => {
  pad!.buttons = Array.from({ length: 17 }, (_, i) => ({ pressed: ids.includes(i) }));
};

const tick = (n = 1) => act(() => { vi.advanceTimersByTime(RC_INTERVAL_MS * n); });
const ws = () => FakeWS.instances[FakeWS.instances.length - 1];
const last = <T,>(a: T[]) => a[a.length - 1];

describe('useStickControl', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    FakeWS.instances = [];
    vi.stubGlobal('WebSocket', FakeWS);
    pad = { id: 'Xbox Wireless Controller (STANDARD GAMEPAD)', connected: true, axes: [0, 0, 0, 0], buttons: [] };
    setButtons();
    Object.defineProperty(navigator, 'getGamepads', { configurable: true, value: () => [pad] });
    useDroneStore.setState({
      connectionStatus: 'connected',
      previewMode: false,
      isFlying: true,
      commandPending: false,
      sequenceProgress: null,
      keyboardMode: 'tap',
      stickSpeed: 50,
      stickInput: IDLE_STICKS,
      gamepadName: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('sends nothing until the bumper (dead-man) is held', () => {
    renderHook(() => useStickControl());
    pad!.axes = [0, 0, 0, -1]; // full forward
    tick(3);
    expect(ws().sent).toEqual([]);
    expect(useDroneStore.getState().gamepadName).toMatch(/Xbox/);

    setButtons(PAD.RB);
    tick();
    expect(last(ws().sent)).toEqual({ lr: 0, fb: 50, ud: 0, yaw: 0 });
    expect(useDroneStore.getState().stickInput.armed).toBe(true);

    setButtons(); // let go -> one stop, then silence
    tick(3);
    expect(last(ws().sent)).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
    const count = ws().sent.length;
    tick(3);
    expect(ws().sent.length).toBe(count);
  });

  it('stops when the controller disappears mid-flight', () => {
    renderHook(() => useStickControl());
    pad!.axes = [0, 0, 1, 0];
    setButtons(PAD.LB);
    tick();
    expect(last(ws().sent)).toEqual({ lr: 50, fb: 0, ud: 0, yaw: 0 });
    pad = null;
    tick();
    expect(last(ws().sent)).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
    expect(useDroneStore.getState().gamepadName).toBeNull();
  });

  it('does not stream while a sequence runs or on the ground', () => {
    renderHook(() => useStickControl());
    pad!.axes = [0, 0, 0, -1];
    setButtons(PAD.RB);
    useDroneStore.setState({ sequenceProgress: { sequence_id: 'x', status: 'running', current_step: 1, total_steps: 3, step_description: '' } });
    tick(2);
    expect(ws().sent).toEqual([]);
    useDroneStore.setState({ sequenceProgress: null, isFlying: false });
    tick(2);
    expect(ws().sent).toEqual([]);
  });

  it('emergency needs both sticks clicked, and fires once', () => {
    renderHook(() => useStickControl());
    setButtons(PAD.L3);
    tick();
    expect(api.emergencyStop).not.toHaveBeenCalled();
    setButtons(PAD.L3, PAD.R3);
    tick(4);
    expect(api.emergencyStop).toHaveBeenCalledTimes(1);
  });

  it('takes off with bumper + Start and lands with Back', async () => {
    useDroneStore.setState({ isFlying: false });
    renderHook(() => useStickControl());
    setButtons(PAD.START);
    tick();
    expect(api.takeoff).not.toHaveBeenCalled();
    setButtons(PAD.RB, PAD.START);
    tick();
    expect(api.takeoff).toHaveBeenCalledTimes(1);
    await act(async () => { await Promise.resolve(); });
    useDroneStore.setState({ isFlying: true, commandPending: false });
    setButtons(PAD.BACK);
    tick();
    expect(api.land).toHaveBeenCalledTimes(1);
  });

  it('hold-to-fly keys stream while held and stop on release or blur', () => {
    pad = null;
    useDroneStore.setState({ keyboardMode: 'hold', stickSpeed: 40 });
    renderHook(() => useStickControl());
    act(() => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w' })); });
    act(() => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'e' })); });
    tick();
    expect(last(ws().sent)).toEqual({ lr: 0, fb: 40, ud: 0, yaw: 40 });
    act(() => { window.dispatchEvent(new Event('blur')); });
    tick();
    expect(last(ws().sent)).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
  });

  it('tap mode ignores held keys', () => {
    pad = null;
    renderHook(() => useStickControl());
    act(() => { window.dispatchEvent(new KeyboardEvent('keydown', { key: 'w' })); });
    tick(2);
    expect(ws().sent).toEqual([]);
  });

  it('shows the backend refusal reason', () => {
    renderHook(() => useStickControl());
    act(() => { ws().onmessage?.({ data: JSON.stringify({ type: 'rc_status', ok: false, error: 'Take off first' }) }); });
    expect(useDroneStore.getState().rcError).toBe('Take off first');
    act(() => { ws().onmessage?.({ data: JSON.stringify({ type: 'rc_status', ok: true, error: null }) }); });
    expect(useDroneStore.getState().rcError).toBeNull();
  });

  it('sends a final stop and closes when disconnected', () => {
    const { unmount } = renderHook(() => useStickControl());
    const sock = ws();
    unmount();
    expect(last(sock.sent)).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
    expect(sock.readyState).toBe(3);
  });
});
