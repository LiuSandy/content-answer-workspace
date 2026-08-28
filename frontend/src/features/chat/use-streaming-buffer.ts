export interface StreamingBufferOptions {
  /** React 文本快照的最小提交间隔，默认约 33 FPS。 */
  throttleMs?: number;
  /** 以下调度器仅用于测试注入；业务代码使用浏览器默认实现。 */
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (id: number) => void;
  setTimer?: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (id: ReturnType<typeof setTimeout>) => void;
  now?: () => number;
}

export interface StreamingTextBuffer {
  appendChunk(chunk: string): void;
  flush(): void;
  reset(): void;
  destroy(): void;
  getSnapshot(): string;
  subscribe(listener: () => void): () => void;
}

/**
 * 与 React 组件解耦的流式文本缓冲器。
 * SSE 回调只写入这个对象；只有订阅它的流式卡片会在批量提交后更新。
 */
export function createStreamingTextBuffer(
  options: StreamingBufferOptions = {},
): StreamingTextBuffer {
  const throttleMs = options.throttleMs ?? 30;
  const requestFrame = options.requestFrame ?? ((callback) => requestAnimationFrame(callback));
  const cancelFrame = options.cancelFrame ?? ((id) => cancelAnimationFrame(id));
  const setTimer = options.setTimer ?? ((callback, delay) => setTimeout(callback, delay));
  const clearTimer = options.clearTimer ?? ((id) => clearTimeout(id));
  const now = options.now ?? (() => performance.now());

  let pendingText = "";
  let committedText = "";
  let frameId: number | null = null;
  let timerId: ReturnType<typeof setTimeout> | null = null;
  let lastFlushTime = 0;
  const listeners = new Set<() => void>();

  const cancelScheduledFlush = () => {
    if (frameId !== null) {
      cancelFrame(frameId);
      frameId = null;
    }
    if (timerId !== null) {
      clearTimer(timerId);
      timerId = null;
    }
  };

  const emit = () => listeners.forEach((listener) => listener());

  const commit = () => {
    cancelScheduledFlush();
    if (!pendingText) return;

    committedText += pendingText;
    pendingText = "";
    lastFlushTime = now();
    emit();
  };

  const scheduleFlush = () => {
    if (frameId !== null || timerId !== null) return;

    const remaining = Math.max(0, throttleMs - (now() - lastFlushTime));
    if (remaining > 0) {
      // 直接由 timer 提交，确保后台标签页 RAF 被暂停时仍会刷新。
      timerId = setTimer(commit, remaining);
      return;
    }

    // 前台页面优先对齐下一次绘制；timer 是 RAF 被浏览器挂起时的兜底。
    frameId = requestFrame(commit);
    timerId = setTimer(commit, throttleMs);
  };

  return {
    appendChunk(chunk) {
      if (!chunk) return;
      pendingText += chunk;
      scheduleFlush();
    },
    flush: commit,
    reset() {
      cancelScheduledFlush();
      pendingText = "";
      lastFlushTime = 0;
      if (!committedText) return;
      committedText = "";
      emit();
    },
    destroy() {
      cancelScheduledFlush();
      pendingText = "";
      listeners.clear();
    },
    getSnapshot() {
      return committedText;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
