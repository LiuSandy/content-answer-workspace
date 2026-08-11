import { describe, expect, test } from "bun:test";

import {
  abortStreamForChat,
  reconcileTransientStreamError,
  type ActiveChatStream,
} from "./chat-stream-lifecycle";

describe("chat stream lifecycle", () => {
  test("does not abort a newly-created chat stream when the previous empty route cleans up", () => {
    const controller = new AbortController();
    const active: ActiveChatStream = { chatId: "new-chat", controller };

    const remaining = abortStreamForChat(active, null);

    expect(controller.signal.aborted).toBe(false);
    expect(remaining).toBe(active);
  });

  test("aborts the stream owned by the chat being left", () => {
    const controller = new AbortController();
    const active: ActiveChatStream = { chatId: "old-chat", controller };

    const remaining = abortStreamForChat(active, "old-chat");

    expect(controller.signal.aborted).toBe(true);
    expect(remaining).toBeNull();
  });

  test("clears a transient SSE error after the same error is persisted", () => {
    const result = reconcileTransientStreamError(
      "本轮处理步骤过多已自动停止",
      [
        {
          messageType: "error",
          content: null,
          payload: { message: "本轮处理步骤过多已自动停止" },
        },
      ],
    );

    expect(result).toBeNull();
  });

  test("keeps a transient transport error when no persisted error matches", () => {
    const result = reconcileTransientStreamError("网络连接中断", [
      { messageType: "text", content: "旧消息", payload: null },
    ]);

    expect(result).toBe("网络连接中断");
  });
});
