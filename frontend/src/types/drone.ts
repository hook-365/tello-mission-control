export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface TelemetryData {
  battery: number;
  height: number;
  flight_time: number;
  temperature: { high: number; low: number };
  attitude: { pitch: number; roll: number; yaw: number };
  speed: { x: number; y: number; z: number };
  barometer: number;
  tof_distance: number;
  /** Wi-Fi signal-to-noise from the drone ("wifi?"), higher is better; null until first read. */
  wifi_snr?: number | null;
  /** Alert levels computed by the backend from its configured thresholds. */
  battery_level?: BatteryAlertLevel;
  signal_level?: SignalAlertLevel;
}

export type BatteryAlertLevel = 'ok' | 'low' | 'critical';
export type SignalAlertLevel = 'ok' | 'weak' | 'critical' | 'unknown';

/** Stick input, each axis -100..100 (percent of max speed). */
export interface RcSticks {
  lr: number;
  fb: number;
  ud: number;
  yaw: number;
}

export type KeyboardMode = 'tap' | 'hold';

export interface CommandLogEntry {
  command: string;
  params: Record<string, unknown>;
  result: 'ok' | 'error';
  timestamp: string;
  error?: string;
}

// ---- Flight sequencer ----

export type SequenceStep =
  | { type: 'takeoff' }
  | { type: 'land' }
  | { type: 'move'; direction: MoveDirection; distance_cm: number }
  | { type: 'rotate'; direction: RotateDirection; angle_deg: number }
  | { type: 'flip'; direction: FlipDirection }
  | { type: 'wait'; seconds: number }
  | { type: 'photo' }
  | { type: 'record'; action: 'start' | 'stop' }
  | {
      type: 'orbit';
      direction: 'left' | 'right';
      radius_cm: number;
      degrees: number;
      speed_cm_s: number;
    }
  | { type: 'glide'; forward_cm: number; right_cm: number; up_cm: number; speed_cm_s: number };

export type StepType = SequenceStep['type'];

/** A sequence as sent to the backend (create / update / run unsaved). */
export interface SequenceDraft {
  name: string;
  description: string;
  auto_takeoff_land: boolean;
  steps: SequenceStep[];
}

/** A saved sequence as returned by the backend. */
export interface Sequence extends SequenceDraft {
  id: string;
  builtin: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export type RunState = 'idle' | 'running' | 'completed' | 'aborted' | 'failed';

/** Live run status (GET /api/sequences/run/status and `sequence_progress` WS events). */
export interface SequenceProgress {
  run_id?: string | null;
  sequence_id: string | null;
  sequence_name?: string | null;
  status: RunState;
  current_step: number;
  total_steps: number;
  /** Index into the sequence's own steps; null for automatic takeoff/land. */
  step_index?: number | null;
  step_description: string;
  message?: string;
}

export type MoveDirection = 'forward' | 'back' | 'left' | 'right' | 'up' | 'down';
export type RotateDirection = 'cw' | 'ccw';
export type FlipDirection = 'forward' | 'back' | 'left' | 'right';

export interface ApiResponse {
  ok: boolean;
  message?: string;
  error?: string;
}

export interface ConnectResponse {
  ok: boolean;
  status: string;
  battery: number;
}

export interface StatusResponse {
  connected: boolean;
  flying: boolean;
  streaming: boolean;
  battery: number;
  wifi_snr?: number | null;
}

// ---- Camera: photos and clips saved on the host ----

export interface MediaItem {
  name: string;
  kind: 'photo' | 'clip';
  size_bytes: number;
  created_at: string;
  duration_s?: number | null;
  /** Where to load it from; null in the demo for clips it can't play. */
  url: string | null;
}

export interface RecordingStatus {
  recording: boolean;
  name: string | null;
  elapsed_s: number;
  started_at: string | null;
}

export interface MediaListResponse {
  items: MediaItem[];
  recording: RecordingStatus;
}

/** `media` WebSocket events. */
export type MediaEvent =
  | { event: 'photo'; item: MediaItem }
  | ({ event: 'recording_started' } & RecordingStatus)
  | { event: 'recording_stopped'; item: MediaItem | null }
  | { event: 'deleted'; name: string };

export interface WsMessage {
  type: 'telemetry' | 'command_log' | 'sequence_progress' | 'media';
  data: TelemetryData | CommandLogEntry | SequenceProgress | MediaEvent;
  timestamp?: string;
}

export interface FlightSummary {
  id: number;
  started_at: string;
  ended_at: string | null;
  telemetry_frames: number;
  commands: number;
  /** True while this session is still being recorded. */
  active: boolean;
}

export interface TelemetrySample {
  timestamp: string;
  data: TelemetryData;
}

export interface FlightDetail extends FlightSummary {
  telemetry: TelemetrySample[];
  command_log: CommandLogEntry[];
}
