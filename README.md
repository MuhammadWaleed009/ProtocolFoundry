# Cerina Protocol Foundry

LangGraph + FastAPI backend with a React dashboard and MCP interface for building CBT protocols with human-in-the-loop approval.

## Architecture (high level)
```mermaid
flowchart LR
  subgraph Interfaces
    REST["REST (FastAPI)"] -->|run/approve/history| API
    WS["WebSocket"] -->|node_update/state_update| API
    MCP["MCP (stdio tool)"] -->|build_cbt_protocol| API
  end

  subgraph API["FastAPI + LangGraph"]
    IG[intent_guard]
    IN[intake]
    DR[drafter]
    SA[safety]
    CR[critic]
    SV[supervisor]
    FI[finalize]
    HR[human_review]
    CP[(Checkpointer\nPostgres/SQLite)]
  end

  REST --> IG
  WS --> IG
  MCP --> IG

  IG -->|relevant| IN
  IG -->|out-of-scope| OUT["Out-of-scope response"]
  IN --> DR --> SA --> CR --> SV --> FI --> HR
  HR -->|approve| END1["Completed"]
  HR -->|reject| DR
  SV -->|revise| DR
  SV -->|finalize| FI

  CP --- IG
  CP --- IN
  CP --- DR
  CP --- SA
  CP --- CR
  CP --- SV
  CP --- FI
  CP --- HR

  subgraph DB["Persistence"]
    RUNS[(runs & run_events)]
  end

  API --> RUNS
  HR -->|pending_interrupt| RUNS
```

## Backend (cbt_backend)
- **Agents:** intent_guard → intake → drafter → safety → critic → supervisor → finalize → human_review (halts for approval; resume applies edits or loops back).
- **State:** drafts, reviews, supervisor decision, metrics, scratchpad, final payload, human feedback, pending interrupts.
- **Persistence:** checkpoints via langgraph-checkpoint-* (Postgres/SQLite); run metadata/events + pending_interrupt column ensured on startup.
- **Interfaces:** REST (sessions, run, approve, runs/events), WS (live updates), MCP stdio tool `build_cbt_protocol`.

### Backend setup
```bash
cd cbt_backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# env (example)
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cbt?sslmode=disable
export CHECKPOINT_BACKEND=postgres
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4o-mini

# optional postgres
docker-compose up -d postgres

# run API
uvicorn app.main:app --reload --port 8000

# run MCP (stdio)
python3 -m mcp_server.server
```

### Backend testing
```bash
cd cbt_backend
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/cbt?sslmode=disable
pytest tests/test_persistence.py
```

## Frontend (cbt-frontend)
- React/Vite dashboard with live WS pipeline view, pending approval actions, scratchpad, events log, and PDF export of finalized protocols.
- REST is used as fallback (Refresh button) when WS is unavailable.

### Frontend setup
```bash
cd cbt-frontend
npm install
npm run dev
```
Set env if needed: `VITE_API_BASE_URL` (default `http://127.0.0.1:8000`), `VITE_WS_BASE_URL` (default `ws://127.0.0.1:8000`).

## MCP usage
- From `cbt_backend`: `python3 -m mcp_server.server`
- Connect via MCP Inspector or Claude Desktop custom MCP server (stdio command above) and call `build_cbt_protocol` with your prompt. `auto_approve_on_halt` can finalize halted runs automatically; set `require_human_approval` to enforce halts.
