# Cerina Protocol Foundry — Frontend (React + Vite)

## Overview
The dashboard provides a transparent view of the LangGraph pipeline, human-in-the-loop halts, and live blackboard state. It consumes REST + WebSocket streams from the backend and offers a PDF export of completed protocols.

## Key features
- Create/clear sessions and launch runs with optional human approval.
- Live pipeline view (WS): node progression, halted state, recent actions.
- Pending approval panel with inline approve/reject + draft preview.
- Blackboard panels: drafts/final preview, scratchpad notes, WS event log.
- PDF export of the final protocol (includes user query).

## Running locally
```bash
cd cbt-frontend
npm install
npm run dev
```
Set the backend base URL via `VITE_API_BASE_URL` and WS base via `VITE_WS_BASE_URL` if not using defaults (`http://127.0.0.1:8000`, `ws://127.0.0.1:8000`).

## UI flow
- **Create session** → **Launch run** → watch live pipeline updates via WS.
- If halted, approve/reject in Pending approval. After completion, view/export the final protocol.
- WS events panel can be expanded/collapsed; REST endpoints serve as fallback.

## Notes
- Intent guard stops out-of-scope prompts; valid CBT prompts run the full pipeline.
- The dashboard favors live updates; when WS is unavailable, use the Refresh button (REST fallback).
