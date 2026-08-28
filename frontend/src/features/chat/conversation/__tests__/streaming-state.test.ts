import { describe, expect, test } from "bun:test";
import { createStreamingMessageController } from "../model/streaming-message-controller";
import { createStreamingTextBuffer } from "../model/streaming-text-buffer";

function createManualBuffer() {
  let currentTime = 100;
  let nextId = 1;
  const frames = new Map<number, FrameRequestCallback>();
  const timers = new Map<number, () => void>();

  const buffer = createStreamingTextBuffer({
    throttleMs: 30,
    now: () => currentTime,
    requestFrame: (callback) => {
      const id = nextId++;
      frames.set(id, callback);
      return id;
    },
    cancelFrame: (id) => frames.delete(id),
    setTimer: (callback) => {
      const id = nextId++;
      timers.set(id, callback);
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimer: (id) => timers.delete(id as unknown as number),
  });

  return {
    buffer,
    frames,
    timers,
    advance(ms: number) {
      currentTime += ms;
    },
    runFrame() {
      const entry = frames.entries().next().value as
        | [number, FrameRequestCallback]
        | undefined;
      if (!entry) return;
      frames.delete(entry[0]);
      entry[1](currentTime);
    },
  };
}

describe("streaming text buffer", () => {
  test("batches multiple chunks into one external-store notification", () => {
    const { buffer, frames, timers, runFrame } = createManualBuffer();
    let notifications = 0;
    buffer.subscribe(() => notifications++);

    buffer.appendChunk("你");
    buffer.appendChunk("好");
    buffer.appendChunk("！");

    expect(buffer.getSnapshot()).toBe("");
    expect(frames.size).toBe(1);
    expect(timers.size).toBe(1);

    runFrame();

    expect(buffer.getSnapshot()).toBe("你好！");
    expect(notifications).toBe(1);
    expect(frames.size).toBe(0);
    expect(timers.size).toBe(0);
  });

  test("flush commits synchronously and reset cancels pending work", () => {
    const { buffer, frames, timers } = createManualBuffer();

    buffer.appendChunk("final");
    buffer.flush();
    expect(buffer.getSnapshot()).toBe("final");

    buffer.appendChunk("discarded");
    buffer.reset();
    expect(buffer.getSnapshot()).toBe("");
    expect(frames.size).toBe(0);
    expect(timers.size).toBe(0);
  });
});

describe("streaming message controller", () => {
  test("retains events before the card subscribes", () => {
    const { buffer } = createManualBuffer();
    const controller = createStreamingMessageController(buffer);

    controller.start("发送中...");
    controller.appendChunk("first token");
    controller.flush();

    expect(controller.getSnapshot()).toEqual({
      visible: true,
      agentStatus: "发送中...",
      streamingText: "first token",
      streamingSourceList: null,
      streamingError: null,
    });
  });

  test("owns status, source, error and terminal cleanup without React parent state", () => {
    const { buffer } = createManualBuffer();
    const controller = createStreamingMessageController(buffer);
    let notifications = 0;
    controller.subscribe(() => notifications++);

    controller.start("生成中...");
    controller.setSourceList({ items: [1] });
    controller.appendChunk("partial");
    controller.setError("请求失败");

    expect(controller.getSnapshot()).toMatchObject({
      visible: true,
      agentStatus: null,
      streamingText: "partial",
      streamingSourceList: { items: [1] },
      streamingError: "请求失败",
    });
    expect(notifications).toBeGreaterThan(0);

    controller.settle(null);
    expect(controller.getSnapshot()).toEqual({
      visible: false,
      agentStatus: null,
      streamingText: "",
      streamingSourceList: null,
      streamingError: null,
    });
  });
});
