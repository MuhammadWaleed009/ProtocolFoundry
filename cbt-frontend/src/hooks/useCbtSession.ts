// cbt-frontend/src/hooks/useCbtSession.ts
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  approve,
  createSession,
  latestRun,
  pendingApproval,
  runSession,
  type RunRecord,
} from "../lib/api";
import { connectWs, type WsMessage } from "../lib/ws";

const LS_KEY = "cbt_thread_id";

/** Minimal safe GraphState shape for UI blackboard panels */
export type Blackboard = {
  input_text?: string;
  require_human_approval?: boolean;

  request?: any;
  drafts?: any[];
  reviews?: any;
  supervisor?: any;
  final?: any;

  scratchpad?: any;
  metrics?: any;
  trace?: any[];

  current_node?: string;
  status?: string;

  halt_payload?: any;
  human_response?: any;
  human_feedback?: string | null;
};

function extractDraftMarkdownFromPending(pending: RunRecord | null): string {
  if (!pending) return "";
  if ((pending as any).final_markdown) return String((pending as any).final_markdown);

  const intr0 = (pending as any).pending_interrupt?.interrupts?.[0]?.value;
  const draft = intr0?.draft;
  const md = draft?.markdown;
  return typeof md === "string" ? md : "";
}

type ThinkingStatus = "idle" | "running" | "halted" | "resuming" | "completed" | "failed";
type StageStatus = "pending" | "active" | "done" | "error";

type StageInfo = {
  status: StageStatus;
  ts?: string;
  note?: string; // latest summary for that stage
  signals?: Record<string, any>;
};

export type Thinking = {
  status: ThinkingStatus;
  runId?: string;
  step?: string;
  detail?: string;
  updatedAt?: string;
  history: { ts?: string; label: string }[];
  stages: Record<string, StageInfo>;
};

const PIPELINE = ["intake", "drafter", "safety", "critic", "supervisor", "finalize", "human_review"] as const;
type NodeName = (typeof PIPELINE)[number];

function nodeToStep(node?: string): string {
  switch (node) {
    case "intake": return "Intake";
    case "drafter": return "Drafting";
    case "safety": return "Safety check";
    case "critic": return "Critic review";
    case "supervisor": return "Supervisor decision";
    case "finalize": return "Finalizing";
    case "human_review": return "Waiting for approval";
    default: return node ? `Step: ${node}` : "";
  }
}

function hintForNode(node?: string): string {
  switch (node) {
    case "intake": return "Parsing request…";
    case "drafter": return "Generating draft…";
    case "safety": return "Running safety checks…";
    case "critic": return "Reviewing quality…";
    case "supervisor": return "Deciding finalize vs revise…";
    case "finalize": return "Finalizing output…";
    case "human_review": return "Waiting for your approval…";
    default: return node ? `Working on ${node}…` : "";
  }
}

function initStages(): Record<string, StageInfo> {
  const out: Record<string, StageInfo> = {};
  for (const n of PIPELINE) out[n] = { status: "pending" };
  return out;
}

function nextNode(node?: string): NodeName | undefined {
  if (!node) return "intake";
  const idx = PIPELINE.indexOf(node as NodeName);
  if (idx < 0) return undefined;
  return PIPELINE[idx + 1];
}

function pushHistory(prev: Thinking, label: string, ts?: string): Thinking {
  const last = prev.history?.[0]?.label;
  if (last && last === label) {
    return { ...prev, updatedAt: ts ?? prev.updatedAt };
  }
  return {
    ...prev,
    updatedAt: ts ?? prev.updatedAt,
    history: [{ ts, label }, ...prev.history].slice(0, 30),
  };
}

function stageIcon(status: StageStatus): string {
  if (status === "done") return "✅";
  if (status === "active") return "⏳";
  if (status === "error") return "❌";
  return "…";
}

function buildPipelineLine(stages: Record<string, StageInfo>): string {
  const parts: string[] = [];

  const draft = stages.drafter;
  if (draft) {
    const v = draft.signals?.draft_version ?? draft.signals?.iteration;
    parts.push(`Draft ${stageIcon(draft.status)}${v != null ? ` (v${v})` : ""}`);
  }

  const safety = stages.safety;
  if (safety) {
    const sp = safety.signals?.safety_pass;
    const req = safety.signals?.required_changes_count;
    if (sp === true) parts.push("Safety ✅");
    else if (sp === false) parts.push(`Safety ⚠️${typeof req === "number" ? ` (${req})` : ""}`);
    else parts.push(`Safety ${stageIcon(safety.status)}`);
  }

  const critic = stages.critic;
  if (critic) {
    const qp = critic.signals?.quality_pass;
    const score = critic.signals?.quality_score;
    const issues = critic.signals?.issues_count;
    if (qp === true) parts.push(`Quality ✅${typeof score === "number" ? ` (${score})` : ""}`);
    else if (qp === false) parts.push(`Quality ⚠️${typeof issues === "number" ? ` (${issues})` : ""}`);
    else parts.push(`Quality ${stageIcon(critic.status)}`);
  }

  const sup = stages.supervisor;
  if (sup) {
    const action = sup.signals?.action;
    if (typeof action === "string" && action) parts.push(`Supervisor: ${action}`);
    else parts.push(`Supervisor ${stageIcon(sup.status)}`);
  }

  const fin = stages.finalize;
  if (fin) parts.push(`Finalize ${stageIcon(fin.status)}`);

  const hr = stages.human_review;
  if (hr && hr.status !== "pending") parts.push(`Approval ${stageIcon(hr.status)}`);

  return parts.join(" • ");
}

