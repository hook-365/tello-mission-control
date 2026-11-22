import type {
  FlipDirection,
  MoveDirection,
  RotateDirection,
  SequenceDraft,
  SequenceStep,
  StepType,
} from '@/types/drone';

// Limits mirror backend/app/models/sequences.py
export const LIMITS = {
  distance: { min: 20, max: 500, step: 10 },
  angle: { min: 1, max: 360, step: 15 },
  seconds: { min: 0.5, max: 10, step: 0.5 },
  radius: { min: 50, max: 300, step: 10 },
  orbitDegrees: { min: 30, max: 360, step: 30 },
  orbitSpeed: { min: 10, max: 60, step: 5 },
  glide: { min: -500, max: 500, step: 10 },
  glideSpeed: { min: 10, max: 100, step: 5 },
  maxSteps: 50,
  nameMax: 60,
} as const;

export const MOVE_DIRECTIONS: MoveDirection[] = ['forward', 'back', 'left', 'right', 'up', 'down'];
export const ROTATE_DIRECTIONS: { value: RotateDirection; label: string }[] = [
  { value: 'cw', label: 'clockwise' },
  { value: 'ccw', label: 'counter-clockwise' },
];
export const FLIP_DIRECTIONS: FlipDirection[] = ['forward', 'back', 'left', 'right'];

export const STEP_LABELS: Record<StepType, string> = {
  takeoff: 'Take off',
  land: 'Land',
  move: 'Move',
  rotate: 'Spin',
  flip: 'Flip',
  wait: 'Hover',
  photo: 'Photo',
  record: 'Record',
  orbit: 'Orbit',
  glide: 'Glide',
};

/** Steps that work on the ground too (they don't move the drone). */
const GROUND_OK: StepType[] = ['wait', 'photo', 'record'];

export function defaultStep(type: StepType): SequenceStep {
  switch (type) {
    case 'move':
      return { type, direction: 'forward', distance_cm: 100 };
    case 'rotate':
      return { type, direction: 'cw', angle_deg: 360 };
    case 'flip':
      return { type, direction: 'back' };
    case 'wait':
      return { type, seconds: 2 };
    case 'takeoff':
      return { type };
    case 'land':
      return { type };
    case 'photo':
      return { type };
    case 'record':
      return { type, action: 'start' };
    case 'orbit':
      return { type, direction: 'right', radius_cm: 150, degrees: 360, speed_cm_s: 30 };
    case 'glide':
      return { type, forward_cm: -150, right_cm: 0, up_cm: 100, speed_cm_s: 30 };
  }
}

export function emptyDraft(): SequenceDraft {
  return { name: '', description: '', auto_takeoff_land: true, steps: [] };
}

export function describeStep(step: SequenceStep): string {
  switch (step.type) {
    case 'takeoff':
      return 'Take off';
    case 'land':
      return 'Land';
    case 'move':
      return `${cap(step.direction)} ${step.distance_cm} cm`;
    case 'rotate':
      return `Spin ${step.direction === 'cw' ? 'clockwise' : 'counter-clockwise'} ${step.angle_deg}°`;
    case 'flip':
      return `Flip ${step.direction}`;
    case 'wait':
      return `Hover ${step.seconds} s`;
    case 'photo':
      return 'Take photo';
    case 'record':
      return step.action === 'start' ? 'Start recording' : 'Stop recording';
    case 'orbit':
      return `Orbit ${step.direction} ${step.degrees}° around a point ${step.radius_cm} cm ahead`;
    case 'glide':
      return `Glide ${glideWords(step)}`;
  }
}

function glideWords(step: { forward_cm: number; right_cm: number; up_cm: number }): string {
  const parts: string[] = [];
  const axes: [number, string, string][] = [
    [step.forward_cm, 'forward', 'back'],
    [step.right_cm, 'right', 'left'],
    [step.up_cm, 'up', 'down'],
  ];
  for (const [v, pos, neg] of axes) if (v) parts.push(`${v > 0 ? pos : neg} ${Math.abs(v)}`);
  return `${parts.join(', ') || 'nowhere'} cm`;
}

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function inRange(v: number, r: { min: number; max: number }) {
  return Number.isFinite(v) && v >= r.min && v <= r.max;
}

