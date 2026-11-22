import { describe, it, expect, vi, beforeEach } from 'vitest';
import { defaultStep, describeStep, emptyDraft, needsCamera, validateDraft } from '@/lib/sequence';
import { NOT_RECORDING, useDroneStore } from '@/stores/droneStore';
import type { MediaItem, SequenceDraft } from '@/types/drone';

vi.mock('@/lib/api', () => ({ getMedia: vi.fn() }));

const draft = (over: Partial<SequenceDraft>): SequenceDraft => ({ ...emptyDraft(), name: 'Test', ...over });
const photo: MediaItem = { name: 'photo-1.jpg', kind: 'photo', size_bytes: 1000, created_at: '2026-01-01T00:00:00Z', url: '/x' };
const clip: MediaItem = { ...photo, name: 'clip-1.mp4', kind: 'clip', duration_s: 4 };

describe('camera sequence steps', () => {
  it('describes the new steps like the backend', () => {
    expect(describeStep(defaultStep('photo'))).toBe('Take photo');
    expect(describeStep({ type: 'record', action: 'stop' })).toBe('Stop recording');
    expect(describeStep(defaultStep('orbit'))).toBe('Orbit right 360° around a point 150 cm ahead');
    expect(describeStep({ type: 'glide', forward_cm: -200, right_cm: 0, up_cm: 120, speed_cm_s: 25 })).toBe(
      'Glide back 200, up 120 cm',
    );
  });

  it('allows photo and record on the ground but not orbit or glide', () => {
    const ground = draft({
      auto_takeoff_land: false,
      steps: [defaultStep('record'), defaultStep('photo'), defaultStep('glide')],
    });
    const errors = validateDraft(ground);
    expect(errors).toContain('Step 3: needs the drone in the air (add a takeoff first)');
    expect(errors.some((e) => e.startsWith('Step 1') || e.startsWith('Step 2'))).toBe(false);
  });

  it('checks orbit and glide limits', () => {
    const errors = validateDraft(
      draft({
        steps: [
          { type: 'orbit', direction: 'left', radius_cm: 20, degrees: 400, speed_cm_s: 80 },
          { type: 'glide', forward_cm: 10, right_cm: -5, up_cm: 20, speed_cm_s: 30 },
          { type: 'glide', forward_cm: 900, right_cm: 0, up_cm: 0, speed_cm_s: 5 },
        ],
      }),
    );
    expect(errors).toEqual([
      'Step 1: orbit distance must be 50-300 cm',
      'Step 1: orbit must be 30-360°',
      'Step 1: orbit speed must be 10-60 cm/s',
      'Step 2: glide needs at least one distance over 20 cm',
      'Step 3: glide distances must be -500 to 500 cm',
      'Step 3: glide speed must be 10-100 cm/s',
    ]);
    expect(validateDraft(draft({ steps: [defaultStep('orbit'), defaultStep('glide')] }))).toEqual([]);
  });

  it('knows when the camera is needed', () => {
    expect(needsCamera(draft({ steps: [defaultStep('orbit')] }))).toBe(false);
    expect(needsCamera(draft({ steps: [defaultStep('orbit'), defaultStep('record')] }))).toBe(true);
  });
});

describe('media store events', () => {
  beforeEach(() => useDroneStore.setState({ media: [], recording: NOT_RECORDING, lastSaved: null }));

  it('tracks photos, recording and deletes', () => {
    const { applyMediaEvent } = useDroneStore.getState();
    applyMediaEvent({ event: 'photo', item: photo });
    applyMediaEvent({ event: 'recording_started', recording: true, name: 'clip-1.mp4', elapsed_s: 0, started_at: 'now' });
    expect(useDroneStore.getState().recording.recording).toBe(true);
    applyMediaEvent({ event: 'recording_stopped', item: clip });
    let s = useDroneStore.getState();
    expect(s.recording).toEqual(NOT_RECORDING);
    expect(s.media.map((m) => m.name)).toEqual(['clip-1.mp4', 'photo-1.jpg']);
    expect(s.lastSaved?.name).toBe('clip-1.mp4');
    applyMediaEvent({ event: 'photo', item: photo }); // duplicate event doesn't double up
    applyMediaEvent({ event: 'deleted', name: 'clip-1.mp4' });
    s = useDroneStore.getState();
    expect(s.media.map((m) => m.name)).toEqual(['photo-1.jpg']);
  });

  it('a failed recording clears the REC state without adding anything', () => {
    useDroneStore.setState({ recording: { recording: true, name: 'x', elapsed_s: 1, started_at: null } });
    useDroneStore.getState().applyMediaEvent({ event: 'recording_stopped', item: null });
    expect(useDroneStore.getState().recording.recording).toBe(false);
    expect(useDroneStore.getState().media).toEqual([]);
  });
});