function stagesFromPendingInterrupt(p: RunRecord | null): Record<string, StageInfo> | null {
  const intr = (p as any)?.pending_interrupt?.interrupts?.[0]?.value;
  const d = intr?.draft;
  if (!d || typeof d !== "object") return null;

  const stages = initStages();

  // If we are at human gate, earlier steps were completed at least once.
  stages.intake.status = "done";
  stages.drafter.status = "done";
  stages.finalize.status = "done";
  stages.human_review.status = "active";

  const safetyPass = d?.reviews?.safety?.safety_pass;
  const req = d?.reviews?.safety?.required_changes;
  stages.safety.status = "done";
  stages.safety.signals = {
    safety_pass: safetyPass,
    required_changes_count: Array.isArray(req) ? req.length : null,
  };

  const qualityPass = d?.reviews?.critic?.quality_pass;
  const qualityScore = d?.reviews?.critic?.quality_score;
  const issues = d?.reviews?.critic?.issues;
  stages.critic.status = "done";
  stages.critic.signals = {
    quality_pass: qualityPass,
    quality_score: qualityScore,
    issues_count: Array.isArray(issues) ? issues.length : null,
  };

  const action = d?.supervisor?.action;
  const rationale = d?.supervisor?.rationale;
  stages.supervisor.status = "done";
  stages.supervisor.signals = {
    action,
    rationale: typeof rationale === "string" ? rationale.slice(0, 240) : null,
  };

  return stages;
}

/** Helper: safe object check */
function isObj(x: any): x is Record<string, any> {
  return !!x && typeof x === "object" && !Array.isArray(x);
}

