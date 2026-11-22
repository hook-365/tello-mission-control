import { describe, it, expect } from 'vitest';
import { defaultStep, describeStep, emptyDraft, validateDraft } from '@/lib/sequence';
import type { SequenceDraft } from '@/types/drone';

const draft = (over: Partial<SequenceDraft>): SequenceDraft => ({ ...emptyDraft(), name: 'Test', ...over });

describe('sequence helpers', () => {
  it('accepts a simple auto takeoff/land sequence', () => {
    expect(validateDraft(draft({ steps: [defaultStep('move'), defaultStep('flip')] }))).toEqual([]);
  });

  it('requires a name and steps', () => {
    expect(validateDraft(emptyDraft())).toEqual(['Give it a name', 'Add at least one step']);
  });

  it('flags out-of-range parameters', () => {
    const errors = validateDraft(
      draft({
        steps: [
          { type: 'move', direction: 'up', distance_cm: 10 },
          { type: 'rotate', direction: 'cw', angle_deg: 400 },
          { type: 'wait', seconds: Number.NaN },
        ],
      }),
    );
    expect(errors).toHaveLength(3);
    expect(errors[0]).toMatch(/Step 1: distance/);
  });

  it('checks flight order when auto takeoff/land is off', () => {
    expect(validateDraft(draft({ auto_takeoff_land: false, steps: [defaultStep('move')] })).join(' ')).toMatch(
      /needs the drone in the air/,
    );
    expect(
      validateDraft(draft({ auto_takeoff_land: false, steps: [defaultStep('takeoff'), defaultStep('move')] })).join(' '),
    ).toMatch(/Ends in the air/);
    expect(
      validateDraft(draft({ auto_takeoff_land: false, steps: [defaultStep('takeoff'), defaultStep('move'), defaultStep('land')] })),
    ).toEqual([]);
  });

  it('describes steps in plain words', () => {
    expect(describeStep({ type: 'rotate', direction: 'ccw', angle_deg: 90 })).toBe('Spin counter-clockwise 90°');
    expect(describeStep({ type: 'move', direction: 'up', distance_cm: 50 })).toBe('Up 50 cm');
  });
});
