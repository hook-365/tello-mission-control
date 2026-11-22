import { describe, it, expect } from 'vitest';
import { PAD, isZero, keysToSticks, readPad, scaleSticks, shapeAxis } from '@/lib/sticks';

const pressedSet = (...ids: number[]) => (i: number) => ids.includes(i);

describe('sticks', () => {
  it('ignores stick drift inside the deadzone', () => {
    expect(shapeAxis(0.05)).toBe(0);
    expect(shapeAxis(-0.11)).toBe(0);
    expect(shapeAxis(NaN)).toBe(0);
  });

  it('reaches full speed at full stick and is gentle near centre', () => {
    expect(shapeAxis(1)).toBeCloseTo(1);
    expect(shapeAxis(-1)).toBeCloseTo(-1);
    expect(shapeAxis(1.3)).toBeCloseTo(1);
    const half = shapeAxis(0.5);
    expect(half).toBeGreaterThan(0);
    expect(half).toBeLessThan(0.4); // expo: half stick is well under half speed
  });

  it('maps Mode 2 axes with stick-up meaning climb / forward', () => {
    const r = readPad([0.8, -1, -1, -1], pressedSet(PAD.RB));
    expect(r.armed).toBe(true);
    expect(r.sticks.yaw).toBeGreaterThan(0);
    expect(r.sticks.ud).toBeCloseTo(1);
    expect(r.sticks.lr).toBeCloseTo(-1);
    expect(r.sticks.fb).toBeCloseTo(1);
  });

  it('is not armed without a bumper, and buttons need their combos', () => {
    const idle = readPad([0, 0, 0, 0], pressedSet(PAD.START, PAD.L3));
    expect(idle.armed).toBe(false);
    expect(idle.takeoff).toBe(false); // Start alone does not take off
    expect(idle.emergency).toBe(false); // one stick click is not enough
    expect(readPad([], pressedSet(PAD.LB, PAD.START)).takeoff).toBe(true);
    expect(readPad([], pressedSet(PAD.L3, PAD.R3)).emergency).toBe(true);
    expect(readPad([], pressedSet(PAD.BACK)).land).toBe(true);
  });

  it('turns held keys into sticks and cancels opposites', () => {
    expect(keysToSticks(['w', 'd', 'e'])).toEqual({ lr: 1, fb: 1, ud: 0, yaw: 1 });
    expect(keysToSticks(['w', 's'])).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
    expect(keysToSticks([' ', 'shift'])).toEqual({ lr: 0, fb: 0, ud: 0, yaw: 0 });
  });

  it('scales to whole -100..100 values at the chosen speed', () => {
    expect(scaleSticks({ lr: 1, fb: -0.5, ud: 0, yaw: -1 }, 60)).toEqual({ lr: 60, fb: -30, ud: 0, yaw: -60 });
    const z = scaleSticks({ lr: -0.001, fb: 0, ud: 0, yaw: 0 }, 50);
    expect(Object.is(z.lr, -0)).toBe(false);
    expect(isZero(z)).toBe(true);
  });
});
