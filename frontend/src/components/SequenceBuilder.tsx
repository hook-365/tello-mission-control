import { useEffect, useMemo, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  GripVertical,
  OctagonX,
  Play,
  Plus,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';
import * as api from '@/lib/api';
import {
  FLIP_DIRECTIONS,
  LIMITS,
  MOVE_DIRECTIONS,
  ROTATE_DIRECTIONS,
  STEP_LABELS,
  defaultStep,
  describeStep,
  emptyDraft,
  hasFlips,
  validateDraft,
} from '@/lib/sequence';
import type { Sequence, SequenceDraft, SequenceStep, StepType } from '@/types/drone';

interface SequenceBuilderProps {
  isOpen: boolean;
  onClose: () => void;
}

const FIELD = 'bg-white/5 border border-white/10 rounded-md px-2 py-1 text-hud-sm text-white focus:outline-none focus:border-info';

function toDraft(seq: Sequence): SequenceDraft {
  return {
    name: seq.name,
    description: seq.description,
    auto_takeoff_land: seq.auto_takeoff_land,
    steps: seq.steps.map((s) => ({ ...s })),
  };
}

function num(value: string): number {
  return value === '' ? Number.NaN : Number(value);
}

function StepFields({
  step,
  disabled,
  onChange,
}: {
  step: SequenceStep;
  disabled: boolean;
  onChange: (s: SequenceStep) => void;
}) {
  switch (step.type) {
    case 'move':
      return (
        <>
          <select
            aria-label="Direction"
            className={FIELD}
            disabled={disabled}
            value={step.direction}
            onChange={(e) => onChange({ ...step, direction: e.target.value as typeof step.direction })}
          >
            {MOVE_DIRECTIONS.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <input
            aria-label="Distance in cm"
            type="number"
            className={`${FIELD} w-20`}
            disabled={disabled}
            min={LIMITS.distance.min}
            max={LIMITS.distance.max}
            step={LIMITS.distance.step}
            value={Number.isNaN(step.distance_cm) ? '' : step.distance_cm}
            onChange={(e) => onChange({ ...step, distance_cm: num(e.target.value) })}
          />
          <span className="text-hud-xs text-hud-secondary">cm</span>
        </>
      );
    case 'rotate':
      return (
        <>
          <select
            aria-label="Spin direction"
            className={FIELD}
            disabled={disabled}
            value={step.direction}
            onChange={(e) => onChange({ ...step, direction: e.target.value as typeof step.direction })}
          >
            {ROTATE_DIRECTIONS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
          <input
            aria-label="Angle in degrees"
            type="number"
            className={`${FIELD} w-20`}
            disabled={disabled}
            min={LIMITS.angle.min}
            max={LIMITS.angle.max}
            step={LIMITS.angle.step}
            value={Number.isNaN(step.angle_deg) ? '' : step.angle_deg}
            onChange={(e) => onChange({ ...step, angle_deg: num(e.target.value) })}
          />
          <span className="text-hud-xs text-hud-secondary">°</span>
        </>
      );
    case 'flip':
      return (
        <select
          aria-label="Flip direction"
          className={FIELD}
          disabled={disabled}
          value={step.direction}
          onChange={(e) => onChange({ ...step, direction: e.target.value as typeof step.direction })}
        >
          {FLIP_DIRECTIONS.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
      );
    case 'wait':
      return (
        <>
          <input
            aria-label="Hover seconds"
            type="number"
            className={`${FIELD} w-20`}
            disabled={disabled}
            min={LIMITS.seconds.min}
            max={LIMITS.seconds.max}
            step={LIMITS.seconds.step}
            value={Number.isNaN(step.seconds) ? '' : step.seconds}
            onChange={(e) => onChange({ ...step, seconds: num(e.target.value) })}
          />
          <span className="text-hud-xs text-hud-secondary">sec</span>
        </>
      );
    default:
      return null;
  }
}

export default function SequenceBuilder({ isOpen, onClose }: SequenceBuilderProps) {
  const sequences = useDroneStore((s) => s.sequences);
  const refreshSequences = useDroneStore((s) => s.refreshSequences);
  const progress = useDroneStore((s) => s.sequenceProgress);
  const setSequenceProgress = useDroneStore((s) => s.setSequenceProgress);
  const battery = useDroneStore((s) => s.telemetry?.battery ?? null);

  const [draft, setDraft] = useState<SequenceDraft>(emptyDraft);
  const [loaded, setLoaded] = useState<Sequence | null>(null);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(JSON.stringify(emptyDraft()));
  const [notice, setNotice] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [dragFrom, setDragFrom] = useState<number | null>(null);
  const [ranDraft, setRanDraft] = useState(false);

  useEffect(() => {
    if (isOpen) refreshSequences();
  }, [isOpen, refreshSequences]);

  const errors = useMemo(() => validateDraft(draft), [draft]);
  const dirty = JSON.stringify(draft) !== savedSnapshot;
  const running = progress?.status === 'running';
  const ownSaved = loaded && !loaded.builtin ? loaded : null;

  // Which step to highlight: only for the run this builder started / has loaded
  const runIsOurs =
    progress != null &&
    ((loaded && progress.sequence_id === loaded.id && !dirty) || (progress.sequence_id == null && ranDraft));
  const activeIndex = running && runIsOurs ? progress?.step_index ?? null : null;

  if (!isOpen) return null;

  const flash = (kind: 'ok' | 'error', text: string) => setNotice({ kind, text });

  const update = (fn: (d: SequenceDraft) => SequenceDraft) => {
    setDraft((d) => fn(d));
    setNotice(null);
    setConfirmDelete(false);
  };

  const setStep = (i: number, s: SequenceStep) =>
    update((d) => ({ ...d, steps: d.steps.map((x, j) => (j === i ? s : x)) }));

  const addStep = (type: StepType) =>
    update((d) => ({ ...d, steps: [...d.steps, defaultStep(type)] }));

  const removeStep = (i: number) =>
    update((d) => ({ ...d, steps: d.steps.filter((_, j) => j !== i) }));

  const moveStep = (from: number, to: number) => {
    if (to < 0 || to >= draft.steps.length || from === to) return;
    update((d) => {
      const steps = [...d.steps];
      const [s] = steps.splice(from, 1);
      steps.splice(to, 0, s);
      return { ...d, steps };
    });
  };

  const load = (id: string) => {
    setConfirmDelete(false);
    setNotice(null);
    if (id === '') {
      const fresh = emptyDraft();
      setDraft(fresh);
      setLoaded(null);
      setSavedSnapshot(JSON.stringify(fresh));
      return;
    }
    const seq = sequences.find((s) => s.id === id);
    if (!seq) return;
    const d = toDraft(seq);
    setDraft(d);
    setLoaded(seq);
    setSavedSnapshot(JSON.stringify(d));
  };

  const save = async (asNew: boolean) => {
    if (errors.length) return;
    setBusy(true);
    try {
      const saved = ownSaved && !asNew
        ? await api.updateSequence(ownSaved.id, draft)
        : await api.createSequence(draft);
      await refreshSequences();
      setLoaded(saved);
      setSavedSnapshot(JSON.stringify(draft));
      flash('ok', `Saved "${saved.name}"`);
    } catch (e) {
      flash('error', e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!ownSaved) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy(true);
    try {
      await api.deleteSequence(ownSaved.id);
      await refreshSequences();
      load('');
      flash('ok', `Deleted "${ownSaved.name}"`);
    } catch (e) {
      flash('error', e instanceof Error ? e.message : 'Delete failed');
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  const play = async () => {
    if (errors.length || running) return;
    setBusy(true);
    setNotice(null);
    try {
      const useSaved = loaded && !dirty;
      setRanDraft(!useSaved);
      const status = useSaved ? await api.runSequence(loaded.id) : await api.runDraft(draft);
      setSequenceProgress(status);
    } catch (e) {
      flash('error', e instanceof Error ? e.message : 'Could not start');
    } finally {
      setBusy(false);
    }
  };

  const builtins = sequences.filter((s) => s.builtin);
  const mine = sequences.filter((s) => !s.builtin);
  const flipWarning = hasFlips(draft) && battery !== null && battery < 50;
  const palette: StepType[] = draft.auto_takeoff_land
    ? ['move', 'rotate', 'flip', 'wait']
    : ['takeoff', 'move', 'rotate', 'flip', 'wait', 'land'];

  return (
    <aside
      className="fixed z-[4] right-3 top-3 sm:right-4 sm:top-4 w-[min(440px,calc(100vw-24px))] hud-panel flex flex-col gap-3 animate-fade-in-up"
      // Leave room at the bottom so the Emergency Stop button is never covered
      style={{ bottom: 'clamp(96px, 12vh, 120px)' }}
      aria-label="Flight sequencer"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="hud-label text-hud-lg">FLIGHT SEQUENCER</span>
        <button className="control-btn p-1" onClick={onClose} aria-label="Close sequencer">
          <X size={16} />
        </button>
      </div>

      {/* Load + name */}
      <div className="flex flex-col gap-2">
        <select
          aria-label="Load a sequence"
          className={FIELD}
          disabled={running}
          value={loaded?.id ?? ''}
          onChange={(e) => load(e.target.value)}
        >
          <option value="">+ New sequence</option>
          {builtins.length > 0 && (
            <optgroup label="Built-in">
              {builtins.map((s) => (
                <option key={s.id} value={s.id}>★ {s.name}</option>
              ))}
            </optgroup>
          )}
          {mine.length > 0 && (
            <optgroup label="Saved">
              {mine.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </optgroup>
          )}
        </select>
        {loaded?.description && (
          <p className="text-hud-xs text-hud-secondary">{loaded.description}</p>
        )}
        <input
          aria-label="Sequence name"
          className={FIELD}
          placeholder="Name it, e.g. Victory lap"
          maxLength={LIMITS.nameMax}
          disabled={running}
          value={draft.name}
          onChange={(e) => update((d) => ({ ...d, name: e.target.value }))}
        />
        <label className="flex items-center gap-2 text-hud-xs text-hud-secondary cursor-pointer select-none">
          <input
            type="checkbox"
            disabled={running}
            checked={draft.auto_takeoff_land}
            onChange={(e) => update((d) => ({ ...d, auto_takeoff_land: e.target.checked }))}
          />
          Auto take off at the start and land at the end
        </label>
      </div>

      {/* Steps */}
      <ol className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1 pr-1" aria-label="Steps">
        {draft.steps.length === 0 && (
          <li className="text-hud-xs text-hud-dim italic text-center py-6">
            No steps yet. Add some below, like Move up 50, Move forward 100, Spin 360, Flip.
          </li>
        )}
        {draft.steps.map((step, i) => {
          const active = activeIndex === i;
          return (
            <li
              key={i}
              data-testid={`step-${i}`}
              data-active={active || undefined}
              title={describeStep(step)}
              draggable={!running}
              onDragStart={() => setDragFrom(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => {
                if (dragFrom !== null) moveStep(dragFrom, i);
                setDragFrom(null);
              }}
              className={`flex items-center gap-1.5 rounded-lg px-1.5 py-1.5 border transition ${
                active
                  ? 'border-info bg-info/20 shadow-[0_0_12px_rgba(58,139,255,0.35)]'
                  : 'border-transparent hover:bg-surface-hover'
              }`}
            >
              <GripVertical size={14} className="text-hud-dim cursor-grab shrink-0" />
              <span className="font-mono text-hud-xs text-hud-secondary w-5 text-right shrink-0">{i + 1}</span>
              <span className="text-hud-sm font-semibold w-14 shrink-0">{STEP_LABELS[step.type]}</span>
              <div className="flex items-center gap-1 flex-1 min-w-0 flex-wrap">
                <StepFields step={step} disabled={running} onChange={(s) => setStep(i, s)} />
              </div>
              <button className="control-btn p-1" disabled={running || i === 0} onClick={() => moveStep(i, i - 1)} aria-label={`Move step ${i + 1} up`}>
                <ArrowUp size={12} />
              </button>
              <button className="control-btn p-1" disabled={running || i === draft.steps.length - 1} onClick={() => moveStep(i, i + 1)} aria-label={`Move step ${i + 1} down`}>
                <ArrowDown size={12} />
              </button>
              <button className="control-btn p-1 hover:text-danger" disabled={running} onClick={() => removeStep(i)} aria-label={`Delete step ${i + 1}`}>
                <Trash2 size={12} />
              </button>
            </li>
          );
        })}
      </ol>

      {/* Add step palette */}
      <div className="flex flex-wrap gap-1.5">
        {palette.map((t) => (
          <button
            key={t}
            className="control-btn px-2.5 py-1.5"
            disabled={running || draft.steps.length >= LIMITS.maxSteps}
            onClick={() => addStep(t)}
          >
            <Plus size={12} />
            {STEP_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Validation + notices */}
      {(errors.length > 0 && draft.steps.length > 0) || flipWarning || notice ? (
        <div className="text-hud-xs space-y-1" role="status">
          {draft.steps.length > 0 && errors.map((e) => (
            <p key={e} className="text-caution">{e}</p>
          ))}
          {flipWarning && <p className="text-caution">Battery under 50%: the drone won't flip.</p>}
          {notice && (
            <p className={`whitespace-pre-line ${notice.kind === 'ok' ? 'text-ok' : 'text-danger'}`}>{notice.text}</p>
          )}
        </div>
      ) : null}

      {/* Run state */}
      {running && progress ? (
        <div className="space-y-2">
          <div className="text-hud-xs text-hud-secondary">
            Step {progress.current_step}/{progress.total_steps}: {progress.step_description}
          </div>
          <button
            className="w-full rounded-xl border-2 border-caution bg-caution/20 text-caution font-bold uppercase tracking-widest py-4 text-hud-lg flex items-center justify-center gap-2 hover:bg-caution/35 active:bg-caution active:text-black transition"
            onClick={() => api.abortSequence()}
          >
            <OctagonX size={22} />
            Abort and land
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            className="control-btn px-3 py-2"
            disabled={busy || errors.length > 0 || (!!ownSaved && !dirty)}
            onClick={() => save(false)}
          >
            <Save size={14} />
            {ownSaved ? 'Save' : 'Save new'}
          </button>
          {ownSaved && (
            <button className="control-btn px-3 py-2" disabled={busy || errors.length > 0} onClick={() => save(true)}>
              Save copy
            </button>
          )}
          {ownSaved && (
            <button
              className={`control-btn px-3 py-2 ${confirmDelete ? 'border-danger text-danger' : ''}`}
              disabled={busy}
              onClick={remove}
            >
              <Trash2 size={14} />
              {confirmDelete ? 'Sure?' : 'Delete'}
            </button>
          )}
          <button
            className="control-btn border-ok text-ok hover:bg-ok/20 px-4 py-2 ml-auto"
            disabled={busy || errors.length > 0}
            onClick={play}
          >
            <Play size={16} />
            Play
          </button>
        </div>
      )}
      {progress && !running && runIsOurs && (
        <p className={`text-hud-xs ${progress.status === 'completed' ? 'text-ok' : 'text-caution'}`}>
          {progress.message || progress.status}
        </p>
      )}
    </aside>
  );
}
