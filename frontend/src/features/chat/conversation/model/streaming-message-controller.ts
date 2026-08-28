import {
  createStreamingTextBuffer,
  type StreamingTextBuffer,
} from "./streaming-text-buffer";

export interface StreamingMessageSnapshot {
  visible: boolean;
  agentStatus: string | null;
  streamingText: string;
  streamingSourceList: unknown | null;
  streamingError: string | null;
}

export interface StreamingMessageController {
  start(status?: string | null): void;
  appendChunk(chunk: string): void;
  setStatus(status: string | null): void;
  setSourceList(data: unknown | null): void;
  setError(error: string | null): void;
  flush(): void;
  settle(error?: string | null): void;
  reset(): void;
  destroy(): void;
  getSnapshot(): StreamingMessageSnapshot;
  subscribe(listener: () => void): () => void;
}

const EMPTY_SNAPSHOT: StreamingMessageSnapshot = {
  visible: false,
  agentStatus: null,
  streamingText: "",
  streamingSourceList: null,
  streamingError: null,
};

/**
 * 管理一轮 SSE 助手消息的临时快照和展示生命周期。
 * SSE 负责写入，StreamingMessageCard 通过 useSyncExternalStore 独占订阅，
 * 从而避免高频文本更新触发 ChatPanel 和历史消息列表重新渲染。
 */
export function createStreamingMessageController(
  textBuffer: StreamingTextBuffer = createStreamingTextBuffer({ throttleMs: 30 }),
): StreamingMessageController {
  let snapshot = EMPTY_SNAPSHOT;
  const listeners = new Set<() => void>();

  const emit = () => listeners.forEach((listener) => listener());

  // 相同快照不发通知，避免无意义的外部 Store 更新。
  const update = (patch: Partial<StreamingMessageSnapshot>) => {
    const next = { ...snapshot, ...patch };
    if (
      next.visible === snapshot.visible &&
      next.agentStatus === snapshot.agentStatus &&
      next.streamingText === snapshot.streamingText &&
      next.streamingSourceList === snapshot.streamingSourceList &&
      next.streamingError === snapshot.streamingError
    ) {
      return;
    }
    snapshot = next;
    emit();
  };

  // 只在缓冲器批量提交时更新文本，而不是响应每个原始 SSE chunk。
  const unsubscribeBuffer = textBuffer.subscribe(() => {
    update({ streamingText: textBuffer.getSnapshot() });
  });

  return {
    start(status = null) {
      textBuffer.reset();
      snapshot = {
        visible: true,
        agentStatus: status,
        streamingText: "",
        streamingSourceList: null,
        streamingError: null,
      };
      emit();
    },
    appendChunk: textBuffer.appendChunk,
    setStatus(agentStatus) {
      update({ visible: true, agentStatus });
    },
    setSourceList(streamingSourceList) {
      update({ visible: true, streamingSourceList });
    },
    setError(streamingError) {
      // 出错前提交剩余文本，保留已经生成的部分内容。
      if (streamingError) textBuffer.flush();
      update({
        visible: Boolean(streamingError) || snapshot.visible,
        agentStatus: streamingError ? null : snapshot.agentStatus,
        streamingError,
      });
    },
    flush: textBuffer.flush,
    settle(streamingError = null) {
      textBuffer.reset();
      snapshot = {
        ...EMPTY_SNAPSHOT,
        visible: Boolean(streamingError),
        streamingError,
      };
      emit();
    },
    reset() {
      textBuffer.reset();
      snapshot = EMPTY_SNAPSHOT;
      emit();
    },
    destroy() {
      unsubscribeBuffer();
      textBuffer.destroy();
      listeners.clear();
    },
    getSnapshot() {
      return snapshot;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
