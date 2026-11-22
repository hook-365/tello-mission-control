import { useEffect, useRef } from 'react';
import { BatteryWarning, Volume2, VolumeX, WifiLow, WifiZero } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import { playAlarm } from '@/lib/alarm';

/** Seconds between repeat beeps while something is critical. */
const REPEAT_MS = 10000;

interface Alert {
  key: string;
  critical: boolean;
  icon: JSX.Element;
  text: string;
}

export default function FlightAlerts() {
  const telemetry = useDroneStore((s) => s.telemetry);
  const previewMode = useDroneStore((s) => s.previewMode);
  const muted = useDroneStore((s) => s.alertsMuted);
  const toggleMuted = useDroneStore((s) => s.toggleAlertsMuted);

  const alerts: Alert[] = [];
  if (telemetry && !previewMode) {
    const b = telemetry.battery_level;
    if (b === 'critical') {
      alerts.push({ key: 'battery', critical: true, icon: <BatteryWarning size={18} />, text: `Battery ${telemetry.battery}%: land now` });
    } else if (b === 'low') {
      alerts.push({ key: 'battery', critical: false, icon: <BatteryWarning size={18} />, text: `Battery ${telemetry.battery}%: land soon` });
    }
    const s = telemetry.signal_level;
    const snr = telemetry.wifi_snr;
    if (s === 'critical') {
      alerts.push({ key: 'signal', critical: true, icon: <WifiZero size={18} />, text: `Wi-Fi almost gone (${snr}): come closer, the drone may land itself` });
    } else if (s === 'weak') {
      alerts.push({ key: 'signal', critical: false, icon: <WifiLow size={18} />, text: `Weak Wi-Fi (${snr}): stay closer` });
    }
  }

  const criticalKey = alerts.filter((a) => a.critical).map((a) => a.key).join(',');

  // Beep when something goes critical, then every REPEAT_MS while it stays critical.
  const lastKeyRef = useRef('');
  useEffect(() => {
    const prev = lastKeyRef.current;
    lastKeyRef.current = criticalKey;
    if (!criticalKey || muted) return;
    const newlyCritical = criticalKey.split(',').some((k) => !prev.split(',').includes(k));
    if (newlyCritical) playAlarm();
    const id = setInterval(playAlarm, REPEAT_MS);
    return () => clearInterval(id);
  }, [criticalKey, muted]);

  if (alerts.length === 0) return null;

  return (
    <div
      className="fixed top-16 left-1/2 -translate-x-1/2 z-[3] flex flex-col items-center gap-2 pointer-events-none w-[min(92vw,520px)]"
      role="alert"
      aria-live="assertive"
    >
      {alerts.map((a) => (
        <div
          key={a.key}
          data-testid={`alert-${a.key}`}
          data-level={a.critical ? 'critical' : 'warning'}
          className={`pointer-events-auto w-full flex items-center gap-2 rounded-xl border-2 px-4 py-2.5 font-bold uppercase tracking-wider text-hud-sm backdrop-blur ${
            a.critical
              ? 'border-danger bg-danger/30 text-white animate-pulse'
              : 'border-caution bg-caution/20 text-caution'
          }`}
        >
          {a.icon}
          <span className="flex-1">{a.text}</span>
          {a.critical && (
            <button
              type="button"
              className="p-1 rounded hover:bg-white/10"
              onClick={toggleMuted}
              aria-label={muted ? 'Unmute alarm' : 'Mute alarm'}
              title={muted ? 'Unmute alarm' : 'Mute alarm'}
            >
              {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
