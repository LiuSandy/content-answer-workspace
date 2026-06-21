import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { ChatMessage } from "@/types/workflow";

import { ChatMessageInput } from "./chat-message-input";
import { ChatMessageThread } from "./chat-message-thread";
import { ChatSessionList } from "./chat-session-list";
import { createSession, getConversationHistory, listSessions, sendConversationMessage } from "./workflow-api";

const SESSION_LIST_QUERY_KEY = ["chat-session-list"];

export function ChatPage() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const setActiveSessionId = useWorkspaceStore((s) => s.setActiveSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const queryClient = useQueryClient();

  const sessionListQuery = useQuery({
    queryKey: SESSION_LIST_QUERY_KEY,
    queryFn: listSessions,
  });

  const historyQuery = useQuery({
    queryKey: ["chat-history", activeSessionId],
    queryFn: () => getConversationHistory(activeSessionId as string),
    enabled: Boolean(activeSessionId),
  });

  useEffect(() => {
    setMessages(historyQuery.data?.messages ?? []);
  }, [historyQuery.data]);

  async function handleCreateSession() {
    const session = await createSession();
    setActiveSessionId(session.sessionId);
    setMessages([]);
    queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
  }

  async function handleSend(message: string) {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    try {
      const res = await sendConversationMessage({ sessionId: activeSessionId, message });
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "发送失败，请重试" }]);
    } finally {
      setIsSending(false);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    }
  }

  return (
    <section className="flex min-h-0 flex-1 gap-4">
      <ChatSessionList
        sessions={sessionListQuery.data ?? []}
        activeSessionId={activeSessionId}
        onSelect={setActiveSessionId}
        onCreate={handleCreateSession}
      />
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border bg-white">
        <ChatMessageThread messages={messages} isLoading={historyQuery.isLoading} />
        <ChatMessageInput disabled={!activeSessionId || isSending} onSend={handleSend} />
      </div>
    </section>
  );
}
