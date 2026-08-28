import { useState, useRef, useCallback, useEffect } from "react";

export interface UseStreamingBufferOptions {
  /**
   * 批次刷新节流时间（毫秒），默认为 30ms（约 30~33 FPS）。
   * 控制文本刷新的最高频率，避免每来一个 Token 就刷新一次导致的性能瓶颈。
   */
  throttleMs?: number;
}

/**
 * 流式文本时间切片缓冲 Hook (useStreamingBuffer)
 *
 * 【设计背景与解决的核心问题】：
 * 1. 削峰填谷：LLM 推流每秒可产生 30~60 个 SSE 数据块（Token）。若每次都直接 setState，
 *    会导致 Markdown/AST 解析器每秒执行数十次全量重解析，引发 CPU 暴涨与发热卡顿。
 * 2. 帧率平滑：将高频且到达间隔不均的 Token 先暂存在纯内存缓冲区，通过 requestAnimationFrame (RAF)
 *    对齐到浏览器重绘周期，以平滑均匀的批次（约 30 FPS）提交给 React 渲染。
 * 3. 终态零丢字：在流式传输结束（SSE 完成）时提供同步 flush 机制，确保缓冲区中剩余的最后字符
 *    百分之百落地上屏，杜绝截断问题。
 */
export function useStreamingBuffer(options: UseStreamingBufferOptions = {}) {
  // 节流间隔，默认 30ms（约 33 帧/秒，既保证肉眼极度丝滑，又大幅减少不必要的重复计算）
  const { throttleMs = 30 } = options;

  // 暴露给 React 渲染层使用的已提交文本状态
  const [streamingText, setStreamingText] = useState("");

  // -------------------------------------------------------------
  // Ref 状态（仅保存在内存中，读写不触发组件重渲染，解决闭包过期与高频开销）
  // -------------------------------------------------------------

  /** 尚未提交到 React state 的待刷文本缓冲区（Token 暂存队列） */
  const pendingBufferRef = useRef("");

  /** 当前已提交到 React state 的全量文本快照（方便同步追加，无需依赖异步的 state 回调） */
  const currentTextRef = useRef("");

  /** requestAnimationFrame 的任务 ID，用于在重绘前取消或防重复调度 */
  const rafIdRef = useRef<number | null>(null);

  /** setTimeout 的定时器 ID，用于在节流窗口未满时等待剩余时间，以及作为非活跃标签页的兜底 */
  const timerIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** 上一次向 React 提交（commitFlush）的时间戳（使用 performance.now() 高精度时间） */
  const lastFlushTimeRef = useRef<number>(0);

  /**
   * 清除所有正在等待执行的动画帧与定时器。
   * 用于在执行紧急刷新（flush）、重置（reset）或组件卸载时清理调度现场。
   */
  const clearPendingScheduled = useCallback(() => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
    if (timerIdRef.current !== null) {
      clearTimeout(timerIdRef.current);
      timerIdRef.current = null;
    }
  }, []);

  /**
   * 提交刷新（Commit）：
   * 将内存缓冲区（pendingBufferRef）中的所有文本一次性合并入已提交文本，
   * 并触发唯一一次 React 状态更新（setStreamingText）。
   */
  const commitFlush = useCallback(() => {
    // 先取消待处理的任务，防止同一帧内产生重复刷新
    clearPendingScheduled();

    if (pendingBufferRef.current) {
      // 1. 将暂存队列中的所有分块合并到当前文本快照中
      currentTextRef.current += pendingBufferRef.current;
      // 2. 清空暂存队列
      pendingBufferRef.current = "";
      // 3. 提交给 React 状态，触发这一帧的 DOM/Markdown 重绘
      setStreamingText(currentTextRef.current);
      // 4. 记录本次提交的高精度时间戳
      lastFlushTimeRef.current = performance.now();
    }
  }, [clearPendingScheduled]);

  /**
   * 智能调度策略（双定时器机制：RAF + setTimeout 兜底）：
   * 1. 若当前已有调度任务在队列中，直接复用，不重复创建；
   * 2. 若距上次提交已超过 throttleMs，立即向下一帧注册 requestAnimationFrame；
   * 3. 若未达到节流间隔，先用 setTimeout 补齐剩余等待时间，再对齐到下一帧 RAF；
   *    这种机制同时解决了“浏览器标签页切到后台时 RAF 被系统挂起导致文字不刷新”的边缘问题。
   */
  const scheduleFlush = useCallback(() => {
    // 互斥守卫：如果已经有一个 flush 任务在排队，直接退出，等待那一帧执行即可
    if (rafIdRef.current !== null || timerIdRef.current !== null) {
      return;
    }

    const now = performance.now();
    const elapsed = now - lastFlushTimeRef.current;

    // 执行任务：清空 ID 并提交文本
    const performFlush = () => {
      rafIdRef.current = null;
      timerIdRef.current = null;
      commitFlush();
    };

    if (elapsed >= throttleMs) {
      // 已经满足节流时间间隔，对齐到浏览器的下一次屏幕垂直同步信号（vsync）进行渲染
      rafIdRef.current = requestAnimationFrame(performFlush);
    } else {
      // 尚未达到节流时间，先等待剩余的时差，再排队到 RAF 保证平滑过渡
      const remainingTime = throttleMs - elapsed;
      timerIdRef.current = setTimeout(() => {
        timerIdRef.current = null;
        rafIdRef.current = requestAnimationFrame(performFlush);
      }, remainingTime);
    }
  }, [throttleMs, commitFlush]);

  /**
   * 【核心对外方法】追加文本分块（Token Chunk）：
   * 当 SSE 收到 `message.delta` 时调用。
   * 此方法仅向内存中快速追加字符串，完全不触发 React 重渲染，耗时 < 0.01ms。
   */
  const appendChunk = useCallback(
    (chunk: string) => {
      if (!chunk) return;
      pendingBufferRef.current += chunk;
      scheduleFlush();
    },
    [scheduleFlush],
  );

  /**
   * 【核心对外方法】强制立即同步（Flush）：
   * 在 SSE 流结束（run.completed）或报错时调用。
   * 强制将缓冲区内残留的所有字符瞬间刷入 React 状态，防止最后几个字在定时器中丢失。
   */
  const flush = useCallback(() => {
    commitFlush();
  }, [commitFlush]);

  /**
   * 【核心对外方法】重置状态（Reset）：
   * 清除所有定时器，并将缓冲区与状态彻底归零，供开启新的一轮对话前调用。
   */
  const reset = useCallback(() => {
    clearPendingScheduled();
    pendingBufferRef.current = "";
    currentTextRef.current = "";
    lastFlushTimeRef.current = 0;
    setStreamingText("");
  }, [clearPendingScheduled]);

  /**
   * 生命周期保护：
   * 当组件被卸载（如用户在生成中途关闭页面或切换路由）时，
   * 及时取消正在排队的 requestAnimationFrame 和 setTimeout，防止内存泄漏和报 React 卸载组件更新错误。
   */
  useEffect(() => {
    return () => {
      clearPendingScheduled();
    };
  }, [clearPendingScheduled]);

  return {
    /** 当前已生效并用于渲染的流式文本内容 */
    streamingText,
    /** 追加 SSE 文本分块到缓冲队列 */
    appendChunk,
    /** 立即提交缓冲区所有剩余字符（流结束时调用） */
    flush,
    /** 清空所有缓冲区与文本状态 */
    reset,
    /** 直接设置文本（供特殊场景或手动干预使用） */
    setStreamingText,
  };
}

