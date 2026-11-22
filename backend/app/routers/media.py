"""Photos and clips saved from the drone camera."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.services.media import MediaError, MediaNotFoundError

router = APIRouter(prefix="/api/media", tags=["media"])


def _svc(request: Request):
    return request.app.state.media_service


@router.get("")
async def list_media(request: Request):
    svc = _svc(request)
    return {"items": [i.to_dict() for i in svc.list()], "recording": svc.recording_status()}


@router.get("/files/{name}")
async def get_file(name: str, request: Request):
    try:
        path = _svc(request).path_for(name)
    except MediaNotFoundError:
        raise HTTPException(status_code=404, detail="No such photo or clip")
    media_type = "image/jpeg" if path.suffix == ".jpg" else "video/mp4"
    return FileResponse(path, media_type=media_type, filename=name)


@router.delete("/files/{name}")
async def delete_file(name: str, request: Request):
    try:
        _svc(request).delete(name)
    except MediaNotFoundError:
        raise HTTPException(status_code=404, detail="No such photo or clip")
    await request.app.state.drone_manager.broadcast_event(
        {"type": "media", "data": {"event": "deleted", "name": name}}
    )
    return {"ok": True}


@router.post("/photo")
async def take_photo(request: Request):
    try:
        item = await _svc(request).take_photo()
    except MediaError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return item.to_dict()


@router.get("/record/status")
async def record_status(request: Request):
    return _svc(request).recording_status()


@router.post("/record/start")
async def record_start(request: Request):
    try:
        return await _svc(request).start_recording()
    except MediaError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/record/stop")
async def record_stop(request: Request):
    item = await _svc(request).stop_recording()
    return {"item": item.to_dict() if item else None}
