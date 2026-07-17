import { describe, test, expect } from "bun:test";

type Message = {
  messageId: string;
  role: "user" | "assistant" | "tool";
  messageType: "text" | "source_card" | "source_list" | "tool_status" | "error";
  content: string | null;
  parentMessageId?: string | null;
  payload: any;
  createdAt: string;
};

// Copy the implementation of resolveParentIds
function resolveParentIds(allMsgs: Message[]): Message[] {
  const sorted = [...allMsgs].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  const resolved = sorted.map(m => ({ ...m }));
  
  for (let i = 0; i < resolved.length; i++) {
    const msg = resolved[i];
    if (msg.parentMessageId === undefined || msg.parentMessageId === null) {
      if (i === 0) {
        msg.parentMessageId = null;
        continue;
      }
      
      const prevMsg = resolved[i - 1];
      
      if (msg.role === "assistant" || msg.role === "tool") {
        msg.parentMessageId = prevMsg.messageId;
      } else if (msg.role === "user") {
        const nextMsg = resolved[i + 1];
        if (nextMsg && (nextMsg.role === "assistant" || nextMsg.role === "tool")) {
          const nextMsgDbParent = allMsgs.find(m => m.messageId === nextMsg.messageId)?.parentMessageId;
          if (!nextMsgDbParent || nextMsgDbParent !== msg.messageId) {
            msg.parentMessageId = prevMsg.messageId;
          } else {
            msg.parentMessageId = null;
          }
        } else {
          msg.parentMessageId = prevMsg.messageId;
        }
      }
    }
  }
  return resolved;
}

// Copy getActivePathAndInit to test its path tracing logic
function getActivePathAndInit(allMsgs: Message[], activeLeafMessageId: string | null) {
  if (allMsgs.length === 0) return { path: [], leafId: null };

  const parentIdsSet = new Set(allMsgs.map(m => m.parentMessageId).filter(Boolean) as string[]);
  const leafMessages = allMsgs.filter(m => !parentIdsSet.has(m.messageId));
  
  leafMessages.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  const defaultLeafId = leafMessages[0]?.messageId || null;

  let currentLeafId = activeLeafMessageId;
  if (!currentLeafId || !allMsgs.some(m => m.messageId === currentLeafId)) {
    currentLeafId = defaultLeafId;
  }

  if (!currentLeafId) return { path: [], leafId: null };

  const msgMap = new Map(allMsgs.map(m => [m.messageId, m]));
  const path: Message[] = [];
  let currId: string | null = currentLeafId;
  const visited = new Set<string>();

  while (currId && msgMap.has(currId) && !visited.has(currId)) {
    visited.add(currId);
    const currentMsg: Message = msgMap.get(currId)!;
    path.push(currentMsg);
    
    if (currentMsg.parentMessageId) {
      currId = currentMsg.parentMessageId;
    } else {
      const sortedAll = [...allMsgs].sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
      const idx = sortedAll.findIndex(m => m.messageId === currentMsg.messageId);
      if (idx > 0) {
        currId = sortedAll[idx - 1].messageId;
      } else {
        currId = null;
      }
    }
  }

  path.reverse();
  return { path, leafId: currentLeafId };
}

