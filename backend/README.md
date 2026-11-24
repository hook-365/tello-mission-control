# Backend

FastAPI service that owns the drone connection (via `djitellopy`) and serves the REST and WebSocket API. When `frontend/dist` exists it also serves the web UI at `/`.

- Running it: the [top-level README](../README.md)
- API: [docs/api.md](../docs/api.md)
- Settings: [docs/configuration.md](../docs/configuration.md)
- Code layout and design rules: [CLAUDE.md](../CLAUDE.md)

## Tests

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

Every test runs against `MockTello`; no drone is needed.
