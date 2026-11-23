import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, Pause, Play, Trash2, X } from 'lucide-react';
import TelemetryPanel from '@/components/TelemetryPanel';
import * as api from '@/lib/api';
import { formatFlightTime, secondsBetween } from '@/lib/format';
import type { FlightDetail, FlightSummary } from '@/types/drone';

interface FlightsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/** Replay advances one recorded frame per tick; frames are logged at ~4 Hz. */
const PLAYBACK_INTERVAL_MS = 250;

function formatStart(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function FlightsModal({ isOpen, onClose }: FlightsModalProps) {
  const [flights, setFlights] = useState<FlightSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<FlightDetail | null>(null);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  const loadFlights = useCallback(async () => {
    setError(null);
    try {
      setFlights(await api.getFlights());
    } catch {
      setFlights([]);
      setError('Flight log unavailable');
    }
  }, []);

  // Reset to a fresh list every time the modal opens.
  useEffect(() => {
    if (!isOpen) return;
    setDetail(null);
    setPlaying(false);
    setFlights(null);
    loadFlights();
  }, [isOpen, loadFlights]);

  // No Escape-to-close on purpose: Escape is the global emergency motor kill
  // (useKeyboard), and dismissing a dialog must never double as that.

  const frameCount = detail?.telemetry.length ?? 0;

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setFrameIndex((i) => {
        if (i >= frameCount - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, PLAYBACK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [playing, frameCount]);

  const openFlight = async (id: number) => {
    setError(null);
    try {
      setDetail(await api.getFlight(id));
      setFrameIndex(0);
      setPlaying(false);
    } catch {
      setError('Could not load that flight');
    }
  };

  const removeFlight = async (id: number) => {
    const res = await api.deleteFlight(id);
    if (!res.ok) setError('Could not delete that flight');
    await loadFlights();
  };

  const frame = detail?.telemetry[frameIndex] ?? null;
  const elapsed = detail && frame ? secondsBetween(detail.started_at, frame.timestamp) : 0;
  const total = detail
    ? secondsBetween(detail.started_at, detail.telemetry[frameCount - 1]?.timestamp)
    : 0;

  // Commands issued up to the scrubber position are "done"; the rest are dimmed.
  const commandsDone = useMemo(() => {
    if (!detail || !frame) return 0;
    const now = new Date(frame.timestamp).getTime();
    return detail.command_log.filter((c) => new Date(c.timestamp).getTime() <= now).length;
  }, [detail, frame]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[4] flex items-center justify-center"
      onClick={onClose}
    >
      <div
        className="hud-panel max-w-2xl w-full mx-4 max-h-[85vh] flex flex-col"
        role="dialog"
        aria-label="Flight log"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4 gap-2">
          <div className="flex items-center gap-2 min-w-0">
            {detail && (
              <button
                className="control-btn p-1"
                onClick={() => {
                  setDetail(null);
                  setPlaying(false);
                }}
                aria-label="Back to flight list"
              >
                <ArrowLeft size={16} />
              </button>
            )}
            <span className="hud-label text-hud-lg truncate">
              {detail ? `FLIGHT ${detail.id} · ${formatStart(detail.started_at)}` : 'FLIGHT LOG'}
            </span>
          </div>
          <button className="control-btn p-1" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {error && (
          <p className="text-hud-xs text-danger mb-2" role="alert">
            {error}
          </p>
        )}

        {!detail && (
          <div className="overflow-y-auto">
            {flights === null ? (
              <p className="text-hud-xs text-hud-dim italic text-center py-6">Loading…</p>
            ) : flights.length === 0 ? (
              !error && (
                <p className="text-hud-xs text-hud-dim italic text-center py-6">
                  No flights recorded yet
                </p>
              )
            ) : (
              <ul className="space-y-1">
                {flights.map((f) => (
                  <li key={f.id} className="flex items-center gap-2">
                    <button
                      className="flex-1 min-w-0 text-left py-2.5 px-3 rounded-lg hover:bg-surface-hover transition"
                      onClick={() => openFlight(f.id)}
                    >
                      <div className="text-hud-base font-semibold text-white">
                        {formatStart(f.started_at)}
                        {f.active && (
                          <span className="ml-2 text-hud-xs font-mono text-ok uppercase">
                            recording
                          </span>
                        )}
                      </div>
                      <div className="text-hud-xs text-hud-secondary mt-0.5 font-mono">
                        {f.active ? '—' : formatFlightTime(secondsBetween(f.started_at, f.ended_at))}
                        {' · '}
                        {f.commands} commands · {f.telemetry_frames} frames
                      </div>
                    </button>
                    <button
                      className="control-btn p-2 hover:text-danger hover:border-danger/30"
                      disabled={f.active}
                      onClick={() => removeFlight(f.id)}
                      aria-label={`Delete flight ${f.id}`}
                      title={f.active ? 'Still recording' : 'Delete this flight'}
                    >
                      <Trash2 size={16} strokeWidth={1.5} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {detail && (
          <div className="flex flex-col min-h-0">
            {frameCount === 0 ? (
              <p className="text-hud-xs text-hud-dim italic text-center py-6">
                No telemetry was recorded for this flight
              </p>
            ) : (
              <div className="flex items-center gap-3 mb-3">
                <button
                  className="control-btn p-2"
                  onClick={() => {
                    if (!playing && frameIndex >= frameCount - 1) setFrameIndex(0);
                    setPlaying((p) => !p);
                  }}
                  aria-label={playing ? 'Pause replay' : 'Play replay'}
                >
                  {playing ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <input
                  type="range"
                  className="hud-slider flex-1"
                  aria-label="Replay position"
                  min={0}
                  max={frameCount - 1}
                  step={1}
                  value={frameIndex}
                  onChange={(e) => {
                    setPlaying(false);
                    setFrameIndex(Number(e.target.value));
                  }}
                />
                <span className="font-mono text-hud-xs whitespace-nowrap">
                  {formatFlightTime(elapsed)} / {formatFlightTime(total)}
                </span>
              </div>
            )}

            <div className="flex gap-3 min-h-0">
              {frameCount > 0 && <TelemetryPanel data={frame?.data ?? null} title="Recorded" />}
              <div className="flex-1 min-w-0 overflow-y-auto max-h-[calc(50vh-32px)]">
                <h3 className="hud-label mb-2">Commands</h3>
                {detail.command_log.length === 0 ? (
                  <p className="text-hud-xs text-hud-dim italic">None</p>
                ) : (
                  <ol className="space-y-0.5 font-mono text-hud-xs">
                    {detail.command_log.map((c, i) => (
                      <li
                        key={i}
                        className={`flex gap-2 ${i < commandsDone || frameCount === 0 ? 'text-white' : 'text-hud-dim'}`}
                      >
                        <span className="text-hud-secondary">
                          {formatFlightTime(secondsBetween(detail.started_at, c.timestamp))}
                        </span>
                        <span className={c.result === 'error' ? 'text-danger' : undefined}>
                          {c.command}
                          {Object.keys(c.params ?? {}).length > 0 &&
                            ` ${Object.values(c.params).join(' ')}`}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