describe("Chat Logic TDD Tests", () => {
  test("resolveParentIds chains legacy linear messages correctly", () => {
    // 7 legacy linear messages all having parentMessageId as null
    const legacyMessages: Message[] = [
      { messageId: "u1", role: "user", messageType: "text", content: "Q1", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:00:00Z" },
      { messageId: "a1", role: "assistant", messageType: "text", content: "A1", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:01:00Z" },
      { messageId: "u2", role: "user", messageType: "text", content: "Q2", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:02:00Z" },
      { messageId: "a2", role: "assistant", messageType: "text", content: "A2", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:03:00Z" },
    ];

    const resolved = resolveParentIds(legacyMessages);

    // u1 should have parent null
    expect(resolved.find(m => m.messageId === "u1")?.parentMessageId).toBeNull();
    // a1 should point to u1
    expect(resolved.find(m => m.messageId === "a1")?.parentMessageId).toBe("u1");
    // u2 should point to a1
    expect(resolved.find(m => m.messageId === "u2")?.parentMessageId).toBe("a1");
    // a2 should point to u2
    expect(resolved.find(m => m.messageId === "a2")?.parentMessageId).toBe("u2");
  });

  test("resolveParentIds keeps new root edits branch as null", () => {
    const messages: Message[] = [
      { messageId: "u1", role: "user", messageType: "text", content: "Q1", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:00:00Z" },
      { messageId: "a1", role: "assistant", messageType: "text", content: "A1", parentMessageId: "u1", payload: null, createdAt: "2026-07-14T10:01:00Z" },
      { messageId: "u1_branch", role: "user", messageType: "text", content: "Q1 Edited", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:02:00Z" },
      { messageId: "a1_branch", role: "assistant", messageType: "text", content: "A1 Edited", parentMessageId: "u1_branch", payload: null, createdAt: "2026-07-14T10:03:00Z" },
    ];

    const resolved = resolveParentIds(messages);

    expect(resolved.find(m => m.messageId === "u1")?.parentMessageId).toBeNull();
    expect(resolved.find(m => m.messageId === "u1_branch")?.parentMessageId).toBeNull();
    expect(resolved.find(m => m.messageId === "a1_branch")?.parentMessageId).toBe("u1_branch");
  });

  test("getActivePathAndInit includes newly added optimistic user message during stream when activeLeafMessageId is correctly updated", () => {
    const historicalMessages: Message[] = [
      { messageId: "u1", role: "user", messageType: "text", content: "Q1", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:00:00Z" },
      { messageId: "a1", role: "assistant", messageType: "text", content: "A1", parentMessageId: "u1", payload: null, createdAt: "2026-07-14T10:01:00Z" },
    ];

    const activeLeafIdBeforeSend = "a1";

    // Simulate sending new message: we add temp-user-msg and set activeLeafMessageId to temp-user-msg
    const messagesWithOptimistic: Message[] = [
      ...historicalMessages,
      { messageId: "temp-user-msg", role: "user", messageType: "text", content: "Q2", parentMessageId: "a1", payload: null, createdAt: "2026-07-14T10:02:00Z" }
    ];

    // If activeLeafMessageId is updated immediately to temp-user-msg
    const { path, leafId } = getActivePathAndInit(messagesWithOptimistic, "temp-user-msg");

    expect(leafId).toBe("temp-user-msg");
    expect(path.map(m => m.messageId)).toEqual(["u1", "a1", "temp-user-msg"]);
  });

  test("getActivePathAndInit locks to old leaf if activeLeafMessageId is NOT updated when sending (THE BUG SCENARIO)", () => {
    const historicalMessages: Message[] = [
      { messageId: "u1", role: "user", messageType: "text", content: "Q1", parentMessageId: null, payload: null, createdAt: "2026-07-14T10:00:00Z" },
      { messageId: "a1", role: "assistant", messageType: "text", content: "A1", parentMessageId: "u1", payload: null, createdAt: "2026-07-14T10:01:00Z" },
    ];

    const activeLeafIdBeforeSend = "a1";

    const messagesWithOptimistic: Message[] = [
      ...historicalMessages,
      { messageId: "temp-user-msg", role: "user", messageType: "text", content: "Q2", parentMessageId: "a1", payload: null, createdAt: "2026-07-14T10:02:00Z" }
    ];

    // If activeLeafMessageId is NOT updated (stays as a1)
    const { path, leafId } = getActivePathAndInit(messagesWithOptimistic, activeLeafIdBeforeSend);

    // It will remain locked to a1
    expect(leafId).toBe("a1");
    // And path will not include temp-user-msg!
    expect(path.map(m => m.messageId).includes("temp-user-msg")).toBe(false);
    expect(path.map(m => m.messageId)).toEqual(["u1", "a1"]);
  });
});
