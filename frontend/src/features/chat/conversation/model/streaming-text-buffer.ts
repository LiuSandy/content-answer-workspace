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
 * 与 React 解耦的流式文本缓冲器。
 * 连续 chunk 先进入等待区，再按最小时间间隔批量提交；前台使用 RAF
 * 对齐绘制，timer 负责节流并作为后台标签页中 RAF 暂停时的兜底。
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

  // pendingText 是等待区，committedText 是订阅者可读取的稳定快照。
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

  // RAF 与 timer 共用 commit；先执行的一方会取消另一方，避免重复提交。
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
      // 距离上次提交不足 throttleMs，只等待剩余时间即可。
      timerId = setTimer(commit, remaining);
      return;
    }

    // 前台对齐下一次绘制；timer 在 RAF 被挂起时兜底。
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
