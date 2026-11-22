import type { RcSticks } from '@/types/drone';

/**
 * Game controller / keyboard -> Tello stick values.
 *
 * Layout is "Mode 2", the usual drone layout:
 *   left stick:  up/down (throttle) and spin (yaw)
 *   right stick: forward/back and left/right
 * Hold either bumper (LB / RB) to fly: let go and the drone stops and hovers.
 * Hold the bumper and press Start (Menu) to take off. Back (View) lands.
 * Click BOTH sticks in together (L3 + R3) for an emergency motor stop.
 */

export const DEADZONE = 0.12;

/** W3C "standard" gamepad mapping indices. */
export const PAD = {
  A: 0, B: 1, X: 2, Y: 3,
  LB: 4, RB: 5, LT: 6, RT: 7,
  BACK: 8, START: 9, L3: 10, R3: 11,
} as const;

export const ZERO: RcSticks = { lr: 0, fb: 0, ud: 0, yaw: 0 };

/**
 * Deadzone + gentle expo: small stick moves give fine control, full stick
 * still gives full speed. Returns -1..1.
 */
export function shapeAxis(v: number, dz = DEADZONE): number {
  if (!Number.isFinite(v)) return 0;
  const a = Math.min(1, Math.abs(v));
  if (a < dz) return 0;
  const s = (a - dz) / (1 - dz);
  const shaped = 0.35 * s + 0.65 * s * s * s;
  return Math.sign(v) * shaped;
}

export interface PadReading {
  /** Unit sticks, -1..1 per axis */
  sticks: RcSticks;
  armed: boolean;
  takeoff: boolean;
  land: boolean;
  emergency: boolean;
}

export function readPad(axes: readonly number[], pressed: (i: number) => boolean): PadReading {
  const armed = pressed(PAD.LB) || pressed(PAD.RB);
  return {
    sticks: {
      yaw: shapeAxis(axes[0] ?? 0),
      ud: -shapeAxis(axes[1] ?? 0) || 0, // stick up = climb (axis is negative when pushed up)
      lr: shapeAxis(axes[2] ?? 0),
      fb: -shapeAxis(axes[3] ?? 0) || 0,
    },
    armed,
    takeoff: armed && pressed(PAD.START),
    land: pressed(PAD.BACK),
    emergency: pressed(PAD.L3) && pressed(PAD.R3),
  };
}

/** Hold-to-fly keys (same keys as tap mode). Values are unit sticks. */
export const HOLD_KEYS: Record<string, [keyof RcSticks, number]> = {
  w: ['fb', 1],
  s: ['fb', -1],
  a: ['lr', -1],
  d: ['lr', 1],
  ' ': ['ud', 1],
  shift: ['ud', -1],
  q: ['yaw', -1],
  e: ['yaw', 1],
};

export function keysToSticks(keys: Iterable<string>): RcSticks {
  const out = { ...ZERO };
  for (const k of keys) {
    const m = HOLD_KEYS[k];
    if (m) out[m[0]] += m[1];
  }
  for (const k of Object.keys(out) as (keyof RcSticks)[]) out[k] = Math.max(-1, Math.min(1, out[k]));
  return out;
}

/** Unit sticks -> integer -100..100 at the chosen speed (percent). */
export function scaleSticks(s: RcSticks, speedPct: number): RcSticks {
  const f = Math.max(0, Math.min(100, speedPct));
  const c = (v: number) => {
    const r = Math.round(v * f);
    return r === 0 ? 0 : Math.max(-100, Math.min(100, r)); // avoid -0
  };
  return { lr: c(s.lr), fb: c(s.fb), ud: c(s.ud), yaw: c(s.yaw) };
}

export function isZero(s: RcSticks): boolean {
  return s.lr === 0 && s.fb === 0 && s.ud === 0 && s.yaw === 0;
}

export function sameSticks(a: RcSticks, b: RcSticks): boolean {
  return a.lr === b.lr && a.fb === b.fb && a.ud === b.ud && a.yaw === b.yaw;
}
