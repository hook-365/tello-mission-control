import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as api from '@/lib/api';

describe('api client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function mockFetch(body: unknown, ok = true, status = 200) {
    return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok,
      status,
      json: () => Promise.resolve(body),
      text: () => Promise.resolve(JSON.stringify(body)),
      blob: () => Promise.resolve(new Blob()),
    } as Response);
  }

  it('connectDrone sends POST to /api/control/connect', async () => {
    const spy = mockFetch({ ok: true, status: 'connected', battery: 85 });
    const res = await api.connectDrone();
    expect(spy).toHaveBeenCalledWith('/api/control/connect', expect.objectContaining({ method: 'POST' }));
    expect(res.battery).toBe(85);
  });

  it('disconnectDrone sends POST', async () => {
    const spy = mockFetch({ ok: true, message: 'Disconnected' });
    await api.disconnectDrone();
    expect(spy).toHaveBeenCalledWith('/api/control/disconnect', expect.objectContaining({ method: 'POST' }));
  });

  it('takeoff sends POST', async () => {
    const spy = mockFetch({ ok: true, message: 'Takeoff' });
    const res = await api.takeoff();
    expect(spy).toHaveBeenCalledWith('/api/control/takeoff', expect.objectContaining({ method: 'POST' }));
    expect(res.ok).toBe(true);
  });

  it('land sends POST', async () => {
    mockFetch({ ok: true, message: 'Land' });
    const res = await api.land();
    expect(res.ok).toBe(true);
  });

  it('emergencyStop sends POST', async () => {
    const spy = mockFetch({ ok: true, message: 'Emergency' });
    await api.emergencyStop();
    expect(spy).toHaveBeenCalledWith('/api/control/emergency', expect.objectContaining({ method: 'POST' }));
  });

  it('move sends direction and distance', async () => {
    const spy = mockFetch({ ok: true, message: 'Moved' });
    await api.move('forward', 100);
    expect(spy).toHaveBeenCalledWith(
      '/api/control/move',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ direction: 'forward', distance_cm: 100 }),
      }),
    );
  });

  it('rotate sends direction and angle', async () => {
    const spy = mockFetch({ ok: true, message: 'Rotated' });
    await api.rotate('cw', 90);
    expect(spy).toHaveBeenCalledWith(
      '/api/control/rotate',
      expect.objectContaining({
        body: JSON.stringify({ direction: 'cw', angle_deg: 90 }),
      }),
    );
  });

  it('flip sends direction', async () => {
    const spy = mockFetch({ ok: true, message: 'Flipped' });
    await api.flip('forward');
    expect(spy).toHaveBeenCalledWith(
      '/api/control/flip',
      expect.objectContaining({
        body: JSON.stringify({ direction: 'forward' }),
      }),
    );
  });

  it('sendRc sends joystick values', async () => {
    const spy = mockFetch({ ok: true });
    await api.sendRc(10, -20, 30, -40);
    expect(spy).toHaveBeenCalledWith(
      '/api/control/rc',
      expect.objectContaining({
        body: JSON.stringify({ lr: 10, fb: -20, ud: 30, yaw: -40 }),
      }),
    );
  });

  it('getStatus fetches GET /api/status', async () => {
    const spy = mockFetch({ connected: true, flying: false, battery: 90 });
    const res = await api.getStatus();
    expect(spy).toHaveBeenCalledWith('/api/status');
    expect(res.connected).toBe(true);
  });

  it('getSequences fetches sequence list', async () => {
    const spy = mockFetch([{ id: 'patrol', name: 'Square Patrol', description: 'Fly square', steps: 8 }]);
    const res = await api.getSequences();
    expect(spy).toHaveBeenCalledWith('/api/sequences');
    expect(res).toHaveLength(1);
    expect(res[0].id).toBe('patrol');
  });

  it('runSequence sends POST with sequence id', async () => {
    const spy = mockFetch({ ok: true });
    await api.runSequence('patrol');
    expect(spy).toHaveBeenCalledWith('/api/sequences/patrol/run', expect.objectContaining({ method: 'POST' }));
  });

  it('cancelSequence sends POST', async () => {
    const spy = mockFetch({ ok: true });
    await api.cancelSequence();
    expect(spy).toHaveBeenCalledWith('/api/sequences/cancel', expect.objectContaining({ method: 'POST' }));
  });

  it('handles network errors gracefully', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network failure'));
    const res = await api.connectDrone();
    expect(res.ok).toBe(false);
  });

  it('handles HTTP error responses', async () => {
    mockFetch('Bad Request', false, 400);
    const res = await api.takeoff();
    expect(res.ok).toBe(false);
  });

  it('VIDEO_STREAM_URL is correct', () => {
    expect(api.VIDEO_STREAM_URL).toBe('/api/video/stream');
  });

  it('startVideoStream sends POST to /api/video/stream/start', async () => {
    const spy = mockFetch({ ok: true });
    const res = await api.startVideoStream();
    expect(spy).toHaveBeenCalledWith('/api/video/stream/start', expect.objectContaining({ method: 'POST' }));
    expect(res.ok).toBe(true);
  });

  it('stopVideoStream sends POST to /api/video/stream/stop', async () => {
    const spy = mockFetch({ ok: true });
    const res = await api.stopVideoStream();
    expect(spy).toHaveBeenCalledWith('/api/video/stream/stop', expect.objectContaining({ method: 'POST' }));
    expect(res.ok).toBe(true);
  });

  it('createSequence POSTs JSON and returns the saved sequence', async () => {
    const spy = mockFetch({ id: 'hop-1', name: 'Hop' }, true, 201);
    const draft = { name: 'Hop', description: '', auto_takeoff_land: true, steps: [{ type: 'wait' as const, seconds: 1 }] };
    const res = await api.createSequence(draft);
    expect(spy).toHaveBeenCalledWith('/api/sequences', expect.objectContaining({ method: 'POST', body: JSON.stringify(draft) }));
    expect(res.id).toBe('hop-1');
  });

  it('runDraft surfaces pre-flight problems as an error message', async () => {
    mockFetch({ detail: { message: 'Pre-flight check failed', problems: ['Battery is 20%'] } }, false, 409);
    await expect(api.runDraft({ name: 'x', description: '', auto_takeoff_land: true, steps: [] })).rejects.toThrow(
      'Battery is 20%',
    );
  });

  it('turns FastAPI validation errors into readable step messages', async () => {
    mockFetch({ detail: [{ loc: ['body', 'steps', 2, 'move', 'distance_cm'], msg: 'Input should be less than or equal to 500' }] }, false, 422);
    await expect(api.updateSequence('hop-1', { name: 'x', description: '', auto_takeoff_land: true, steps: [] })).rejects.toThrow(
      'Step 3: Input should be less than or equal to 500',
    );
  });

  it('abortSequence POSTs to /api/sequences/abort', async () => {
    const spy = mockFetch({ ok: true });
    await api.abortSequence();
    expect(spy).toHaveBeenCalledWith('/api/sequences/abort', expect.objectContaining({ method: 'POST' }));
  });
});
