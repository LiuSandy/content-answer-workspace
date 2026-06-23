import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { ChatMessage } from "@/types/workflow";

import { ChatMessageInput } from "./chat-message-input";
import { ChatMessageThread } from "./chat-message-thread";
import {
  getConversationHistory,
  streamConversationMessage,
} from "./workflow-api";

const SESSION_LIST_QUERY_KEY = ["chat-session-list"];

export function ChatPage() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const queryClient = useQueryClient();

  const historyQuery = useQuery({
    queryKey: ["chat-history", activeSessionId],
    queryFn: () => getConversationHistory(activeSessionId as string),
    enabled: Boolean(activeSessionId),
  });

  useEffect(() => {
    setMessages(historyQuery.data?.messages ?? []);
  }, [historyQuery.data]);

  async function handleSend(message: string) {
    if (!activeSessionId) {
      return;
    }
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    setStreamingContent("");
    try {
      await streamConversationMessage(
        { sessionId: activeSessionId, message },
        {
          onChunk: (text) => {
            setStreamingContent((prev) => prev + text);
          },
          onDone: (data) => {
            setStreamingContent("");
            setMessages((prev) => [...prev, { role: "assistant", content: data.reply }]);
          },
          onError: (msg) => {
            setStreamingContent("");
            setMessages((prev) => [...prev, { role: "assistant", content: `发送失败：${msg}` }]);
          },
        },
      );
    } catch {
      setStreamingContent("");
      setMessages((prev) => [...prev, { role: "assistant", content: "发送失败，请重试" }]);
    } finally {
      setIsSending(false);
      queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    }
  }

  return (
    <section className="flex min-h-0 flex-1">
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border bg-white">
        <ChatMessageThread
          messages={messages}
          isLoading={historyQuery.isLoading}
          isSending={isSending}
          streamingContent={streamingContent}
        />
        <ChatMessageInput disabled={!activeSessionId || isSending} onSend={handleSend} />
      </div>
    </section>
  );
}

