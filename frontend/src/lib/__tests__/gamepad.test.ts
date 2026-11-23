import { describe, it, expect } from 'vitest';
import { axesToRc, axisToVelocity, isZeroRc, RC_ZERO } from '@/lib/gamepad';

describe('axisToVelocity', () => {
  it('returns 0 inside the deadzone', () => {
    expect(axisToVelocity(0.05, 100)).toBe(0);
    expect(axisToVelocity(-0.1, 100)).toBe(0);
  });

  it('never returns negative zero', () => {
    expect(Object.is(axisToVelocity(-0.05, 100), 0)).toBe(true);
  });

  it('reaches the cap at full deflection in both directions', () => {
    expect(axisToVelocity(1, 60)).toBe(60);
    expect(axisToVelocity(-1, 60)).toBe(-60);
  });

  it('ramps from zero at the deadzone edge instead of jumping', () => {
    expect(axisToVelocity(0.13, 100, 0.12)).toBeLessThanOrEqual(2);
  });

  it('clamps over-range and ignores non-finite input', () => {
    expect(axisToVelocity(1.4, 50)).toBe(50);
    expect(axisToVelocity(NaN, 50)).toBe(0);
  });
});

describe('axesToRc', () => {
  it('is all zero with centred sticks', () => {
    expect(axesToRc([0, 0, 0, 0], 100)).toEqual(RC_ZERO);
    expect(isZeroRc(axesToRc([0.02, -0.03, 0.01, 0], 100))).toBe(true);
  });

  it('maps left stick to throttle and yaw', () => {
    expect(axesToRc([0, -1, 0, 0], 100)).toEqual({ ...RC_ZERO, ud: 100 }); // stick up = climb
    expect(axesToRc([0, 1, 0, 0], 100)).toEqual({ ...RC_ZERO, ud: -100 });
    expect(axesToRc([1, 0, 0, 0], 100)).toEqual({ ...RC_ZERO, yaw: 100 }); // stick right = clockwise
  });

  it('maps right stick to forward/back and left/right', () => {
    expect(axesToRc([0, 0, 0, -1], 100)).toEqual({ ...RC_ZERO, fb: 100 }); // stick up = forward
    expect(axesToRc([0, 0, -1, 0], 100)).toEqual({ ...RC_ZERO, lr: -100 }); // stick left = left
  });

  it('applies the speed cap and clamps it to 0..100', () => {
    expect(axesToRc([0, 0, 0, -1], 40).fb).toBe(40);
    expect(axesToRc([0, 0, 0, -1], 250).fb).toBe(100);
    expect(axesToRc([0, 0, 0, -1], -5).fb).toBe(0);
  });

  it('tolerates gamepads reporting fewer than four axes', () => {
    expect(axesToRc([0, -1], 100)).toEqual({ ...RC_ZERO, ud: 100 });
  });
});
