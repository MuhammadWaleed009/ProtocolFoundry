// cbt-frontend/src/lib/ws.ts
const WS_BASE = import.meta.env.VITE_WS_BASE_URL ?? "ws://127.0.0.1:8000";

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
  const ws = new WebSocket(`${WS_BASE}/ws/${threadId}`);

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
