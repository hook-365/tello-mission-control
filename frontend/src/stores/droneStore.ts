import { create } from 'zustand';
import type {
  ApiResponse,
  CommandLogEntry,
  ConnectionStatus,
  DetectionsData,
  KeyboardMode,
  MediaEvent,
  MediaItem,
  RcSticks,
  RecordingStatus,
  Sequence,
  SequenceProgress,
  TelemetryData,
  VisionState,
} from '@/types/drone';
import * as api from '@/lib/api';

const MAX_LOG_ENTRIES = 200;
const VISION_OFF: VisionState = { available: false, detecting: false, tracking: false };

export const NOT_RECORDING: RecordingStatus = { recording: false, name: null, elapsed_s: 0, started_at: null };

export interface StickInput {
  sticks: RcSticks;
  /** True while the dead-man is held (controller bumper, or a hold-to-fly key). */
  armed: boolean;
  source: 'gamepad' | 'keyboard' | null;
}

export const IDLE_STICKS: StickInput = {
  sticks: { lr: 0, fb: 0, ud: 0, yaw: 0 },
  armed: false,
  source: null,
};

function loadPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key) as T | null;
    return v && allowed.includes(v) ? v : fallback;
  } catch {
    return fallback;
  }
}

function savePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Private mode etc.: preference just isn't remembered
  }
}

interface DroneStore {
  // Connection
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;

  // Flight state
  isFlying: boolean;
  setIsFlying: (flying: boolean) => void;

  // Command lock
  commandPending: boolean;
  setCommandPending: (pending: boolean) => void;

  // Telemetry
  telemetry: TelemetryData | null;
  setTelemetry: (data: TelemetryData) => void;

  // Command log
  commandLog: CommandLogEntry[];
  addCommandLog: (entry: CommandLogEntry) => void;
  clearCommandLog: () => void;

  // Sequences
  sequences: Sequence[];
  setSequences: (sequences: Sequence[]) => void;
  refreshSequences: () => Promise<void>;
  sequenceProgress: SequenceProgress | null;
  setSequenceProgress: (progress: SequenceProgress | null) => void;

  // Control settings
  moveDistance: number;
  setMoveDistance: (d: number) => void;
  rotateAngle: number;
  setRotateAngle: (a: number) => void;

  // Stick flying (game controller / hold-to-fly keys)
  keyboardMode: KeyboardMode;
  setKeyboardMode: (m: KeyboardMode) => void;
  stickSpeed: number; // 20-100 % of max speed
  setStickSpeed: (pct: number) => void;
  gamepadName: string | null;
  setGamepadName: (name: string | null) => void;
  stickInput: StickInput;
  setStickInput: (input: StickInput) => void;
  rcError: string | null;
  setRcError: (e: string | null) => void;

  // Camera: saved photos and clips
  media: MediaItem[];
  recording: RecordingStatus;
  galleryOpen: boolean;
  setGalleryOpen: (open: boolean) => void;
  refreshMedia: () => Promise<void>;
  applyMediaEvent: (e: MediaEvent) => void;
  /** Newest item to briefly highlight in the gallery / show a toast for. */
  lastSaved: MediaItem | null;

  // Alerts
  alertsMuted: boolean;
  toggleAlertsMuted: () => void;

  // Vision (optional backend feature: detection overlay + tracking)
  vision: VisionState;
  setVision: (state: VisionState | null) => void;
  detections: DetectionsData | null;
  setDetections: (data: DetectionsData) => void;


  // UI state
  commandLogCollapsed: boolean;
  toggleCommandLog: () => void;
  previewMode: boolean;

  // Compound actions
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  enterPreview: () => void;
  sendCommand: (commandFn: () => Promise<ApiResponse>) => Promise<boolean>;
}

