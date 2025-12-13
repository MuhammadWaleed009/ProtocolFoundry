RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id UUID PRIMARY KEY,
  thread_id TEXT NOT NULL REFERENCES sessions(thread_id) ON DELETE CASCADE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  status TEXT NOT NULL, -- RUNNING | HALTED | COMPLETED | FAILED
  require_human_approval BOOLEAN NOT NULL DEFAULT TRUE,

  input_text TEXT,

  -- snapshot fields for dashboard
  iteration INT,
  safety_score DOUBLE PRECISION,
  quality_score DOUBLE PRECISION,

  final_markdown TEXT,
  final_data JSONB,
  reviews JSONB,
  supervisor JSONB,
  human_edit JSONB,

  error TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_thread_created ON runs(thread_id, created_at DESC);
"""

RUN_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS run_events (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  seq INT,
  event_type TEXT NOT NULL,
  payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_ts ON run_events(run_id, ts DESC);
"""

RUNS_ALTER_SQL = """
ALTER TABLE runs ADD COLUMN IF NOT EXISTS pending_interrupt JSONB;
"""