import { useMemo, useState } from "react";
import "./App.css";
import { useCbtSession } from "./hooks/useCbtSession";

function prettyJson(x: any) {
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
}

function thinkingDot(status: string) {
  if (status === "running" || status === "resuming") return "🟡";
  if (status === "halted") return "🟠";
  if (status === "completed") return "🟢";
  if (status === "failed") return "🔴";
  return "⚪️";
}

type ThinkingSafe = {
  status: string;
  runId?: string;
  step?: string;
  detail?: string;
  updatedAt?: string;
  history?: { ts?: string; label: string }[];
  stages?: Record<string, any>;
};

function badge(text: string, tone: "neutral" | "good" | "warn" | "bad" = "neutral") {
  const bg =
    tone === "good"
      ? "rgba(34,197,94,0.15)"
      : tone === "warn"
      ? "rgba(234,179,8,0.15)"
      : tone === "bad"
      ? "rgba(239,68,68,0.15)"
      : "rgba(148,163,184,0.12)";

  const border =
    tone === "good"
      ? "rgba(34,197,94,0.45)"
      : tone === "warn"
      ? "rgba(234,179,8,0.45)"
      : tone === "bad"
      ? "rgba(239,68,68,0.45)"
      : "rgba(148,163,184,0.25)";

  return (
    <span
      style={{
        padding: "3px 8px",
        borderRadius: 999,
        background: bg,
        border: `1px solid ${border}`,
        fontSize: 12,
        opacity: 0.95,
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
}

function panel(title: string, children: any) {
  return (
    <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
      </div>
      <div style={{ marginTop: 10 }}>{children}</div>
    </div>
  );
}

function smallKv(k: string, v: any) {
  return (
    <div style={{ fontSize: 13, opacity: 0.85, marginBottom: 4 }}>
      <b>{k}:</b> {v ?? "-"}
    </div>
  );
}

export default function App() {
  const {
    threadId,
    wsStatus,
    events,
    pending,
    latest,
    busy,
    error,
    thinking,
    draftMarkdown,
    blackboard, // ✅ NEW from hook
    startNewSession,
    clearSession,
    run,
    doApprove,
    doReject,
    refresh,
  } = useCbtSession() as any;

  const thinkingSafe: ThinkingSafe = thinking ?? { status: "idle", history: [] };

  const [inputText, setInputText] = useState("Test run history");
  const [requireApproval, setRequireApproval] = useState(true);

  const [editedText, setEditedText] = useState("");
  const [feedback, setFeedback] = useState("Make it shorter (5 min) and add a 60-second version.");

  const statusLabel = useMemo(() => {
    if (pending?.status === "HALTED") return "HALTED (needs approval)";
    if (latest?.status === "COMPLETED") return "COMPLETED";
    if (latest?.status === "FAILED") return "FAILED";
    return threadId ? "READY" : "NO SESSION";
  }, [pending, latest, threadId]);

  const wsHint =
    wsStatus === "open"
      ? "WS connected"
      : wsStatus === "error"
      ? "WS error (REST still works)"
      : wsStatus === "closed"
      ? "WS disconnected (REST still works)"
      : "Connecting WS…";

  // Prefer real-time blackboard markdown if present
  const bbDraftMd =
    blackboard?.final?.markdown ||
    (Array.isArray(blackboard?.drafts) && blackboard.drafts.length
      ? blackboard.drafts[blackboard.drafts.length - 1]?.markdown
      : "");

  const draftPreviewMd =
    (typeof bbDraftMd === "string" && bbDraftMd.trim()) ? bbDraftMd : draftMarkdown;

  const bbTrace = Array.isArray(blackboard?.trace) ? blackboard.trace : [];
  const bbScratch = blackboard?.scratchpad ?? null;
  const bbReviews = blackboard?.reviews ?? null;
  const bbSupervisor = blackboard?.supervisor ?? null;
  const bbMetrics = blackboard?.metrics ?? null;
  const bbDrafts = Array.isArray(blackboard?.drafts) ? blackboard.drafts : [];
  const bbFinal = blackboard?.final ?? null;

  const safetyPass = bbReviews?.safety?.safety_pass;
  const qualityPass = bbReviews?.critic?.quality_pass;

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: 16, textAlign: "left" }}>
      <h2 style={{ marginTop: 0 }}>CBT Protocol UI</h2>

      {/* Top bar */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button onClick={startNewSession} disabled={busy}>
          Create session
        </button>
        <button onClick={clearSession} disabled={!threadId || busy}>
          Clear session
        </button>
        <button onClick={() => refresh()} disabled={!threadId || busy}>
          Refresh
        </button>

        <div style={{ opacity: 0.9 }}>
          <div>
            <b>thread_id:</b> {threadId || "-"}
          </div>
          <div>
            <b>WS:</b> {wsStatus} &nbsp; | &nbsp; <b>Status:</b> {statusLabel}
          </div>
          {threadId && <div style={{ fontSize: 13, opacity: 0.75 }}>{wsHint}</div>}
        </div>

        <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
          {typeof safetyPass === "boolean" &&
            badge(`Safety ${safetyPass ? "✅" : "⚠️"}`, safetyPass ? "good" : "warn")}
          {typeof qualityPass === "boolean" &&
            badge(`Quality ${qualityPass ? "✅" : "⚠️"}`, qualityPass ? "good" : "warn")}
          {blackboard?.current_node && badge(`Node: ${blackboard.current_node}`, "neutral")}
          {blackboard?.status && badge(`State: ${blackboard.status}`, blackboard.status === "FAILED" ? "bad" : "neutral")}
        </div>
      </div>

      {/* Thinking */}
      <div style={{ marginTop: 12, padding: 12, border: "1px solid #333", borderRadius: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <b>Thinking:</b>
          <span>
            {thinkingDot(thinkingSafe.status)} {thinkingSafe.step || thinkingSafe.status}
          </span>
          {!!thinkingSafe.runId && <span style={{ opacity: 0.7 }}>run: {thinkingSafe.runId}</span>}
          {!!thinkingSafe.updatedAt && <span style={{ opacity: 0.7 }}>@ {thinkingSafe.updatedAt}</span>}
          {busy && <span style={{ opacity: 0.75 }}>— Running…</span>}
        </div>

        {!!thinkingSafe.detail && (
          <div style={{ marginTop: 8, opacity: 0.9, fontSize: 13 }}>{thinkingSafe.detail}</div>
        )}

        <details style={{ marginTop: 10 }}>
          <summary>Live trace (client)</summary>
          <ul style={{ marginTop: 8, paddingLeft: 18 }}>
            {(thinkingSafe.history ?? []).map((h, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <span style={{ opacity: 0.7 }}>{h.ts ? `${h.ts} — ` : ""}</span>
                {h.label}
              </li>
            ))}
            {(thinkingSafe.history ?? []).length === 0 && <li style={{ opacity: 0.7 }}>No trace yet.</li>}
          </ul>
        </details>
      </div>

      {error && (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #f00", borderRadius: 8 }}>
          <b>Error:</b> {error}
        </div>
      )}

      <hr style={{ margin: "16px 0" }} />

      {/* Main grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Run controls */}
        {panel(
          "Run",
          <>
            <label style={{ display: "block", marginBottom: 6 }}>Input</label>
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              rows={5}
              style={{ width: "100%", padding: 10, borderRadius: 8 }}
            />

            <div style={{ marginTop: 10, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={requireApproval}
                  onChange={(e) => setRequireApproval(e.target.checked)}
                />
                Require human approval
              </label>

              <button onClick={() => run(inputText, requireApproval)} disabled={!threadId || busy || !inputText.trim()}>
                Run
              </button>

              {busy && <span style={{ opacity: 0.75 }}>Running…</span>}
            </div>

            <div style={{ marginTop: 12, opacity: 0.8, fontSize: 13 }}>
              Tip: WebSocket gives live progress; REST fallback keeps the UI usable.
            </div>
          </>
        )}

        {/* Pending approval */}
        {panel(
          "Pending approval",
          <>
            {!threadId && <div>Create a session first.</div>}
            {threadId && !pending && <div>No pending approval.</div>}

            {pending && (
              <>
                <div style={{ opacity: 0.8, fontSize: 13 }}>
                  <div><b>run_id:</b> {pending.run_id}</div>
                  <div><b>status:</b> {pending.status}</div>
                </div>

                <h4 style={{ marginTop: 12 }}>Draft preview</h4>
                <pre style={{ whiteSpace: "pre-wrap", padding: 12, borderRadius: 8, border: "1px solid #444" }}>
                  {draftPreviewMd || "(no draft markdown found)"}
                </pre>

                <h4 style={{ marginTop: 12 }}>Approve with optional edit</h4>
                <textarea
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  placeholder="(Optional) Paste edited markdown here"
                  rows={4}
                  style={{ width: "100%", padding: 10, borderRadius: 8 }}
                />

                <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button onClick={() => doApprove(editedText || undefined)} disabled={busy}>
                    Approve
                  </button>
                </div>

                <h4 style={{ marginTop: 12 }}>Reject with feedback</h4>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="Feedback for revision"
                  rows={3}
                  style={{ width: "100%", padding: 10, borderRadius: 8 }}
                />

                <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <button onClick={() => doReject(feedback)} disabled={busy}>
                    Reject
                  </button>
                </div>

                <details style={{ marginTop: 12 }}>
                  <summary>Raw pending JSON</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(pending)}</pre>
                </details>
              </>
            )}
          </>
        )}
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* Blackboard panels */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {panel(
          "Blackboard — Trace (server)",
          <>
            {!threadId && <div>Create a session first.</div>}
            {threadId && bbTrace.length === 0 && <div style={{ opacity: 0.75 }}>No trace yet.</div>}
            {bbTrace.length > 0 && (
              <ul style={{ marginTop: 8, paddingLeft: 18 }}>
                {[...bbTrace].slice(-20).reverse().map((t: any, i: number) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <span style={{ opacity: 0.7 }}>{t.ts ? `${t.ts} — ` : ""}</span>
                    <b style={{ opacity: 0.95 }}>{t.node || "node"}</b>:{" "}
                    <span style={{ opacity: 0.9 }}>{t.summary || ""}</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}

        {panel(
          "Blackboard — Scratchpad (public notes)",
          <>
            {!bbScratch && <div style={{ opacity: 0.75 }}>No scratchpad yet.</div>}
            {bbScratch && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                {Object.entries(bbScratch).map(([k, v]: any) => (
                  <div key={k} style={{ border: "1px solid #444", borderRadius: 10, padding: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <b style={{ textTransform: "capitalize" }}>{k}</b>
                      <span style={{ opacity: 0.6, fontSize: 12 }}>
                        {Array.isArray(v) ? `${v.length} items` : ""}
                      </span>
                    </div>
                    <div style={{ marginTop: 8, fontSize: 13, opacity: 0.9 }}>
                      {Array.isArray(v) && v.length > 0 ? (
                        <ul style={{ margin: 0, paddingLeft: 18 }}>
                          {v.slice(-6).map((s: any, i: number) => (
                            <li key={i} style={{ marginBottom: 4 }}>
                              {String(s)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <div style={{ opacity: 0.7 }}>—</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* Reviews + Supervisor + Metrics */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {panel(
          "Blackboard — Reviews",
          <>
            {!bbReviews && <div style={{ opacity: 0.75 }}>No reviews yet.</div>}
            {bbReviews && (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {typeof safetyPass === "boolean" &&
                    badge(`Safety ${safetyPass ? "passed" : "failed"}`, safetyPass ? "good" : "warn")}
                  {typeof qualityPass === "boolean" &&
                    badge(`Quality ${qualityPass ? "passed" : "failed"}`, qualityPass ? "good" : "warn")}
                </div>

                <details style={{ marginTop: 12 }}>
                  <summary>Raw reviews JSON</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(bbReviews)}</pre>
                </details>
              </>
            )}
          </>
        )}

        {panel(
          "Blackboard — Supervisor + Metrics",
          <>
            {!bbSupervisor && <div style={{ opacity: 0.75 }}>No supervisor decision yet.</div>}
            {bbSupervisor && (
              <>
                {smallKv("action", bbSupervisor.action)}
                {smallKv("rationale", bbSupervisor.rationale)}
              </>
            )}

            <div style={{ marginTop: 12 }} />

            {!bbMetrics && <div style={{ opacity: 0.75 }}>No metrics yet.</div>}
            {bbMetrics && (
              <>
                {smallKv("iteration", bbMetrics.iteration)}
                {smallKv("max_iterations", bbMetrics.max_iterations)}
                {smallKv("safety_score", bbMetrics.safety_score)}
                {smallKv("quality_score", bbMetrics.quality_score)}
              </>
            )}

            {(bbSupervisor || bbMetrics) && (
              <details style={{ marginTop: 12 }}>
                <summary>Raw supervisor/metrics JSON</summary>
                <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson({ supervisor: bbSupervisor, metrics: bbMetrics })}</pre>
              </details>
            )}
          </>
        )}
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* Drafts + Final */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {panel(
          `Blackboard — Drafts (${bbDrafts.length})`,
          <>
            {bbDrafts.length === 0 && <div style={{ opacity: 0.75 }}>No drafts yet.</div>}
            {bbDrafts.length > 0 && (
              <details open>
                <summary>Show latest draft</summary>
                <div style={{ marginTop: 10, fontSize: 13, opacity: 0.85 }}>
                  {smallKv("version", bbDrafts[bbDrafts.length - 1]?.version)}
                  {smallKv("created_at", bbDrafts[bbDrafts.length - 1]?.created_at)}
                  {smallKv("source", bbDrafts[bbDrafts.length - 1]?.source)}
                  {smallKv("notes", bbDrafts[bbDrafts.length - 1]?.notes)}
                </div>
                <pre style={{ whiteSpace: "pre-wrap", padding: 12, borderRadius: 8, border: "1px solid #444" }}>
                  {bbDrafts[bbDrafts.length - 1]?.markdown || "(no markdown)"}
                </pre>

                <details style={{ marginTop: 10 }}>
                  <summary>Raw drafts JSON</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(bbDrafts)}</pre>
                </details>
              </details>
            )}
          </>
        )}

        {panel(
          "Blackboard — Final",
          <>
            {!bbFinal && <div style={{ opacity: 0.75 }}>No final yet.</div>}
            {bbFinal && (
              <>
                <div style={{ fontSize: 13, opacity: 0.85 }}>
                  {smallKv("created_at", bbFinal.created_at)}
                </div>

                <h4 style={{ marginTop: 12 }}>Final markdown</h4>
                <pre style={{ whiteSpace: "pre-wrap", padding: 12, borderRadius: 8, border: "1px solid #444" }}>
                  {bbFinal.markdown || "(no markdown)"}
                </pre>

                <details style={{ marginTop: 12 }}>
                  <summary>Raw final JSON</summary>
                  <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(bbFinal)}</pre>
                </details>
              </>
            )}
          </>
        )}
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* Latest (REST) */}
      <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
        <h3>Latest run (REST)</h3>
        {!threadId && <div>Create a session first.</div>}
        {threadId && !latest && <div>No latest run yet.</div>}

        {latest && (
          <>
            <div style={{ opacity: 0.8, fontSize: 13 }}>
              <div><b>run_id:</b> {latest.run_id}</div>
              <div><b>status:</b> {latest.status}</div>
            </div>

            <h4 style={{ marginTop: 12 }}>Final markdown</h4>
            <pre style={{ whiteSpace: "pre-wrap", padding: 12, borderRadius: 8, border: "1px solid #444" }}>
              {latest.final_markdown || "(no final_markdown)"}
            </pre>

            <details style={{ marginTop: 12 }}>
              <summary>Raw latest JSON</summary>
              <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(latest)}</pre>
            </details>
          </>
        )}
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* WS events */}
      <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
        <h3>WebSocket events (latest first)</h3>
        {!threadId && <div>Create a session first.</div>}
        {threadId && events.length === 0 && <div>No events yet.</div>}

        {events.map((e: any, idx: number) => (
          <div
            key={idx}
            style={{
              padding: 10,
              borderRadius: 8,
              border: "1px solid #444",
              marginBottom: 8,
            }}
          >
            <div style={{ opacity: 0.8, fontSize: 13 }}>
              <b>{e.type}</b> {e.ts ? `— ${e.ts}` : ""} {e.run_id ? `— run ${e.run_id}` : ""}
            </div>
            <details>
              <summary>Details</summary>
              <pre style={{ whiteSpace: "pre-wrap" }}>{prettyJson(e)}</pre>
            </details>
          </div>
        ))}
      </div>
    </div>
  );
}
