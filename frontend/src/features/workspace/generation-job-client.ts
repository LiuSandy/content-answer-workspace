import type { GenerationJobSseEvent } from "@/types/workflow";

const STORAGE_KEY = "workbench:generation-job";

export type StoredGenerationJob = {
  jobId: string;
  itemId: string;
  lastEventId: number;
  streamingAnswer: string;
};

export type GenerationJobSubscription = {
  close: () => void;
};

export type GenerationJobCallbacks = {
  onChunk?: (text: string, eventId: number) => void;
  onDone?: (item: GenerationJobSseEvent & { event: "done" }) => void;
  onJobError?: (message: string, eventId: number) => void;
  onCanceled?: (message: string, eventId: number) => void;
  onRecovering?: () => void;
  onInterrupted?: (message: string) => void;
};

export function buildGenerationJobStreamUrl(jobId: string, lastEventId: number) {
  return `/api/workflow/generate-one/jobs/${jobId}/stream?lastEventId=${lastEventId}`;
}

export function subscribeGenerationJob(
  jobId: string,
  lastEventId: number,
  callbacks: GenerationJobCallbacks,
  recoverTimeoutMs = 60_000,
): GenerationJobSubscription {
  let appliedLastEventId = lastEventId;
  let closed = false;
  let interruptedTimer: number | null = null;
  const source = new EventSource(buildGenerationJobStreamUrl(jobId, lastEventId));

  function clearInterruptedTimer() {
    if (interruptedTimer !== null) {
      window.clearTimeout(interruptedTimer);
      interruptedTimer = null;
    }
  }

  function applyEvent(eventName: GenerationJobSseEvent["event"], event: MessageEvent) {
    const eventId = Number(event.lastEventId);
    if (!Number.isFinite(eventId) || eventId <= appliedLastEventId) return;
    appliedLastEventId = eventId;
    clearInterruptedTimer();
    const data = JSON.parse(event.data);
    if (eventName === "chunk") callbacks.onChunk?.(data.text || "", eventId);
    if (eventName === "done") callbacks.onDone?.({ id: eventId, event: "done", data });
    if (eventName === "job_error") callbacks.onJobError?.(data.message || "生成失败", eventId);
    if (eventName === "canceled") callbacks.onCanceled?.(data.message || "生成已取消", eventId);
  }

  source.addEventListener("chunk", (event) => applyEvent("chunk", event as MessageEvent));
  source.addEventListener("done", (event) => applyEvent("done", event as MessageEvent));
  source.addEventListener("job_error", (event) => applyEvent("job_error", event as MessageEvent));
  source.addEventListener("canceled", (event) => applyEvent("canceled", event as MessageEvent));
  source.onerror = () => {
    callbacks.onRecovering?.();
    if (interruptedTimer === null) {
      interruptedTimer = window.setTimeout(() => {
        if (!closed) callbacks.onInterrupted?.("生成连接恢复超时，请继续恢复或重新生成");
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

export function saveStoredGenerationJob(value: StoredGenerationJob) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function readStoredGenerationJob(): StoredGenerationJob | null {
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredGenerationJob;
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearStoredGenerationJob() {
  window.sessionStorage.removeItem(STORAGE_KEY);
}
