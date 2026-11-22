from fastapi import APIRouter, HTTPException, Request, Response, status

from app.models.commands import CommandResponse
from app.models.sequences import RunRequest, RunStatus, Sequence, SequenceIn
from app.services.sequence_runner import PreflightError, SequenceAlreadyRunningError
from app.services.sequence_store import BuiltinSequenceError, SequenceNotFoundError

router = APIRouter(prefix="/api/sequences", tags=["sequences"])


def _store(request: Request):
    return request.app.state.sequence_store


def _runner(request: Request):
    return request.app.state.sequence_runner


def _get_or_404(request: Request, seq_id: str) -> Sequence:
    try:
        return _store(request).get(seq_id)
    except SequenceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Sequence '{seq_id}' not found")


async def _start(request: Request, seq: SequenceIn, seq_id: str | None) -> RunStatus:
    try:
        return await _runner(request).start(seq, sequence_id=seq_id)
    except SequenceAlreadyRunningError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PreflightError as e:
        raise HTTPException(status_code=409, detail={"message": "Pre-flight check failed", "problems": e.problems})


# -- Run control (declared before /{seq_id} routes) --

@router.get("/run/status", response_model=RunStatus)
async def run_status(request: Request):
    return _runner(request).status


@router.post("/run", response_model=RunStatus)
async def run(request: Request, body: RunRequest):
    if body.sequence_id is not None:
        seq = _get_or_404(request, body.sequence_id)
        return await _start(request, seq, seq.id)
    return await _start(request, body.sequence, None)


@router.post("/abort", response_model=CommandResponse)
async def abort(request: Request):
    if _runner(request).abort("Aborted by user"):
        return CommandResponse(ok=True, message="Abort requested, landing after the current step")
    return CommandResponse(ok=True, message="No sequence running")


# Older frontend builds call /cancel
router.add_api_route("/cancel", abort, methods=["POST"], response_model=CommandResponse, include_in_schema=False)


# -- CRUD --

@router.get("", response_model=list[Sequence])
async def list_sequences(request: Request):
    return _store(request).list()


@router.post("", response_model=Sequence, status_code=status.HTTP_201_CREATED)
async def create_sequence(request: Request, body: SequenceIn):
    return _store(request).create(body)


@router.get("/{seq_id}", response_model=Sequence)
async def get_sequence(request: Request, seq_id: str):
    return _get_or_404(request, seq_id)


@router.put("/{seq_id}", response_model=Sequence)
async def update_sequence(request: Request, seq_id: str, body: SequenceIn):
    try:
        return _store(request).update(seq_id, body)
    except BuiltinSequenceError:
        raise HTTPException(status_code=403, detail="Built-in sequences can't be changed. Save a copy instead.")
    except SequenceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Sequence '{seq_id}' not found")


@router.delete("/{seq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sequence(request: Request, seq_id: str):
    try:
        _store(request).delete(seq_id)
    except BuiltinSequenceError:
        raise HTTPException(status_code=403, detail="Built-in sequences can't be deleted")
    except SequenceNotFoundError:
        raise HTTPException(status_code=404, detail=f"Sequence '{seq_id}' not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{seq_id}/run", response_model=RunStatus)
async def run_saved(request: Request, seq_id: str):
    seq = _get_or_404(request, seq_id)
    return await _start(request, seq, seq.id)
