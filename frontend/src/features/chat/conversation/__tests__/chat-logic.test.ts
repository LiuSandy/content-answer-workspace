import { describe, expect, test } from "bun:test";
import {
  getActiveMessagePath,
  resolveParentIds,
  type ChatMessage,
} from "../model/chat-message-tree";

const message = (
  messageId: string,
  role: ChatMessage["role"],
  content: string,
  parentMessageId: string | null,
  createdAt: string,
): ChatMessage => ({
  messageId,
  role,
  messageType: "text",
  content,
  parentMessageId,
  payload: null,
  createdAt,
});

describe("chat message tree", () => {
  test("chains legacy linear messages correctly", () => {
    const resolved = resolveParentIds([
      message("u1", "user", "Q1", null, "2026-07-14T10:00:00Z"),
      message("a1", "assistant", "A1", null, "2026-07-14T10:01:00Z"),
      message("u2", "user", "Q2", null, "2026-07-14T10:02:00Z"),
      message("a2", "assistant", "A2", null, "2026-07-14T10:03:00Z"),
    ]);

    expect(resolved.find((item) => item.messageId === "u1")?.parentMessageId).toBeNull();
    expect(resolved.find((item) => item.messageId === "a1")?.parentMessageId).toBe("u1");
    expect(resolved.find((item) => item.messageId === "u2")?.parentMessageId).toBe("a1");
    expect(resolved.find((item) => item.messageId === "a2")?.parentMessageId).toBe("u2");
  });

  test("keeps new root edits as separate branches", () => {
    const resolved = resolveParentIds([
      message("u1", "user", "Q1", null, "2026-07-14T10:00:00Z"),
      message("a1", "assistant", "A1", "u1", "2026-07-14T10:01:00Z"),
      message("u1-branch", "user", "Q1 edited", null, "2026-07-14T10:02:00Z"),
      message("a1-branch", "assistant", "A1 edited", "u1-branch", "2026-07-14T10:03:00Z"),
    ]);

    expect(resolved.find((item) => item.messageId === "u1")?.parentMessageId).toBeNull();
    expect(resolved.find((item) => item.messageId === "u1-branch")?.parentMessageId).toBeNull();
    expect(resolved.find((item) => item.messageId === "a1-branch")?.parentMessageId).toBe(
      "u1-branch",
    );
  });

  test("includes an optimistic message when it is the requested active leaf", () => {
    const messages = [
      message("u1", "user", "Q1", null, "2026-07-14T10:00:00Z"),
      message("a1", "assistant", "A1", "u1", "2026-07-14T10:01:00Z"),
      message("temp-user-msg", "user", "Q2", "a1", "2026-07-14T10:02:00Z"),
    ];

    const { path, leafId } = getActiveMessagePath(messages, "temp-user-msg");
    expect(leafId).toBe("temp-user-msg");
    expect(path.map((item) => item.messageId)).toEqual(["u1", "a1", "temp-user-msg"]);
  });

  test("keeps the requested historical leaf until the caller changes it", () => {
    const messages = [
      message("u1", "user", "Q1", null, "2026-07-14T10:00:00Z"),
      message("a1", "assistant", "A1", "u1", "2026-07-14T10:01:00Z"),
      message("temp-user-msg", "user", "Q2", "a1", "2026-07-14T10:02:00Z"),
    ];

    const { path, leafId } = getActiveMessagePath(messages, "a1");
    expect(leafId).toBe("a1");
    expect(path.map((item) => item.messageId)).toEqual(["u1", "a1"]);
  });
});
