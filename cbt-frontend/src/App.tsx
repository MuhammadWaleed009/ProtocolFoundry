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
    startNewSession,
    clearSession,
    run,
    doApprove,
    doReject,
    refresh,
  } = useCbtSession();

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

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 16, textAlign: "left" }}>
      <h2>CBT Protocol UI</h2>

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

        <div style={{ opacity: 0.8 }}>
          <div>
            <b>thread_id:</b> {threadId || "-"}
          </div>
          <div>
            <b>WS:</b> {wsStatus} &nbsp; | &nbsp; <b>Status:</b> {statusLabel}
          </div>
        </div>
      </div>

      {/* ✅ NEW: Thinking panel */}
      <div style={{ marginTop: 12, padding: 12, border: "1px solid #333", borderRadius: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <b>Thinking:</b>
          <span>
            {thinkingDot(thinking.status)} {thinking.step || thinking.status}
          </span>
          {thinking.runId && <span style={{ opacity: 0.7 }}>run: {thinking.runId}</span>}
          {thinking.updatedAt && <span style={{ opacity: 0.7 }}>@ {thinking.updatedAt}</span>}
        </div>

        {thinking.detail && (
          <div style={{ marginTop: 8, opacity: 0.9, fontSize: 13 }}>{thinking.detail}</div>
        )}

        <details style={{ marginTop: 10 }}>
          <summary>Live trace</summary>
          <ul style={{ marginTop: 8, paddingLeft: 18 }}>
            {thinking.history.map((h, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <span style={{ opacity: 0.7 }}>{h.ts ? `${h.ts} — ` : ""}</span>
                {h.label}
              </li>
            ))}
          </ul>
        </details>
      </div>

      {error && (
        <div style={{ marginTop: 12, padding: 10, border: "1px solid #f00", borderRadius: 8 }}>
          <b>Error:</b> {error}
        </div>
      )}

      <hr style={{ margin: "16px 0" }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Left: Run controls */}
        <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
          <h3>Run</h3>

          <label style={{ display: "block", marginBottom: 6 }}>Input</label>
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            rows={5}
            style={{ width: "100%", padding: 10, borderRadius: 8 }}
          />

          <div style={{ marginTop: 10, display: "flex", gap: 12, alignItems: "center" }}>
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

            {/* ✅ simple running indicator */}
            {busy && <span style={{ opacity: 0.75 }}>Running…</span>}
          </div>

          <div style={{ marginTop: 12, opacity: 0.8, fontSize: 13 }}>
            Tip: If WS disconnects, the UI still works because it fetches pending/latest from REST.
          </div>
        </div>

        {/* Right: Pending approval */}
        <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
          <h3>Pending approval</h3>

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
                {draftMarkdown || "(no draft markdown found)"}
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
        </div>
      </div>

      <hr style={{ margin: "16px 0" }} />

      {/* Latest */}
      <div style={{ padding: 12, border: "1px solid #333", borderRadius: 10 }}>
        <h3>Latest run</h3>
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

        {events.map((e, idx) => (
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