export const useDroneStore = create<DroneStore>((set, get) => ({
  // Connection
  connectionStatus: 'disconnected',
  setConnectionStatus: (status) => set({ connectionStatus: status }),

  // Flight state
  isFlying: false,
  setIsFlying: (flying) => set({ isFlying: flying }),

  // Command lock
  commandPending: false,
  setCommandPending: (pending) => set({ commandPending: pending }),

  // Telemetry
  telemetry: null,
  setTelemetry: (data) => set({ telemetry: data }),

  // Command log
  commandLog: [],
  addCommandLog: (entry) =>
    set((state) => ({
      commandLog: [...state.commandLog, entry].slice(-MAX_LOG_ENTRIES),
    })),
  clearCommandLog: () => set({ commandLog: [] }),

  // Sequences
  sequences: [],
  setSequences: (sequences) => set({ sequences }),
  refreshSequences: async () => {
    if (get().previewMode) return;
    try {
      set({ sequences: await api.getSequences() });
    } catch {
      // Non-critical: keep the current list
    }
  },
  sequenceProgress: null,
  setSequenceProgress: (progress) => set({ sequenceProgress: progress }),

  // Control settings
  moveDistance: 100,
  setMoveDistance: (d) => set({ moveDistance: Math.max(20, Math.min(500, d)) }),
  rotateAngle: 90,
  setRotateAngle: (a) => set({ rotateAngle: Math.max(1, Math.min(360, a)) }),

  // Stick flying
  keyboardMode: loadPref<KeyboardMode>('tello.keyboardMode', ['tap', 'hold'], 'tap'),
  setKeyboardMode: (m) => {
    savePref('tello.keyboardMode', m);
    set({ keyboardMode: m });
  },
  stickSpeed: Number(loadPref('tello.stickSpeed', ['20', '30', '40', '50', '60', '70', '80', '90', '100'], '50')),
  setStickSpeed: (pct) => {
    const v = Math.max(20, Math.min(100, Math.round(pct / 10) * 10));
    savePref('tello.stickSpeed', String(v));
    set({ stickSpeed: v });
  },
  gamepadName: null,
  setGamepadName: (name) => set({ gamepadName: name }),
  stickInput: IDLE_STICKS,
  setStickInput: (input) => set({ stickInput: input }),
  rcError: null,
  setRcError: (e) => set({ rcError: e }),

  // Camera
  media: [],
  recording: NOT_RECORDING,
  galleryOpen: false,
  setGalleryOpen: (open) => set({ galleryOpen: open }),
  lastSaved: null,
  refreshMedia: async () => {
    if (get().previewMode) return;
    try {
      const res = await api.getMedia();
      set({ media: res.items, recording: res.recording });
    } catch {
      // Keep what we have
    }
  },
  applyMediaEvent: (e) => {
    const addItem = (item: MediaItem) =>
      set((s) => ({ media: [item, ...s.media.filter((m) => m.name !== item.name)], lastSaved: item }));
    switch (e.event) {
      case 'photo':
        addItem(e.item);
        break;
      case 'recording_started':
        set({ recording: { recording: true, name: e.name, elapsed_s: e.elapsed_s, started_at: e.started_at } });
        break;
      case 'recording_stopped':
        set({ recording: NOT_RECORDING });
        if (e.item) addItem(e.item);
        break;
      case 'deleted':
        set((s) => ({ media: s.media.filter((m) => m.name !== e.name) }));
        break;
    }
  },

  // Alerts
  alertsMuted: false,
  toggleAlertsMuted: () => set((s) => ({ alertsMuted: !s.alertsMuted })),

  // Vision
  vision: VISION_OFF,
  setVision: (state) => set(state ? { vision: state } : {}),
  detections: null,
  // Each frame also carries the live on/off flags, so a tracking cancel shows at once.
  setDetections: (data) =>
    set((s) => ({
      detections: data.detecting ? data : null,
      vision: { ...s.vision, detecting: data.detecting, tracking: data.tracking },
    })),


  // UI state
  commandLogCollapsed: false,
  toggleCommandLog: () => set((s) => ({ commandLogCollapsed: !s.commandLogCollapsed })),
  previewMode: false,

  // Enter preview mode — shows HUD without drone connection
  enterPreview: () => {
    set({
      connectionStatus: 'connected',
      previewMode: true,
      isFlying: false,
      telemetry: null,
      commandLog: [],
      sequenceProgress: null,
    });
  },

  // Connect to drone
  connect: async () => {
    set({ connectionStatus: 'connecting' });
    try {
      const res = await api.connectDrone();
      if (res.ok && res.battery !== undefined) {
        set({
          connectionStatus: 'connected',
          telemetry: get().telemetry
            ? { ...get().telemetry!, battery: res.battery }
            : null,
        });
        // Start video stream (fire-and-forget, non-blocking)
        api.startVideoStream().catch(() => {});
        get().refreshMedia();
        // Is the optional vision feature present? Probing it must never fail the
        // connection, so both sync and async errors just leave the buttons hidden.
        try {
          api.getVision().then((vision) => set({ vision })).catch(() => {});
        } catch {
          // Non-critical
        }
        // Fetch available sequences
        try {
          const sequences = await api.getSequences();
          set({ sequences });
        } catch {
          // Non-critical — sequences panel just stays empty
        }
      } else {
        set({ connectionStatus: 'error' });
      }
    } catch {
      set({ connectionStatus: 'error' });
    }
  },

  // Disconnect from drone
  disconnect: async () => {
    const wasPreview = get().previewMode;
    if (!wasPreview) {
      // Stop video stream and disconnect (best effort)
      api.stopVideoStream().catch(() => {});
      try {
        await api.disconnectDrone();
      } catch {
        // Best effort
      }
    }
    set({
      connectionStatus: 'disconnected',
      isFlying: false,
      telemetry: null,
      sequenceProgress: null,
      commandPending: false,
      previewMode: false,
      recording: NOT_RECORDING,
      galleryOpen: false,
      vision: VISION_OFF,
      detections: null,
    });
  },

  // Generic command wrapper — prevents double-sends
  sendCommand: async (commandFn) => {
    if (get().commandPending) return false;

    set({ commandPending: true });
    try {
      const res = await commandFn();
      return res.ok;
    } catch {
      return false;
    } finally {
      set({ commandPending: false });
    }
  },
}));
