export type ActiveChatStream = {
  chatId: string;
  controller: AbortController;
};

type RefreshableMessage = {
  messageType: string;
  content: string | null;
  payload: unknown;
};

export function abortStreamForChat(
  active: ActiveChatStream | null,
  chatId: string | null,
): ActiveChatStream | null {
  if (!active || active.chatId !== chatId) {
    return active;
  }

  active.controller.abort();
  return null;
}

export function reconcileTransientStreamError(
  currentError: string | null,
  refreshedMessages: RefreshableMessage[],
): string | null {
  if (!currentError) {
    return null;
  }

  const isPersisted = refreshedMessages.some((message) => {
    if (message.messageType !== "error") {
      return false;
    }
    const payload = message.payload;
    const persistedMessage =
      payload && typeof payload === "object" && "message" in payload
        ? (payload as { message?: unknown }).message
        : null;
    return message.content === currentError || persistedMessage === currentError;
  });

  return isPersisted ? null : currentError;
}
