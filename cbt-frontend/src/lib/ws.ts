// cbt-frontend/src/lib/ws.ts

// If you set VITE_WS_BASE_URL, it should be like:
//   ws://127.0.0.1:8000
// NOT:
//   ws://127.0.0.1:8000/ws
const RAW_WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://127.0.0.1:8000";

function normalizeWsBase(base: string) {
  // remove trailing slashes
  let b = base.replace(/\/+$/, "");
  // if someone set ".../ws", strip it to avoid "/ws/ws/..."
  b = b.replace(/\/ws$/, "");
  return b;
}

const WS_BASE = normalizeWsBase(RAW_WS_BASE);

export type WsMessage = {
  type: string;
  ts?: string;
  seq?: number;
  run_id?: string;
  [k: string]: any;
};

export function connectWs(
  threadId: string,
  onMessage: (msg: WsMessage) => void,
  onStatus?: (s: "open" | "closed" | "error") => void
) {
  const url = `${WS_BASE}/ws/${threadId}`;
  const ws = new WebSocket(url);

  ws.onopen = () => onStatus?.("open");
  ws.onclose = () => onStatus?.("closed");
  ws.onerror = () => onStatus?.("error");

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data) as WsMessage;
      onMessage(msg);
    } catch {
      // ignore non-json
    }
  };

  return {
    close: () => {
      try {
        ws.close();
      } catch {}
    },
    ping: () => {
      try {
        ws.send("ping");
      } catch {}
    },
  };
}
