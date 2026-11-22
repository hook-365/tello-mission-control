import { Gamepad2, Keyboard } from 'lucide-react';
import { useDroneStore } from '@/stores/droneStore';

function StickDot({ x, y, label, active }: { x: number; y: number; label: string; active: boolean }) {
  // x, y in -100..100 (y positive = up)
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`relative w-11 h-11 rounded-full border ${active ? 'border-ok/60 bg-ok/10' : 'border-white/15 bg-white/5'}`}
        aria-hidden
      >
        <span
          className={`absolute w-2.5 h-2.5 rounded-full -translate-x-1/2 -translate-y-1/2 ${active ? 'bg-ok' : 'bg-white/40'}`}
          style={{ left: `${50 + x * 0.4}%`, top: `${50 - y * 0.4}%` }}
        />
      </div>
      <span className="text-[9px] text-hud-dim uppercase tracking-wider">{label}</span>
    </div>
  );
}

function shortPadName(id: string): string {
  // "Xbox Wireless Controller (STANDARD GAMEPAD Vendor: 045e Product: 0b13)" -> "Xbox Wireless Controller"
  const name = id.split('(')[0].trim();
  return name.length > 28 ? `${name.slice(0, 27)}…` : name || 'Controller';
}

export default function StickPanel() {
  const keyboardMode = useDroneStore((s) => s.keyboardMode);
  const setKeyboardMode = useDroneStore((s) => s.setKeyboardMode);
  const stickSpeed = useDroneStore((s) => s.stickSpeed);
  const setStickSpeed = useDroneStore((s) => s.setStickSpeed);
  const gamepadName = useDroneStore((s) => s.gamepadName);
  const stickInput = useDroneStore((s) => s.stickInput);
  const rcError = useDroneStore((s) => s.rcError);
  const isFlying = useDroneStore((s) => s.isFlying);
  const running = useDroneStore((s) => s.sequenceProgress?.status === 'running');

  const { sticks, armed } = stickInput;
  const sticksOn = !!gamepadName || keyboardMode === 'hold';

  let hint: string;
  if (running) hint = 'Sticks are off while a sequence runs';
  else if (armed && rcError) hint = rcError;
  else if (gamepadName) {
    if (!isFlying) hint = 'Hold LB or RB and press Start to take off';
    else hint = armed ? 'Sticks live' : 'Hold LB or RB to fly. Let go to hover';
  } else if (keyboardMode === 'hold') {
    hint = isFlying ? 'Hold W A S D, Space, Shift, Q, E to fly' : 'Press T to take off';
  } else {
    hint = 'Plug in a controller and press any button';
  }

  return (
    <div className="mb-3 space-y-2" data-testid="stick-panel">
      <div className="flex items-center gap-2 text-hud-xs">
        {gamepadName ? (
          <span className="flex items-center gap-1.5 text-ok" title={gamepadName}>
            <Gamepad2 size={14} />
            {shortPadName(gamepadName)}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-hud-dim">
            <Keyboard size={14} />
            Keys
          </span>
        )}
        <div className="ml-auto flex rounded-md border border-white/10 overflow-hidden" role="group" aria-label="Keyboard mode">
          {(['tap', 'hold'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={`px-2 py-0.5 ${keyboardMode === m ? 'bg-white/15 text-white' : 'text-hud-dim hover:text-white'}`}
              aria-pressed={keyboardMode === m}
              onClick={() => setKeyboardMode(m)}
              title={m === 'tap' ? 'Each key press moves a set distance' : 'Hold keys to fly smoothly, let go to hover'}
            >
              {m === 'tap' ? 'Tap' : 'Hold to fly'}
            </button>
          ))}
        </div>
      </div>

      <p
        className={`text-hud-xs ${armed && rcError ? 'text-caution' : armed ? 'text-ok' : 'text-hud-secondary'}`}
        role="status"
        data-testid="stick-hint"
      >
        {hint}
      </p>

      {sticksOn && (
        <>
          <div className="flex items-end justify-around">
            <StickDot x={sticks.yaw} y={sticks.ud} label="Spin / Up" active={armed} />
            <StickDot x={sticks.lr} y={sticks.fb} label="Fly" active={armed} />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="hud-label">Stick speed</span>
              <span className="font-mono text-hud-xs">{stickSpeed}%</span>
            </div>
            <input
              type="range"
              className="hud-slider"
              aria-label="Stick speed"
              min={20}
              max={100}
              step={10}
              value={stickSpeed}
              onChange={(e) => setStickSpeed(Number(e.target.value))}
            />
          </div>
          {gamepadName && (
            <details className="text-hud-xs text-hud-secondary">
              <summary className="cursor-pointer text-hud-dim">Controller map</summary>
              <ul className="mt-1 space-y-0.5">
                <li>Hold LB or RB: fly (let go = hover)</li>
                <li>Left stick: up/down and spin</li>
                <li>Right stick: forward/back and sideways</li>
                <li>LB or RB + Start: take off</li>
                <li>Back: land</li>
                <li className="text-danger">Click both sticks in: emergency motor stop</li>
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
