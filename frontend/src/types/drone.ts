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
}

export interface CommandLogEntry {
  command: string;
  params: Record<string, unknown>;
  result: 'ok' | 'error';
  timestamp: string;
  error?: string;
}

export interface Sequence {
  id: string;
  name: string;
  description: string;
  steps: number;
}

export interface SequenceProgress {
  sequence_id: string;
  current_step: number;
  total_steps: number;
  step_description: string;
  status: 'running' | 'completed' | 'cancelled' | 'error';
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
}

/** A detected object. Box is normalised to the video frame: 0..1, origin top-left. */
export interface Detection {
  label: string;
  confidence: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DetectionsData {
  detections: Detection[];
  /** The box being followed, when tracking. */
  target: Detection | null;
  detecting: boolean;
  tracking: boolean;
  /** True when the video stream has stalled, so nothing can be detected. */
  stale: boolean;
  frame_width: number | null;
  frame_height: number | null;
}

export interface VisionState {
  /** False when the backend runs without the optional vision feature. */
  available: boolean;
  detecting: boolean;
  tracking: boolean;
  target?: string;
  hz?: number;
}

export interface WsMessage {
  type: 'telemetry' | 'command_log' | 'sequence_progress' | 'detections';
  data: TelemetryData | CommandLogEntry | SequenceProgress | DetectionsData;
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
