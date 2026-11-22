import { useCallback } from 'react';
import { Camera, Settings, LogOut, Wifi, WifiLow, WifiOff, WifiZero } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { pad, batteryTextColor } from '@/lib/format';

const STATUS_DOT_CLASS: Record<string, string> = {
  connected: 'bg-ok',
  connecting: 'bg-caution animate-pulse',
  disconnected: 'bg-hud-dim',
  error: 'bg-danger',
};

export default function StatusBar() {
  const connectionStatus = useDroneStore((s) => s.connectionStatus);
  const isFlying = useDroneStore((s) => s.isFlying);
  const previewMode = useDroneStore((s) => s.previewMode);
  const telemetry = useDroneStore((s) => s.telemetry);
  const disconnect = useDroneStore((s) => s.disconnect);

  const canSnapshot = connectionStatus === 'connected' && isFlying && !previewMode;
  const battery = telemetry?.battery ?? null;
  const signal = telemetry?.signal_level ?? 'unknown';
  const snr = telemetry?.wifi_snr ?? null;
  const SignalIcon = signal === 'ok' ? Wifi : signal === 'weak' ? WifiLow : signal === 'critical' ? WifiZero : WifiOff;
  const signalClass =
    signal === 'ok' ? 'text-ok' : signal === 'weak' ? 'text-caution' : signal === 'critical' ? 'text-danger animate-pulse' : 'text-hud-dim';

  const handleSnapshot = useCallback(async () => {
    try {
      const blob = await api.takeSnapshot();
      const url = URL.createObjectURL(blob);
      const now = new Date();
      const timestamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
      const a = document.createElement('a');
      a.href = url;
      a.download = `tello_${timestamp}.jpg`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Snapshot failed silently — could surface via toast in the future
    }
  }, []);

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

      {/* Snapshot button */}
      <button
        type="button"
        className="control-btn p-2"
        disabled={!canSnapshot}
        onClick={handleSnapshot}
        aria-label="Take Snapshot"
      >
        <Camera size={18} strokeWidth={1.5} />
      </button>

      {/* Settings button (placeholder) */}
      <button
        type="button"
        className="control-btn p-2"
        disabled
        aria-label="Settings"
      >
        <Settings size={18} strokeWidth={1.5} />
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
