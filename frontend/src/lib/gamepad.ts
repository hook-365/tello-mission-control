export interface RcFrame {
  lr: number;
  fb: number;
  ud: number;
  yaw: number;
}

export const RC_ZERO: RcFrame = { lr: 0, fb: 0, ud: 0, yaw: 0 };

/** Stick travel below this is treated as centred (worn sticks rarely rest at 0). */
export const STICK_DEADZONE = 0.12;

/** Button indices in the W3C "standard" gamepad mapping. */
export const GAMEPAD_BUTTON = {
  takeoff: 0, // A / Cross
  land: 1, // B / Circle
  emergency: 8, // Back / Select / Share
} as const;

/**
 * Map one stick axis (-1..1) to a velocity (-cap..cap).
 * The deadzone is rescaled out so output ramps from 0 at its edge, not from a jump.
 */
export function axisToVelocity(value: number, cap: number, deadzone = STICK_DEADZONE): number {
  if (!Number.isFinite(value)) return 0;
  const magnitude = Math.min(1, Math.abs(value));
  if (magnitude <= deadzone) return 0;
  const scaled = (magnitude - deadzone) / (1 - deadzone);
  // `|| 0` normalises -0 so a centred stick always compares equal to RC_ZERO.
  return Math.round(Math.sign(value) * scaled * cap) || 0;
}

/**
 * Mode 2 layout on a standard-mapped gamepad:
 * left stick = throttle (up/down) + yaw, right stick = pitch (forward/back) + roll (left/right).
 * Stick-up reports a negative axis value, hence the sign flips.
 */
export function axesToRc(axes: readonly number[], cap: number, deadzone = STICK_DEADZONE): RcFrame {
  const limit = Math.max(0, Math.min(100, cap));
  return {
    yaw: axisToVelocity(axes[0] ?? 0, limit, deadzone),
    ud: axisToVelocity(-(axes[1] ?? 0), limit, deadzone),
    lr: axisToVelocity(axes[2] ?? 0, limit, deadzone),
    fb: axisToVelocity(-(axes[3] ?? 0), limit, deadzone),
  };
}

export function isZeroRc(rc: RcFrame): boolean {
  return rc.lr === 0 && rc.fb === 0 && rc.ud === 0 && rc.yaw === 0;
}
