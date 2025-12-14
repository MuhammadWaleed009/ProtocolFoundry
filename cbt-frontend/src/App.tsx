import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { useCbtSession } from "./hooks/useCbtSession";

function prettyJson(x: any) {
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
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

function chip(text: string, tone: "neutral" | "good" | "warn" | "bad" = "neutral") {
  const className =
    tone === "good" ? "chip good" : tone === "warn" ? "chip warn" : tone === "bad" ? "chip bad" : "chip neutral";
  return <span className={className}>{text}</span>;
}

function labelValue(label: string, value: any) {
  return (
    <div className="stack small">
      <span className="subdued">{label}</span>
      <strong>{value ?? "–"}</strong>
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
    blackboard,
    startNewSession,
    clearSession,
    run,
    doApprove,
    doReject,
    refresh,
  } = useCbtSession() as any;

  const thinkingSafe: ThinkingSafe = thinking ?? { status: "idle", history: [] };

  const [inputText, setInputText] = useState("Draft a 5-minute grounding exercise for anxiety.");
  const [requireApproval, setRequireApproval] = useState(true);
  const [editedText, setEditedText] = useState("");
  const [feedback, setFeedback] = useState("Tighten it to 3 minutes and make the reflection shorter.");
  const [showSessionWarning, setShowSessionWarning] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState(false);
  const runDisabled = busy || !inputText.trim();

  useEffect(() => {
    if (threadId) setShowSessionWarning(false);
  }, [threadId]);

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

  const bbDraftMd =
    blackboard?.final?.markdown ||
    (Array.isArray(blackboard?.drafts) && blackboard.drafts.length
      ? blackboard.drafts[blackboard.drafts.length - 1]?.markdown
      : "");
  const draftPreviewMd = typeof bbDraftMd === "string" && bbDraftMd.trim() ? bbDraftMd : draftMarkdown;

  const bbTrace = Array.isArray(blackboard?.trace) ? blackboard.trace : [];
  const bbScratch = blackboard?.scratchpad ?? null;
  const bbReviews = blackboard?.reviews ?? null;
  const bbSupervisor = blackboard?.supervisor ?? null;
  const bbMetrics = blackboard?.metrics ?? null;
  const bbDrafts = Array.isArray(blackboard?.drafts) ? blackboard.drafts : [];
  const bbFinal = blackboard?.final ?? null;
  const safetyPass = bbReviews?.safety?.safety_pass;
  const qualityPass = bbReviews?.critic?.quality_pass;
  const finalPreviewMd =
    (bbFinal && typeof bbFinal.markdown === "string" && bbFinal.markdown.trim() ? bbFinal.markdown : null) ??
    (typeof latest?.final_markdown === "string" && latest.final_markdown.trim() ? latest.final_markdown : "") ??
    "";
  const showFinalPreview =
    !pending &&
    (blackboard?.status === "COMPLETED" || latest?.status === "COMPLETED");

  const handleDownloadPdf = () => {
    if (!showFinalPreview || !finalPreviewMd) return;
    const userQuery = (blackboard as any)?.request?.text || latest?.input_text || inputText;
    const win = window.open("", "_blank", "width=900,height=700");
    if (!win) return;
    const html = `
      <html>
      <head>
        <title>CBT Protocol</title>
        <style>
          body { font-family: "Space Grotesk", "Segoe UI", system-ui, -apple-system, sans-serif; padding: 24px; color: #0f172a; }
          h1 { margin: 0 0 4px; }
          h2 { margin-top: 18px; }
          .sub { color: #475569; font-size: 14px; }
          pre { white-space: pre-wrap; background: #0f172a; color: #e2e8f0; padding: 16px; border-radius: 12px; }
          .meta { margin: 12px 0; }
          .meta div { margin-bottom: 6px; }
        </style>
      </head>
      <body>
        <h1>CBT Protocol</h1>
        <div class="sub">Exported from Cerina Protocol Foundry</div>
        <div class="meta">
          <div><strong>User query:</strong> ${userQuery || "—"}</div>
          <div><strong>Status:</strong> ${latest?.status || blackboard?.status || "COMPLETED"}</div>
        </div>
        <h2>Protocol</h2>
        <pre>${finalPreviewMd}</pre>
      </body>
      </html>
    `;
    win.document.open();
    win.document.write(html);
    win.document.close();
    win.focus();
    win.print();
  };

  const stageChips =
    thinkingSafe.stages &&
    Object.entries(thinkingSafe.stages).map(([name, info]: any) => {
      const status = info?.status;
      const signals = info?.signals || {};
      const label =
        name === "human_review"
          ? "Approval"
          : name === "supervisor"
          ? "Supervisor"
          : name.charAt(0).toUpperCase() + name.slice(1);

      let tone: "neutral" | "good" | "warn" | "bad" = "neutral";
      if (status === "done") tone = "good";
      if (status === "error") tone = "bad";
      if (status === "active") tone = "warn";
      const detail =
        signals?.draft_version || signals?.iteration
          ? `v${signals.draft_version ?? signals.iteration}`
          : signals?.action
          ? signals.action
          : status;
      return (
        <span key={name} className="chip neutral">
          {label}
          {detail ? <span className="subdued" style={{ marginLeft: 6 }}>{detail}</span> : null}
        </span>
      );
    });

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">Cerina Protocol Foundry</p>
          <h1>CBT Protocol Console</h1>
          <p className="sub">See the agents collaborate, pause for human review, and ship the final protocol with confidence.</p>
        </div>
        <div className="hero-actions">
          <button className="btn" onClick={startNewSession} disabled={busy}>
            Create session
          </button>
          <button className="btn secondary" onClick={clearSession} disabled={!threadId || busy}>
            Clear session
          </button>
          <button className="btn ghost" onClick={() => refresh()} disabled={!threadId || busy}>
            Refresh
          </button>
        </div>
      </header>

      <div className="status-bar">
        <span className="pill">
          <strong>Thread</strong> {threadId || "—"}
        </span>
        <span className="pill">
          <strong>WS</strong> {wsStatus} · {wsHint}
        </span>
        <span className="pill">
          <strong>Status</strong> {statusLabel}
        </span>
        {typeof safetyPass === "boolean" && chip(`Safety ${safetyPass ? "pass" : "warn"}`, safetyPass ? "good" : "warn")}
        {typeof qualityPass === "boolean" &&
          chip(`Quality ${qualityPass ? "pass" : "warn"}`, qualityPass ? "good" : "warn")}
        {blackboard?.current_node && <span className="pill">Node: {blackboard.current_node}</span>}
      </div>

      {error && <div className="panel" style={{ borderColor: "#fca5a5", background: "#fef2f2" }}><strong>Error:</strong> {error}</div>}

      <div className="grid two">
        <div className="panel">
          <div className="section-title">
            <h3>Run a request</h3>
            {busy && <span className="chip warn">Running…</span>}
          </div>
          <p className="lead">Describe the protocol you need. Choose if a human must approve before finalizing.</p>
          <div className="field">
            <label>Input</label>
            <textarea value={inputText} onChange={(e) => setInputText(e.target.value)} rows={5} />
          </div>
          <div className="pill-row" style={{ marginBottom: 10 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={requireApproval} onChange={(e) => setRequireApproval(e.target.checked)} />
              Require human approval
            </label>
            <span className="subdued">WS streams live; REST is the fallback.</span>
          </div>
          <div className="pill-row" style={{ alignItems: "center" }}>
            <button
              className="btn"
              onClick={() => {
                if (!threadId) setShowSessionWarning(true);
                run(inputText, requireApproval);
              }}
              disabled={runDisabled}
            >
              Launch run
            </button>
            {showSessionWarning && <span className="chip bad">Create a session first.</span>}
          </div>
        </div>

        <div className="panel">
          <div className="section-title">
            <h3>Live pipeline</h3>
            <span className="subdued">{thinkingSafe.updatedAt ? `Updated ${thinkingSafe.updatedAt}` : ""}</span>
          </div>
          <div className="pill-row" style={{ marginBottom: 10 }}>
            <span className="chip neutral">{thinkingSafe.step || thinkingSafe.status}</span>
            {stageChips}
          </div>
          {thinkingSafe.detail && <div className="subdued" style={{ marginBottom: 10 }}>{thinkingSafe.detail}</div>}
          <div className="divider" />
          <p className="subdued" style={{ margin: "0 0 6px" }}>Recent actions</p>
          <ul className="timeline">
            {(thinkingSafe.history ?? []).slice(0, 6).map((h, i) => (
              <li key={i}>
                <div className="subdued">{h.ts || ""}</div>
                <div>{h.label}</div>
              </li>
            ))}
            {(thinkingSafe.history ?? []).length === 0 && <li className="subdued">No activity yet.</li>}
          </ul>
        </div>
      </div>

      <div className="grid two" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="section-title">
            <h3>Pending approval</h3>
          </div>
          {!threadId && <div className="subdued">Create a session first.</div>}
          {threadId && !pending && <div className="subdued">No pending approval.</div>}
          {pending && (
            <div className="stack">
              <div className="pill-row">
                <span className="pill">run_id: {pending.run_id}</span>
                <span className="pill">status: {pending.status}</span>
              </div>
              <p className="subdued">Draft preview</p>
              <div className="preview">{draftPreviewMd || "(no draft markdown found)"}</div>
              <p className="subdued">Approve with optional edit</p>
              <textarea value={editedText} onChange={(e) => setEditedText(e.target.value)} placeholder="(Optional) Paste edited markdown here" rows={3} />
              <div className="pill-row">
                <button className="btn" onClick={() => doApprove(editedText || undefined)} disabled={busy}>Approve</button>
              </div>
              <p className="subdued">Reject with feedback</p>
              <textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Feedback for revision" rows={3} />
              <div className="pill-row">
                <button className="btn secondary" onClick={() => doReject(feedback)} disabled={busy}>Reject</button>
              </div>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="section-title">
            <h3>Draft / Final preview</h3>
            <div className="pill-row" style={{ alignItems: "center", gap: 8 }}>
              {bbDrafts.length > 0 && <span className="chip neutral">Drafts {bbDrafts.length}</span>}
              {showFinalPreview && finalPreviewMd && (
                <button className="btn ghost" onClick={handleDownloadPdf} style={{ padding: "6px 10px" }}>
                  Download PDF
                </button>
              )}
            </div>
          </div>
          {showFinalPreview && finalPreviewMd ? (
            <div className="preview tall">{finalPreviewMd}</div>
          ) : (
            <div className="subdued">Approve or reject the pending draft first.</div>
          )}
        </div>

        <div className="panel">
          <div className="section-title">
            <h3>Notes</h3>
          </div>
          <p className="subdued">Scratchpad</p>
          {bbScratch ? (
            <div className="list-grid">
              {Object.entries(bbScratch).map(([k, v]: any) => (
                <div key={k} className="item-card">
                  <div className="subdued" style={{ textTransform: "capitalize", marginBottom: 4 }}>{k}</div>
                  {Array.isArray(v) && v.length > 0 ? v.slice(-4).map((s: any, idx: number) => (
                    <div key={idx} style={{ fontSize: 13 }}>{String(s)}</div>
                  )) : <div className="subdued">—</div>}
                </div>
              ))}
            </div>
          ) : (
            <div className="subdued">No scratchpad yet.</div>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="section-title">
          <h3>WebSocket events</h3>
          <button className="btn ghost" onClick={() => setExpandedEvents((v) => !v)}>
            {expandedEvents ? "Show less" : "Show more"}
          </button>
        </div>
        {!threadId && <div className="subdued">Create a session first.</div>}
        {threadId && events.length === 0 && <div className="subdued">No events yet.</div>}
        <div className="stack">
          {(expandedEvents ? events : events.slice(0, 2)).map((e: any, idx: number) => (
            <div key={idx} className="item-card" style={{ background: "#fff" }}>
              <div className="subdued">{e.ts ? `${e.ts}` : ""}</div>
              <div><strong>{e.type}</strong> {e.run_id ? `· run ${e.run_id}` : ""}</div>
              <details>
                <summary className="subdued">Details</summary>
                <pre className="preview" style={{ background: "#0b1120" }}>{prettyJson(e)}</pre>
              </details>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