export function useCbtSession() {
  const [threadId, setThreadId] = useState<string>(() => localStorage.getItem(LS_KEY) || "");
  const [wsStatus, setWsStatus] = useState<"idle" | "open" | "closed" | "error">("idle");
  const [events, setEvents] = useState<WsMessage[]>([]);
  const [pending, setPending] = useState<RunRecord | null>(null);
  const [latest, setLatest] = useState<RunRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ✅ NEW: live blackboard state (from WS node_update.state)
  const [blackboard, setBlackboard] = useState<Blackboard | null>(null);

  const [thinking, setThinking] = useState<Thinking>({
    status: "idle",
    history: [],
    stages: initStages(),
  });

  const wsRef = useRef<{ close: () => void; ping: () => void } | null>(null);

  // ✅ force thinking to match server truth (REST fallback)
  const syncThinkingFromServer = useCallback((p: RunRecord | null, l: RunRecord | null) => {
    setThinking((prev) => {
      const ts = new Date().toISOString();

      if ((p as any)?.status === "HALTED") {
        const rebuilt = stagesFromPendingInterrupt(p) ?? prev.stages;
        const pipeline = buildPipelineLine(rebuilt);

        return pushHistory(
          {
            ...prev,
            status: "halted",
            runId: (p as any).run_id ?? prev.runId,
            step: "Waiting for approval",
            detail: pipeline ? `Draft ready • ${pipeline}` : "Needs human approval.",
            updatedAt: ts,
            stages: rebuilt,
            history: prev.history,
          },
          "HALTED (awaiting approval)",
          ts
        );
      }

      if ((l as any)?.status === "COMPLETED") {
        const stages = { ...prev.stages };
        for (const k of Object.keys(stages)) {
          if (stages[k].status === "pending" || stages[k].status === "active") stages[k].status = "done";
        }

        return pushHistory(
          {
            ...prev,
            status: "completed",
            runId: (l as any).run_id ?? prev.runId,
            step: "Completed",
            detail: "Done.",
            updatedAt: ts,
            stages,
            history: prev.history,
          },
          "Completed",
          ts
        );
      }

      if ((l as any)?.status === "FAILED") {
        return pushHistory(
          {
            ...prev,
            status: "failed",
            runId: (l as any).run_id ?? prev.runId,
            step: "Failed",
            detail: (l as any).error ? String((l as any).error) : "Failed.",
            updatedAt: ts,
            history: prev.history,
          },
          "Failed",
          ts
        );
      }

      return prev;
    });
  }, []);

  const refresh = useCallback(async (id?: string) => {
    const t = id ?? threadId;
    if (!t) return;

    try {
      setError(null);
      const [p, l] = await Promise.all([pendingApproval(t), latestRun(t)]);
      setPending(p.pending);
      setLatest(l.latest);

      // ✅ if your RunRecord includes persisted `state`, use it
      const stateFromRuns =
        (p.pending as any)?.state && isObj((p.pending as any).state)
          ? (p.pending as any).state
          : (l.latest as any)?.state && isObj((l.latest as any).state)
            ? (l.latest as any).state
            : null;

      if (stateFromRuns) setBlackboard(stateFromRuns as Blackboard);

      syncThinkingFromServer(p.pending, l.latest);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }, [threadId, syncThinkingFromServer]);

  const startNewSession = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await createSession("human_optional");
      localStorage.setItem(LS_KEY, res.thread_id);
      setThreadId(res.thread_id);
      setEvents([]);
      setPending(null);
      setLatest(null);
      setBlackboard(null);
      setThinking({ status: "idle", history: [], stages: initStages() });
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
    setPending(null);
    setLatest(null);
    setBlackboard(null);
    setWsStatus("idle");
    setError(null);
    setThinking({ status: "idle", history: [], stages: initStages() });
  }, []);

  const run = useCallback(async (inputText: string, requireApproval: boolean) => {
    if (!threadId) return;
    setBusy(true);
    setError(null);

    setThinking((prev) =>
      pushHistory(
        {
          ...prev,
          status: "running",
          step: "Intake",
          detail: "Starting run…",
          stages: { ...initStages(), intake: { status: "active" } },
        },
        "Starting run…",
        new Date().toISOString()
      )
    );

    try {
      await runSession(threadId, { input_text: inputText, require_human_approval: requireApproval });
      // WS will stream updates; REST refresh is fallback
      await refresh(threadId);
    } catch (e: any) {
      setError(e?.message || String(e));
      setThinking((prev) =>
        pushHistory(
          { ...prev, status: "failed", step: "Failed", detail: e?.message || String(e) },
          "Run failed",
          new Date().toISOString()
        )
      );
    } finally {
      setBusy(false);
    }
  }, [threadId, refresh]);

  const doApprove = useCallback(async (editedText?: string) => {
    if (!threadId) return;
    setBusy(true);
    setError(null);

    setThinking((prev) =>
      pushHistory(
        { ...prev, status: "resuming", step: "Resuming", detail: "Submitting approval…" },
        "Submitting approval…",
        new Date().toISOString()
      )
    );

    try {
      await approve(threadId, { approved: true, edited_text: editedText ?? null });
      await refresh(threadId);
    } catch (e: any) {
      setError(e?.message || String(e));
      setThinking((prev) =>
        pushHistory(
          { ...prev, status: "failed", step: "Failed", detail: e?.message || String(e) },
          "Approve failed",
          new Date().toISOString()
        )
      );
    } finally {
      setBusy(false);
    }
  }, [threadId, refresh]);

  const doReject = useCallback(async (feedback: string) => {
    if (!threadId) return;
    setBusy(true);
    setError(null);

    setThinking((prev) =>
      pushHistory(
        { ...prev, status: "resuming", step: "Resuming", detail: "Submitting rejection + feedback…" },
        "Submitting rejection…",
        new Date().toISOString()
      )
    );

    try {
      await approve(threadId, { approved: false, feedback: feedback || "Please revise." });
      await refresh(threadId);
    } catch (e: any) {
      setError(e?.message || String(e));
      setThinking((prev) =>
        pushHistory(
          { ...prev, status: "failed", step: "Failed", detail: e?.message || String(e) },
          "Reject failed",
          new Date().toISOString()
        )
      );
    } finally {
      setBusy(false);
    }
  }, [threadId, refresh]);

  // connect WS when thread changes
  useEffect(() => {
    wsRef.current?.close();
    wsRef.current = null;

    if (!threadId) return;

    const conn = connectWs(
      threadId,
      (msg) => {
        setEvents((prev) => [msg, ...prev].slice(0, 80));

        // ✅ NEW: if backend sends full state snapshot, update blackboard immediately
        if (msg.type === "node_update") {
          const s = (msg as any).state;
          if (isObj(s)) setBlackboard(s as Blackboard);
        }

        setThinking((prev) => {
          const ts = (msg as any).ts ?? new Date().toISOString();

          if (msg.type === "run_started") {
            const stages = initStages();
            stages.intake.status = "active";
            return pushHistory(
              {
                ...prev,
                status: "running",
                runId: (msg as any).run_id ?? prev.runId,
                step: "Intake",
                detail: "Run started.",
                stages,
              },
              "Run started",
              ts
            );
          }

          if (msg.type === "resume_started") {
            return pushHistory(
              {
                ...prev,
                status: "resuming",
                runId: (msg as any).run_id ?? prev.runId,
                step: "Resuming",
                detail: "Resuming from approval…",
              },
              "Resume started",
              ts
            );
          }

          if (msg.type === "node_update") {
            const node = (msg as any).node as string | undefined;
            const stepName = nodeToStep(node) || "Update";
            const summary =
              typeof (msg as any).summary === "string" && (msg as any).summary.trim()
                ? String((msg as any).summary).trim()
                : hintForNode(node);

            const signals = isObj((msg as any).signals) ? (msg as any).signals : {};
            const isHalt = !!signals.halted;

            const stages = { ...(prev.stages ?? initStages()) };

            if (node) {
              // If halted at human_review, keep it active (not done)
              if (isHalt || node === "human_review") {
                stages[node] = { ...(stages[node] ?? { status: "pending" }), status: "active", note: summary, signals, ts };
              } else {
                stages[node] = { ...(stages[node] ?? { status: "pending" }), status: "done", note: summary, signals, ts };
                const n = nextNode(node);
                if (n && stages[n]?.status === "pending") {
                  stages[n] = { ...(stages[n] ?? { status: "pending" }), status: "active", ts };
                }
              }
            }

            const pipeline = buildPipelineLine(stages);

            // “GPT-like” detail = latest summary + pipeline line
            const detail = `${summary}${pipeline ? ` • ${pipeline}` : ""}`;

            // status transitions
            const status: ThinkingStatus =
              isHalt || node === "human_review"
                ? "halted"
                : prev.status === "resuming"
                  ? "resuming"
                  : "running";

            return pushHistory(
              {
                ...prev,
                status,
                runId: (msg as any).run_id ?? prev.runId,
                step: nodeToStep(node) || prev.step,
                detail,
                updatedAt: ts,
                stages,
                history: prev.history,
              },
              `${stepName} — ${summary}`,
              ts
            );
          }

          if (msg.type === "halt_required") {
            // fallback (backend also emits node_update before halt_required)
            const stages = { ...(prev.stages ?? initStages()) };
            stages.human_review = { ...(stages.human_review ?? { status: "pending" }), status: "active", ts };
            const pipeline = buildPipelineLine(stages);

            return pushHistory(
              {
                ...prev,
                status: "halted",
                runId: (msg as any).run_id ?? prev.runId,
                step: "Waiting for approval",
                detail: pipeline ? `Draft ready • ${pipeline}` : "Needs human approval.",
                updatedAt: ts,
                stages,
                history: prev.history,
              },
              "HALTED (awaiting approval)",
              ts
            );
          }

          if (msg.type === "run_completed" || msg.type === "resume_completed") {
            const stages = { ...(prev.stages ?? initStages()) };
            for (const k of Object.keys(stages)) {
              if (stages[k].status === "pending" || stages[k].status === "active") stages[k].status = "done";
            }
            return pushHistory(
              {
                ...prev,
                status: "completed",
                runId: (msg as any).run_id ?? prev.runId,
                step: "Completed",
                detail: "Done.",
                stages,
              },
              "Completed",
              ts
            );
          }

          if (msg.type === "run_failed" || msg.type === "resume_failed") {
            return pushHistory(
              {
                ...prev,
                status: "failed",
                runId: (msg as any).run_id ?? prev.runId,
                step: "Failed",
                detail: (msg as any).error ? String((msg as any).error) : "Failed.",
              },
              "Failed",
              ts
            );
          }

          return prev;
        });

        // Keep REST refresh only for terminal events (fallback correctness)
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
    refresh(threadId);

    return () => conn.close();
  }, [threadId, refresh]);

  // ✅ draft markdown prefers blackboard real-time state; falls back to pending interrupt
  const draftMarkdown = useMemo(() => {
    const mdFromBlackboard =
      (blackboard as any)?.final?.markdown ??
      (Array.isArray((blackboard as any)?.drafts) && (blackboard as any).drafts.length
        ? (blackboard as any).drafts[(blackboard as any).drafts.length - 1]?.markdown
        : "");

    if (typeof mdFromBlackboard === "string" && mdFromBlackboard.trim()) return mdFromBlackboard;
    return extractDraftMarkdownFromPending(pending);
  }, [blackboard, pending]);

  return {
    threadId,
    wsStatus,
    events,
    pending,
    latest,
    busy,
    error,

    // ✅ NEW
    blackboard,

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
