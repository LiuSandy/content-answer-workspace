export type ChatMessage = {
  messageId: string;
  role: "user" | "assistant" | "tool";
  messageType: "text" | "source_card" | "source_list" | "tool_status" | "error" | "choice_request";
  content: string | null;
  parentMessageId?: string | null;
  payload: any;
  createdAt: string;
};

export function getAssistantDurationSeconds(
  message: ChatMessage,
  messageById: Map<string, ChatMessage>,
): number | null {
  if (message.role !== "assistant" || !message.parentMessageId) return null;
  const userMessage = messageById.get(message.parentMessageId);
  if (!userMessage || userMessage.role !== "user") return null;

  const startedAt = new Date(userMessage.createdAt).getTime();
  const finishedAt = new Date(message.createdAt).getTime();
  if (!Number.isFinite(startedAt) || !Number.isFinite(finishedAt)) return null;
  return Math.max(0, (finishedAt - startedAt) / 1000);
}

/** 为旧的线性消息补充父节点，同时保留真正的根级编辑分支。 */
export function resolveParentIds(allMessages: ChatMessage[]): ChatMessage[] {
  const resolved = [...allMessages].sort(compareCreatedAt).map((message) => ({ ...message }));

  for (let index = 0; index < resolved.length; index += 1) {
    const message = resolved[index];
    if (message.parentMessageId !== undefined && message.parentMessageId !== null) {
      continue;
    }
    if (index === 0) {
      message.parentMessageId = null;
      continue;
    }

    const previous = resolved[index - 1];
    if (message.role === "assistant" || message.role === "tool") {
      message.parentMessageId = previous.messageId;
      continue;
    }

    const next = resolved[index + 1];
    if (next && (next.role === "assistant" || next.role === "tool")) {
      const databaseParent = allMessages.find(
        (item) => item.messageId === next.messageId,
      )?.parentMessageId;
      message.parentMessageId =
        !databaseParent || databaseParent !== message.messageId ? previous.messageId : null;
    } else {
      message.parentMessageId = previous.messageId;
    }
  }

  return resolved;
}

export function getActiveMessagePath(
  messages: ChatMessage[],
  requestedLeafId: string | null,
): { path: ChatMessage[]; leafId: string | null } {
  if (messages.length === 0) return { path: [], leafId: null };

  const parentIds = new Set(
    messages.map((message) => message.parentMessageId).filter(Boolean) as string[],
  );
  const defaultLeafId =
    messages
      .filter((message) => !parentIds.has(message.messageId))
      .sort((left, right) => compareCreatedAt(right, left))[0]?.messageId ?? null;
  const leafId =
    requestedLeafId && messages.some((message) => message.messageId === requestedLeafId)
      ? requestedLeafId
      : defaultLeafId;

  if (!leafId) return { path: [], leafId: null };

  const messageById = new Map(messages.map((message) => [message.messageId, message]));
  const chronological = [...messages].sort(compareCreatedAt);
  const path: ChatMessage[] = [];
  const visited = new Set<string>();
  let currentId: string | null = leafId;

  while (currentId && messageById.has(currentId) && !visited.has(currentId)) {
    visited.add(currentId);
    const current: ChatMessage = messageById.get(currentId)!;
    path.push(current);

    if (current.parentMessageId) {
      currentId = current.parentMessageId;
      continue;
    }

    const currentIndex = chronological.findIndex(
      (message) => message.messageId === current.messageId,
    );
    currentId = currentIndex > 0 ? chronological[currentIndex - 1].messageId : null;
  }

  return { path: path.reverse(), leafId };
}

export function getUserMessageSiblings(
  messages: ChatMessage[],
  message: ChatMessage,
): ChatMessage[] {
  return messages
    .filter(
      (candidate) =>
        candidate.parentMessageId === message.parentMessageId && candidate.role === "user",
    )
    .sort(compareCreatedAt);
}

export function findActiveLeafDescendant(messages: ChatMessage[], startId: string): string {
  let currentId = startId;
  while (true) {
    const children = messages
      .filter((message) => message.parentMessageId === currentId)
      .sort(compareCreatedAt);
    if (children.length === 0) return currentId;
    currentId = children[0].messageId;
  }
}

function compareCreatedAt(left: ChatMessage, right: ChatMessage): number {
  return new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime();
}
