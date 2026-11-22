"""Runs a flight sequence step by step and streams progress over the WebSocket.

Safety model
------------
* Pre-flight checks before anything moves: connected, battery >= the minimum,
  battery high enough for flips if the sequence has any, nothing else running.
* Abort is cooperative: it interrupts hovers immediately, and otherwise takes
  effect as soon as the drone acknowledges the current command (a Tello can't
  be interrupted mid-move). The runner then lands. Emergency stop stays a
  separate, instant motor cut-off handled by DroneManager.
* Any failure mid-run lands the drone if it is airborne.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import settings
from app.models.sequences import (
    FlipStep,
    LandStep,
    MoveStep,
    RotateStep,
    RunState,
    RunStatus,
    SequenceIn,
    TakeoffStep,
    WaitStep,
    describe_step,
)
from app.services.drone_manager import DroneManager

logger = logging.getLogger(__name__)


class SequenceAlreadyRunningError(Exception):
    pass


class PreflightError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class _Aborted(Exception):
    pass


@dataclass
class _PlannedStep:
    step: object
    index: int | None  # position in the user's step list, None for auto bookends
    description: str


class SequenceRunner:
    def __init__(self, drone_manager: DroneManager) -> None:
        self._dm = drone_manager
        self._status = RunStatus()
        self._task: asyncio.Task | None = None
        self._abort = asyncio.Event()
        self._abort_reason = "Aborted"

    # -- state --

    @property
    def status(self) -> RunStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def wait(self) -> RunStatus:
        """Wait for the current run (if any) to finish."""
        if self._task is not None:
            await asyncio.shield(self._task)
        return self._status

    # -- checks --

    async def preflight(self, seq: SequenceIn) -> None:
        problems: list[str] = []
        if self.is_running:
            raise SequenceAlreadyRunningError("A sequence is already running")
        if not self._dm.is_connected:
            raise PreflightError(["Drone is not connected"])
        battery = await self._dm.get_battery()
        if battery < settings.sequence_min_battery_pct:
            problems.append(
                f"Battery is {battery}%, needs at least {settings.sequence_min_battery_pct}% to run a sequence"
            )
        elif seq.has_flips and battery < settings.sequence_flip_min_battery_pct:
            problems.append(
                f"Battery is {battery}%, flips need at least {settings.sequence_flip_min_battery_pct}%"
                " (remove the flips or charge up)"
            )
        if not seq.auto_takeoff_land and not self._dm.is_flying and seq.steps and not isinstance(seq.steps[0], TakeoffStep):
            problems.append("Drone is on the ground: add a takeoff step or turn on auto takeoff/land")
        if problems:
            raise PreflightError(problems)

    # -- control --

    async def start(self, seq: SequenceIn, sequence_id: str | None = None) -> RunStatus:
        await self.preflight(seq)
        plan = self._plan(seq)
        self._abort = asyncio.Event()
        self._abort_reason = "Aborted"
        self._status = RunStatus(
            run_id=uuid.uuid4().hex[:8],
            sequence_id=sequence_id,
            sequence_name=seq.name,
            status=RunState.running,
            total_steps=len(plan),
            message="Starting",
            started_at=datetime.now(timezone.utc),
        )
        self._task = asyncio.create_task(self._run(plan))
        await self._emit()
        return self._status

    def abort(self, reason: str = "Aborted") -> bool:
        """Request an abort. Returns False if nothing was running."""
        if not self.is_running:
            return False
        self._abort_reason = reason
        self._abort.set()
        return True

    async def shutdown(self) -> None:
        if self.is_running:
            self.abort("Server shutting down")
            try:
                await asyncio.wait_for(self.wait(), timeout=30)
            except Exception:
                self._task.cancel()

    # -- internals --

    def _plan(self, seq: SequenceIn) -> list[_PlannedStep]:
        plan = [_PlannedStep(s, i, describe_step(s)) for i, s in enumerate(seq.steps)]
        if seq.auto_takeoff_land:
            if not isinstance(seq.steps[0], TakeoffStep):
                plan.insert(0, _PlannedStep(TakeoffStep(), None, "Take off (auto)"))
            if not isinstance(seq.steps[-1], LandStep):
                plan.append(_PlannedStep(LandStep(), None, "Land (auto)"))
        return plan

    async def _emit(self) -> None:
        await self._dm.broadcast_event({
            "type": "sequence_progress",
            "data": self._status.model_dump(mode="json"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _update(self, **fields) -> None:
        self._status = self._status.model_copy(update=fields)
        await self._emit()

    def _check_abort(self) -> None:
        if self._abort.is_set():
            raise _Aborted()

    async def _hover(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._abort.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        raise _Aborted()

    async def _execute(self, ps: _PlannedStep) -> str | None:
        """Run one step. Returns a note to show if the step was skipped."""
        step = ps.step
        dm = self._dm
        if isinstance(step, TakeoffStep):
            if dm.is_flying:
                return "Already airborne, skipping takeoff"
            await dm.takeoff()
        elif isinstance(step, LandStep):
            if not dm.is_flying:
                return "Already on the ground"
            await dm.land()
        elif isinstance(step, MoveStep):
            await dm.move(step.direction, step.distance_cm)
        elif isinstance(step, RotateStep):
            await dm.rotate(step.direction, step.angle_deg)
        elif isinstance(step, FlipStep):
            battery = await dm.get_battery()
            if battery < settings.sequence_flip_min_battery_pct:
                return f"Skipped flip: battery {battery}% (needs {settings.sequence_flip_min_battery_pct}%)"
            await dm.flip(step.direction)
        elif isinstance(step, WaitStep):
            await self._hover(step.seconds)
        return None

    async def _land_if_flying(self) -> str:
        if not self._dm.is_flying:
            return ""
        try:
            await self._dm.land()
            return "landed"
        except Exception as e:  # pragma: no cover - depends on hardware failures
            logger.error("Sequence: landing failed: %s", e)
            return f"landing failed ({e}) - use Land or Emergency"

    async def _run(self, plan: list[_PlannedStep]) -> None:
        final_state = RunState.completed
        final_msg = "Sequence complete"
        try:
            for pos, ps in enumerate(plan, start=1):
                self._check_abort()
                battery = await self._dm.get_battery()
                if self._dm.is_flying and battery < settings.sequence_abort_battery_pct:
                    self._abort_reason = f"Battery low ({battery}%)"
                    raise _Aborted()
                await self._update(
                    current_step=pos,
                    step_index=ps.index,
                    step_description=ps.description,
                    message=ps.description,
                )
                note = await self._execute(ps)
                if note:
                    await self._update(message=note)
            self._check_abort()
        except (_Aborted, asyncio.CancelledError) as e:
            final_state = RunState.aborted
            reason = self._abort_reason if isinstance(e, _Aborted) else "Cancelled"
            landed = await self._land_if_flying()
            final_msg = f"{reason}, {landed}" if landed else reason
            if isinstance(e, asyncio.CancelledError):
                await self._finish(final_state, final_msg)
                raise
        except Exception as e:
            logger.exception("Sequence failed")
            final_state = RunState.failed
            landed = await self._land_if_flying()
            final_msg = f"Step failed: {e}" + (f", {landed}" if landed else "")
        await self._finish(final_state, final_msg)

    async def _finish(self, state: RunState, message: str) -> None:
        await self._update(
            status=state,
            message=message,
            finished_at=datetime.now(timezone.utc),
        )
        logger.info("Sequence %s: %s (%s)", self._status.sequence_name, state.value, message)
