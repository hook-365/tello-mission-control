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
};

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
  }
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
    } else if (s.type !== 'wait' && !flying) {
      errors.push(`${n}: needs the drone in the air (add a takeoff first)`);
    }
  });
  if (flying && !draft.auto_takeoff_land && draft.steps.length > 0)
    errors.push('Ends in the air: add a land step or turn on auto takeoff/land');

  return errors;
}

export function hasFlips(draft: SequenceDraft): boolean {
  return draft.steps.some((s) => s.type === 'flip');
}
