import type {
  ChatCollectResult,
  ChatConversationRunSseEvent,
  ChatRunUiStatus,
} from "@/types/workflow";

const STORAGE_KEY = "chat:conversation-run";

export type StoredChatRun = {
  runId: string;
  sessionId: string;
  message?: string;
  lastEventId: number;
  streamingContent: string;
  toolSteps: string[];
  collectResults: ChatCollectResult[];
  status: ChatRunUiStatus;
  error: string | null;
};

export type ChatConversationRunSubscription = {
  close: () => void;
};

export type ChatConversationRunCallbacks = {
  onToolStart?: (text: string, eventId: number, name?: string) => void;
  onToolEnd?: (text: string, eventId: number, name?: string) => void;
  onCollectResult?: (result: ChatCollectResult, eventId: number) => void;
  onChunk?: (text: string, eventId: number) => void;
  onDone?: (event: ChatConversationRunSseEvent & { event: "done" }) => void;
  onChatError?: (message: string, eventId: number) => void;
  onCanceled?: (message: string, eventId: number) => void;
  onRecovering?: () => void;
  onInterrupted?: (message: string) => void;
};

export function buildChatRunStreamUrl(runId: string, lastEventId: number) {
  return `/api/agent/conversation/runs/${runId}/stream?lastEventId=${lastEventId}`;
}

export function shouldApplyChatRunEvent(eventId: number, lastEventId: number) {
  return Number.isFinite(eventId) && eventId > lastEventId;
}

export function subscribeChatConversationRun(
  runId: string,
  lastEventId: number,
  callbacks: ChatConversationRunCallbacks,
  recoverTimeoutMs = 60_000,
): ChatConversationRunSubscription {
  let appliedLastEventId = lastEventId;
  let closed = false;
  let interruptedTimer: ReturnType<typeof window.setTimeout> | null = null;
  const source = new EventSource(buildChatRunStreamUrl(runId, lastEventId));

  function clearInterruptedTimer() {
    if (interruptedTimer !== null) {
      window.clearTimeout(interruptedTimer);
      interruptedTimer = null;
    }
  }

  function applyEvent(eventName: ChatConversationRunSseEvent["event"], event: MessageEvent) {
    const eventId = Number(event.lastEventId);
    const hasBusinessEventId = event.lastEventId !== "" && shouldApplyChatRunEvent(eventId, appliedLastEventId);
    if (event.lastEventId !== "" && !hasBusinessEventId) return;
    if (hasBusinessEventId) appliedLastEventId = eventId;
    clearInterruptedTimer();
    const data = JSON.parse(event.data);
    const callbackEventId = hasBusinessEventId ? eventId : appliedLastEventId;
    if (eventName === "tool_start") callbacks.onToolStart?.(data.text || "", callbackEventId, data.name);
    if (eventName === "tool_end") callbacks.onToolEnd?.(data.text || "", callbackEventId, data.name);
    if (eventName === "collect_result") callbacks.onCollectResult?.(data as ChatCollectResult, callbackEventId);
    if (eventName === "chunk") callbacks.onChunk?.(data.text || "", callbackEventId);
    if (eventName === "done") callbacks.onDone?.({ id: callbackEventId, event: "done", data });
    if (eventName === "chat_error") callbacks.onChatError?.(data.message || "对话运行失败", callbackEventId);
    if (eventName === "canceled") callbacks.onCanceled?.(data.message || "对话已取消", callbackEventId);
  }

  source.addEventListener("tool_start", (event) => applyEvent("tool_start", event as MessageEvent));
  source.addEventListener("tool_end", (event) => applyEvent("tool_end", event as MessageEvent));
  source.addEventListener("collect_result", (event) => applyEvent("collect_result", event as MessageEvent));
  source.addEventListener("chunk", (event) => applyEvent("chunk", event as MessageEvent));
  source.addEventListener("done", (event) => applyEvent("done", event as MessageEvent));
  source.addEventListener("chat_error", (event) => applyEvent("chat_error", event as MessageEvent));
  source.addEventListener("canceled", (event) => applyEvent("canceled", event as MessageEvent));
  source.onerror = () => {
    callbacks.onRecovering?.();
    if (interruptedTimer === null) {
      interruptedTimer = window.setTimeout(() => {
        if (!closed) callbacks.onInterrupted?.("对话连接恢复超时，请重新发送或稍后再试");
      }, recoverTimeoutMs);
    }
  };

  return {
    close: () => {
      closed = true;
      clearInterruptedTimer();
      source.close();
    },
  };
}

export function saveStoredChatRun(value: StoredChatRun) {
  globalThis.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function readStoredChatRun(): StoredChatRun | null {
  const raw = globalThis.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredChatRun;
  } catch {
    globalThis.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearStoredChatRun() {
  globalThis.sessionStorage.removeItem(STORAGE_KEY);
}