/** Client-side checks; the backend re-validates everything. */
export function validateDraft(draft: SequenceDraft): string[] {
  const errors: string[] = [];
  if (!draft.name.trim()) errors.push('Give it a name');
  if (draft.steps.length === 0) errors.push('Add at least one step');
  if (draft.steps.length > LIMITS.maxSteps) errors.push(`Max ${LIMITS.maxSteps} steps`);

  draft.steps.forEach((s, i) => {
    const n = `Step ${i + 1}`;
    if (s.type === 'move' && !inRange(s.distance_cm, LIMITS.distance))
      errors.push(`${n}: distance must be ${LIMITS.distance.min}-${LIMITS.distance.max} cm`);
    if (s.type === 'rotate' && !inRange(s.angle_deg, LIMITS.angle))
      errors.push(`${n}: angle must be ${LIMITS.angle.min}-${LIMITS.angle.max}°`);
    if (s.type === 'wait' && !inRange(s.seconds, LIMITS.seconds))
      errors.push(`${n}: hover must be ${LIMITS.seconds.min}-${LIMITS.seconds.max} s`);
    if (s.type === 'orbit') {
      if (!inRange(s.radius_cm, LIMITS.radius))
        errors.push(`${n}: orbit distance must be ${LIMITS.radius.min}-${LIMITS.radius.max} cm`);
      if (!inRange(s.degrees, LIMITS.orbitDegrees))
        errors.push(`${n}: orbit must be ${LIMITS.orbitDegrees.min}-${LIMITS.orbitDegrees.max}°`);
      if (!inRange(s.speed_cm_s, LIMITS.orbitSpeed))
        errors.push(`${n}: orbit speed must be ${LIMITS.orbitSpeed.min}-${LIMITS.orbitSpeed.max} cm/s`);
    }
    if (s.type === 'glide') {
      const d = [s.forward_cm, s.right_cm, s.up_cm];
      if (!d.every((v) => inRange(v, LIMITS.glide)))
        errors.push(`${n}: glide distances must be ${LIMITS.glide.min} to ${LIMITS.glide.max} cm`);
      else if (d.every((v) => Math.abs(v) <= 20)) errors.push(`${n}: glide needs at least one distance over 20 cm`);
      if (!inRange(s.speed_cm_s, LIMITS.glideSpeed))
        errors.push(`${n}: glide speed must be ${LIMITS.glideSpeed.min}-${LIMITS.glideSpeed.max} cm/s`);
    }
  });

  // Simulate airborne state (same rules as the backend)
  let flying = draft.auto_takeoff_land && draft.steps[0]?.type !== 'takeoff';
  draft.steps.forEach((s, i) => {
    const n = `Step ${i + 1}`;
    if (s.type === 'takeoff') {
      if (flying) errors.push(`${n}: already in the air`);
      flying = true;
    } else if (s.type === 'land') {
      if (!flying) errors.push(`${n}: already on the ground`);
      flying = false;
    } else if (!GROUND_OK.includes(s.type) && !flying) {
      errors.push(`${n}: needs the drone in the air (add a takeoff first)`);
    }
  });
  if (flying && !draft.auto_takeoff_land && draft.steps.length > 0)
    errors.push('Ends in the air: add a land step or turn on auto takeoff/land');

  return errors;
}

/** The backend switches the camera on first for these. */
export function needsCamera(draft: SequenceDraft): boolean {
  return draft.steps.some((s) => s.type === 'photo' || s.type === 'record');
}

export function hasFlips(draft: SequenceDraft): boolean {
  return draft.steps.some((s) => s.type === 'flip');
}
