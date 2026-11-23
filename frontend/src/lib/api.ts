import type {
  ApiResponse,
  ConnectResponse,
  FlightDetail,
  FlightSummary,
  FlipDirection,
  MediaItem,
  MediaListResponse,
  MoveDirection,
  RecordingStatus,
  RotateDirection,
  Sequence,
  SequenceDraft,
  SequenceProgress,
  StatusResponse,
} from '@/types/drone';

export const VIDEO_STREAM_URL = '/api/video/stream';

async function post<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error');
      return { ok: false, error: `HTTP ${res.status}: ${text}` } as T;
    }
    return await res.json();
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Network error' } as T;
  }
}

/** For endpoints whose 4xx bodies carry useful detail (validation, pre-flight checks). */
export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

function detailToMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    // FastAPI 422: [{loc, msg}, ...]
    return detail
      .map((d) => {
        const msg = String(d?.msg ?? d).replace(/^Value error, /, '');
        const loc = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== 'body') : [];
        const stepIdx = loc[0] === 'steps' && typeof loc[1] === 'number' ? `Step ${loc[1] + 1}: ` : '';
        return stepIdx + msg;
      })
      .join('\n');
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { message?: string; problems?: string[] };
    if (d.problems?.length) return d.problems.join('\n');
    if (d.message) return d.message;
  }
  return 'Request failed';
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    throw new ApiError(err instanceof Error ? err.message : 'Network error', 0);
  }
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      message = detailToMessage((await res.json()).detail);
    } catch {
      // keep the status text
    }
    throw new ApiError(message, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  try {
    const res = await fetch(path);
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error('Network error');
  }
}

export function connectDrone(): Promise<ConnectResponse> {
  return post<ConnectResponse>('/api/control/connect');
}

export function disconnectDrone(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/disconnect');
}

export function takeoff(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/takeoff');
}

export function land(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/land');
}

export function emergencyStop(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/emergency');
}

export function move(direction: MoveDirection, distance_cm: number): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/move', { direction, distance_cm });
}

export function rotate(direction: RotateDirection, angle_deg: number): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/rotate', { direction, angle_deg });
}

export function flip(direction: FlipDirection): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/flip', { direction });
}

export function sendRc(lr: number, fb: number, ud: number, yaw: number): Promise<ApiResponse> {
  return post<ApiResponse>('/api/control/rc', { lr, fb, ud, yaw });
}

export function getStatus(): Promise<StatusResponse> {
  return get<StatusResponse>('/api/status');
}

export async function takeSnapshot(): Promise<Blob> {
  const res = await fetch('/api/video/snapshot', { method: 'POST' });
  if (!res.ok) {
    throw new Error(`Snapshot failed: HTTP ${res.status}`);
  }
  return res.blob();
}

export function getSequences(): Promise<Sequence[]> {
  return get<Sequence[]>('/api/sequences');
}

export function createSequence(seq: SequenceDraft): Promise<Sequence> {
  return request<Sequence>('POST', '/api/sequences', seq);
}

export function updateSequence(id: string, seq: SequenceDraft): Promise<Sequence> {
  return request<Sequence>('PUT', `/api/sequences/${encodeURIComponent(id)}`, seq);
}

export function deleteSequence(id: string): Promise<void> {
  return request<void>('DELETE', `/api/sequences/${encodeURIComponent(id)}`);
}

/** Start a saved sequence. Throws ApiError with pre-flight problems on 409. */
export function runSequence(id: string): Promise<SequenceProgress> {
  return request<SequenceProgress>('POST', `/api/sequences/${encodeURIComponent(id)}/run`);
}

/** Start an unsaved sequence straight from the builder. */
export function runDraft(seq: SequenceDraft): Promise<SequenceProgress> {
  return request<SequenceProgress>('POST', '/api/sequences/run', { sequence: seq });
}

export function getRunStatus(): Promise<SequenceProgress> {
  return get<SequenceProgress>('/api/sequences/run/status');
}

/** Abort the running sequence; the drone lands after the current step. */
export function abortSequence(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/sequences/abort');
}

/** @deprecated use abortSequence */
export function cancelSequence(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/sequences/cancel');
}

// ---- Camera: photos and clips saved on the host ----

export function getMedia(): Promise<MediaListResponse> {
  return get<MediaListResponse>('/api/media');
}

/** Save a photo to the gallery (starts the camera if needed). */
export function takePhoto(): Promise<MediaItem> {
  return request<MediaItem>('POST', '/api/media/photo');
}

export function startRecording(): Promise<RecordingStatus> {
  return request<RecordingStatus>('POST', '/api/media/record/start');
}

export function stopRecording(): Promise<{ item: MediaItem | null }> {
  return request<{ item: MediaItem | null }>('POST', '/api/media/record/stop');
}

export function deleteMedia(name: string): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('DELETE', `/api/media/files/${encodeURIComponent(name)}`);
}

export function startVideoStream(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/video/stream/start');
}

export function stopVideoStream(): Promise<ApiResponse> {
  return post<ApiResponse>('/api/video/stream/stop');
}

export function getFlights(): Promise<FlightSummary[]> {
  return get<FlightSummary[]>('/api/flights');
}

export function getFlight(id: number): Promise<FlightDetail> {
  return get<FlightDetail>(`/api/flights/${id}`);
}

export async function deleteFlight(id: number): Promise<ApiResponse> {
  try {
    const res = await fetch(`/api/flights/${id}`, { method: 'DELETE' });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    return await res.json();
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : 'Network error' };
  }
}
