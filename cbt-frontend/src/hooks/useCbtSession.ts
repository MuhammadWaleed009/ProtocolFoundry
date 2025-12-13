// cbt-frontend/src/hooks/useCbtSession.ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { approve, createSession, latestRun, pendingApproval, runSession, type RunRecord } from "../lib/api";
import { connectWs, type WsMessage } from "../lib/ws";

const LS_KEY = "cbt_thread_id";

function extractDraftMarkdown(pending: RunRecord | null): string {
  if (!pending) return "";
  if (pending.final_markdown) return pending.final_markdown;

  const intr0 = pending.pending_interrupt?.interrupts?.[0]?.value;
  const draft = intr0?.draft;
  const md = draft?.markdown;
  return typeof md === "string" ? md : "";
}

type ThinkingStatus = "idle" | "running" | "halted" | "resuming" | "completed" | "failed";

export type Thinking = {
  status: ThinkingStatus;
  runId?: string;
  step?: string;
  detail?: string;
  updatedAt?: string;
  history: { ts?: string; label: string }[];
};

function nodeToStep(node?: string): string {
  switch (node) {
    case "intake":
      return "Intake";
    case "drafter":
      return "Drafting";
    case "safety":
      return "Safety check";
    case "critic":
      return "Critic review";
    case "supervisor":
      return "Supervisor decision";
    case "finalize":
      return "Finalizing";
    case "human_review":
      return "Waiting for human approval";
    default:
      return node ? `Step: ${node}` : "";
  }
}

function pushHistory(prev: Thinking, label: string, ts?: string): Thinking {
  return {
    ...prev,
    updatedAt: ts ?? prev.updatedAt,
    history: [{ ts, label }, ...prev.history].slice(0, 12),
  };
}

