# ui-blake

Minimal realtime interview UI for AI Blake (v1).

## Run

```bash
cd ui-blake
npm install
npm run dev
```

Set environment in `ui-blake/.env.local` (or `project/.env`):

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_AGENT_ID`
- `ELEVENLABS_VOICE_ID` (optional if agent default voice is already set)

This app stores sessions under `ui-blake/data/sessions/<session_id>/`.

## API Routes

- `POST /api/eleven/signed-url`
- `POST /api/session/start`
- `POST /api/session/event`
- `POST /api/session/end`
- `GET /api/session/export?id=<session_id>`

## Session Artifacts

Each session folder writes:

- `meta.json`
- `transcript.json`
- `events.jsonl`
- `mic.webm`
- `assistant.webm`
