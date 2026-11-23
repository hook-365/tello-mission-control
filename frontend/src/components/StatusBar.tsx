import { useCallback } from 'react';
import { Camera, Crosshair, Gamepad2, History, ScanSearch, Settings, LogOut } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import { pad, batteryTextColor } from '@/lib/format';

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
  const isFlying = useDroneStore((s) => s.isFlying);
  const previewMode = useDroneStore((s) => s.previewMode);
  const telemetry = useDroneStore((s) => s.telemetry);
  const disconnect = useDroneStore((s) => s.disconnect);
  const gamepadConnected = useDroneStore((s) => s.gamepadConnected);
  const vision = useDroneStore((s) => s.vision);
  const setVision = useDroneStore((s) => s.setVision);

  const canSnapshot = connectionStatus === 'connected' && isFlying && !previewMode;
  const battery = telemetry?.battery ?? null;

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

      {/* Separator */}
      <span className="w-px h-4 bg-white/10" />

      {/* Drone ID */}
      <span className="text-hud-secondary font-mono text-hud-sm">TELLO</span>

      {/* Gamepad indicator (only while a controller is attached) */}
      {gamepadConnected && (
        <span
          className="text-ok flex items-center"
          role="status"
          aria-label="Gamepad connected"
          title="Gamepad connected — left stick: up/down + turn, right stick: move. A takeoff, B land, Back emergency."
        >
          <Gamepad2 size={18} strokeWidth={1.5} />
        </span>
      )}

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

      {/* Vision toggles (only when the backend has the optional feature) */}
      {vision.available && (
        <>
          <button
            type="button"
            className={`control-btn p-2 ${vision.detecting ? 'text-info border-info/40' : ''}`}
            onClick={async () => setVision(await api.setDetecting(!vision.detecting))}
            aria-label="Object detection"
            aria-pressed={vision.detecting}
            title={vision.detecting ? 'Stop object detection' : 'Detect objects in the video'}
          >
            <ScanSearch size={18} strokeWidth={1.5} />
          </button>
          <button
            type="button"
            className={`control-btn p-2 ${vision.tracking ? 'text-caution border-caution/40' : ''}`}
            disabled={!isFlying && !vision.tracking}
            onClick={async () => setVision(await api.setTracking(!vision.tracking))}
            aria-label="Follow person"
            aria-pressed={vision.tracking}
            title={
              vision.tracking
                ? 'Stop following'
                : 'Follow the nearest person — any stick, move or land command takes back control'
            }
          >
            <Crosshair size={18} strokeWidth={1.5} />
          </button>
        </>
      )}

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