export function useCbtSession() {
  const [threadId, setThreadId] = useState<string>(() => localStorage.getItem(LS_KEY) || "");
  const [wsStatus, setWsStatus] = useState<"idle" | "open" | "closed" | "error">("idle");
  const [events, setEvents] = useState<WsMessage[]>([]);
  const [pending, setPending] = useState<RunRecord | null>(null);
  const [latest, setLatest] = useState<RunRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [thinking, setThinking] = useState<Thinking>({ status: "idle", history: [] });

  const wsRef = useRef<{ close: () => void; ping: () => void } | null>(null);

  const refresh = useCallback(
    async (id?: string) => {
      const t = id ?? threadId;
      if (!t) return;

      try {
        setError(null);
        const [p, l] = await Promise.all([pendingApproval(t), latestRun(t)]);
        setPending(p.pending);
        setLatest(l.latest);
      } catch (e: any) {
        setError(e?.message || String(e));
      }
    },
    [threadId]
  );

  const startNewSession = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await createSession("human_optional");
      localStorage.setItem(LS_KEY, res.thread_id);
      setThreadId(res.thread_id);
      setThinking({ status: "idle", history: [] });
      setEvents([]);
      setPending(null);
      setLatest(null);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const clearSession = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    localStorage.removeItem(LS_KEY);
    setThreadId("");
    setEvents([]);
    setThinking({ status: "idle", history: [] });
    setPending(null);
    setLatest(null);
    setWsStatus("idle");
    setError(null);
  }, []);

  const run = useCallback(
    async (inputText: string, requireApproval: boolean) => {
      if (!threadId) return;
      setBusy(true);
      setError(null);

      // optimistic “thinking”
      setThinking((prev) =>
        pushHistory(
          {
            ...prev,
            status: "running",
            step: "Starting",
            detail: undefined,
          },
          "Starting run…"
        )
      );

      try {
        await runSession(threadId, { input_text: inputText, require_human_approval: requireApproval });
        await refresh(threadId);
      } catch (e: any) {
        setError(e?.message || String(e));
        setThinking((prev) => pushHistory({ ...prev, status: "failed", step: "Failed" }, "Failed"));
      } finally {
        setBusy(false);
      }
    },
    [threadId, refresh]
  );

  const doApprove = useCallback(
    async (editedText?: string) => {
      if (!threadId) return;
      setBusy(true);
      setError(null);

      setThinking((prev) =>
        pushHistory(
          {
            ...prev,
            status: "resuming",
            step: "Resuming",
            detail: undefined,
          },
          "Approved — resuming…"
        )
      );

      try {
        await approve(threadId, { approved: true, edited_text: editedText ?? null });
        await refresh(threadId);
      } catch (e: any) {
        setError(e?.message || String(e));
        setThinking((prev) => pushHistory({ ...prev, status: "failed", step: "Failed" }, "Failed"));
      } finally {
        setBusy(false);
      }
    },
    [threadId, refresh]
  );

  const doReject = useCallback(
    async (feedback: string) => {
      if (!threadId) return;
      setBusy(true);
      setError(null);

      setThinking((prev) =>
        pushHistory(
          {
            ...prev,
            status: "resuming",
            step: "Revising",
            detail: feedback ? `Feedback: ${feedback}` : undefined,
          },
          "Rejected — requesting revision…"
        )
      );

      try {
        await approve(threadId, { approved: false, feedback: feedback || "Please revise." });
        await refresh(threadId);
      } catch (e: any) {
        setError(e?.message || String(e));
        setThinking((prev) => pushHistory({ ...prev, status: "failed", step: "Failed" }, "Failed"));
      } finally {
        setBusy(false);
      }
    },
    [threadId, refresh]
  );

  // connect WS when thread changes
  useEffect(() => {
    wsRef.current?.close();
    wsRef.current = null;

    if (!threadId) return;

    const conn = connectWs(
      threadId,
      (msg) => {
        setEvents((prev) => [msg, ...prev].slice(0, 30));

        // ✅ update “thinking” from WS
        setThinking((prev) => {
          const ts = msg.ts;
          const runId = msg.run_id ?? prev.runId;

          if (msg.type === "run_started") {
            const next = { ...prev, status: "running" as const, runId, step: "Starting", updatedAt: ts };
            return pushHistory(next, "Run started", ts);
          }

          if (msg.type === "state_update") {
            const upd = (msg as any).update ?? {};
            const node = Object.keys(upd)[0];
            const step = nodeToStep(node);
            if (!step) return prev;
            const next = { ...prev, status: "running" as const, runId, step, updatedAt: ts };
            return pushHistory(next, step, ts);
          }

          if (msg.type === "halt_required") {
            const next = { ...prev, status: "halted" as const, runId, step: "Waiting for approval", updatedAt: ts };
            return pushHistory(next, "HALTED — awaiting approval", ts);
          }

          if (msg.type === "resume_started") {
            const next = { ...prev, status: "resuming" as const, runId, step: "Resuming", updatedAt: ts };
            return pushHistory(next, "Resume started", ts);
          }

          if (msg.type === "resume_completed" || msg.type === "run_completed") {
            const next = { ...prev, status: "completed" as const, runId, step: "Done", updatedAt: ts };
            return pushHistory(next, "Completed", ts);
          }

          if (msg.type === "run_failed" || msg.type === "resume_failed") {
            const err = (msg as any).error ? String((msg as any).error) : "";
            const next = { ...prev, status: "failed" as const, runId, step: "Failed", detail: err, updatedAt: ts };
            return pushHistory(next, `Failed${err ? `: ${err}` : ""}`, ts);
          }

          return prev;
        });

        // On key events, refetch server truth
        const t = msg.type;
        if (
          t === "halt_required" ||
          t === "run_completed" ||
          t === "resume_completed" ||
          t === "run_failed" ||
          t === "resume_failed"
        ) {
          refresh(threadId);
        }
      },
      (s) => setWsStatus(s)
    );

    wsRef.current = conn;

    // initial fetch
    refresh(threadId);

    return () => conn.close();
  }, [threadId, refresh]);

  const draftMarkdown = useMemo(() => extractDraftMarkdown(pending), [pending]);

  return {
    threadId,
    wsStatus,
    events,
    pending,
    latest,
    busy,
    error,
    thinking,

    draftMarkdown,

    startNewSession,
    clearSession,
    refresh,
    run,
    doApprove,
    doReject,
  };
}
