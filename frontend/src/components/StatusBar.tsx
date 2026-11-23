import { useCallback, useEffect, useState } from 'react';
import { Camera, Circle, History, Images, Square, LogOut, Wifi, WifiLow, WifiOff, WifiZero } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { batteryTextColor } from '@/lib/format';

function RecTimer({ startedAt }: { startedAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const secs = startedAt ? Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000)) : 0;
  return (
    <span className="font-mono text-hud-sm text-danger" data-testid="rec-indicator">
      <span className="inline-block w-2 h-2 rounded-full bg-danger animate-pulse mr-1 align-middle" />
      REC {Math.floor(secs / 60)}:{String(secs % 60).padStart(2, '0')}
    </span>
  );
}

const STATUS_DOT_CLASS: Record<string, string> = {
  connected: 'bg-ok',
  connecting: 'bg-caution animate-pulse',
  disconnected: 'bg-hud-dim',
  error: 'bg-danger',
};

interface StatusBarProps {
  onOpenFlights?: () => void;
}

export default function StatusBar({ onOpenFlights }: StatusBarProps = {}) {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const previewMode = useDroneStore((s) => s.previewMode);
  const telemetry = useDroneStore((s) => s.telemetry);
  const disconnect = useDroneStore((s) => s.disconnect);
  const recording = useDroneStore((s) => s.recording);
  const mediaCount = useDroneStore((s) => s.media.length);
  const setGalleryOpen = useDroneStore((s) => s.setGalleryOpen);
  const galleryOpen = useDroneStore((s) => s.galleryOpen);
  const addCommandLog = useDroneStore((s) => s.addCommandLog);
  const [busy, setBusy] = useState(false);

  // Photos and clips work on the ground too; the camera switches itself on.
  const cameraReady = connectionStatus === 'connected' && !previewMode;
  const battery = telemetry?.battery ?? null;
  const signal = telemetry?.signal_level ?? 'unknown';
  const snr = telemetry?.wifi_snr ?? null;
  const SignalIcon = signal === 'ok' ? Wifi : signal === 'weak' ? WifiLow : signal === 'critical' ? WifiZero : WifiOff;
  const signalClass =
    signal === 'ok' ? 'text-ok' : signal === 'weak' ? 'text-caution' : signal === 'critical' ? 'text-danger animate-pulse' : 'text-hud-dim';

  const run = useCallback(
    async (command: string, fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn(); // success shows up via the media WebSocket event
      } catch (err) {
        addCommandLog({
          command,
          params: {},
          result: 'error',
          error: err instanceof Error ? err.message : 'Failed',
          timestamp: new Date().toISOString(),
        });
      } finally {
        setBusy(false);
      }
    },
    [addCommandLog],
  );

  const handlePhoto = () => run('photo', api.takePhoto);
  const handleRecord = () =>
    recording.recording ? run('record_stop', api.stopRecording) : run('record_start', api.startRecording);

  return (
    <div className="hud-panel animate-fade-in-up flex flex-row items-center gap-3">
      {/* Status dot */}
      <span
        className={`w-2 h-2 rounded-full flex-shrink-0 ${previewMode ? 'bg-info' : (STATUS_DOT_CLASS[connectionStatus] ?? 'bg-hud-dim')}`}
      />

      {/* Status label */}
      <span className="font-mono uppercase text-hud-sm tracking-[0.08em]">
        {previewMode ? 'preview' : connectionStatus}
      </span>

      {/* Battery inline (when available) */}
      {battery !== null && !previewMode && (
        <>
          <span className="w-px h-4 bg-white/10" />
          <span className={`font-mono text-hud-sm ${batteryTextColor(battery)}`}>
            {battery}%
          </span>
        </>
      )}

      {/* Wi-Fi signal (SNR from the drone) */}
      {telemetry && !previewMode && (
        <>
          <span className="w-px h-4 bg-white/10" />
          <span
            className={`flex items-center gap-1 font-mono text-hud-sm ${signalClass}`}
            title={snr === null ? 'Wi-Fi signal: not read yet' : `Wi-Fi signal (SNR): ${snr}`}
            data-testid="wifi-signal"
          >
            <SignalIcon size={16} strokeWidth={1.75} />
            {snr ?? '--'}
          </span>
        </>
      )}

      {/* Separator */}
      <span className="w-px h-4 bg-white/10" />

      {/* Drone ID */}
      <span className="text-hud-secondary font-mono text-hud-sm">TELLO</span>

      {recording.recording && <RecTimer startedAt={recording.started_at} />}

      {/* Photo: saved to the gallery on the host */}
      <button
        type="button"
        className="control-btn p-2"
        disabled={!cameraReady || busy}
        onClick={handlePhoto}
        aria-label="Take photo"
        title="Take a photo (saved to the gallery)"
      >
        <Camera size={18} strokeWidth={1.5} />
      </button>

      {/* Flight log */}
      <button
        type="button"
        className="control-btn p-2"
        disabled={previewMode || !onOpenFlights}
        onClick={onOpenFlights}
        aria-label="Flight log"
        title="Recorded flights"
      >
        <History size={18} strokeWidth={1.5} />
      </button>

      {/* Record a clip */}
      <button
        type="button"
        className={`control-btn p-2 ${recording.recording ? 'text-danger border-danger/40' : ''}`}
        disabled={!cameraReady || busy}
        onClick={handleRecord}
        aria-label={recording.recording ? 'Stop recording' : 'Start recording'}
        aria-pressed={recording.recording}
        title={recording.recording ? 'Stop and save the clip' : 'Record a video clip'}
      >
        {recording.recording ? (
          <Square size={16} strokeWidth={2} fill="currentColor" />
        ) : (
          <Circle size={18} strokeWidth={2} className="text-danger" />
        )}
      </button>

      {/* Gallery */}
      <button
        type="button"
        className={`control-btn p-2 relative ${galleryOpen ? 'border-info text-info' : ''}`}
        disabled={previewMode}
        onClick={() => setGalleryOpen(!galleryOpen)}
        aria-label="Gallery"
        title="Photos and clips"
      >
        <Images size={18} strokeWidth={1.5} />
        {mediaCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-info text-[10px] leading-4 font-mono text-white">
            {mediaCount > 99 ? '99+' : mediaCount}
          </span>
        )}
      </button>

      {/* Disconnect button */}
      <button
        type="button"
        className="control-btn p-2 hover:text-danger hover:border-danger/30"
        onClick={disconnect}
        aria-label="Disconnect"
        title="Disconnect and return to connection screen"
      >
        <LogOut size={18} strokeWidth={1.5} />
      </button>
    </div>
  );
}
