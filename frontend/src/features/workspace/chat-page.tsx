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
// 实时的「正在整理最终回答」步骤；仅作进行中提示，不写入历史，故由前端独立维护
const FINAL_OUTPUT_STEP = "✍️ 正在整理最终回答…";

export function ChatPage() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [toolSteps, setToolSteps] = useState<string[]>([]);
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
    setToolSteps([]);
    // 本地累加器：回调闭包捕获的 state 是初始值，用局部变量保证 onDone 拿到最新步骤
    let localToolSteps: string[] = [];
    try {
      await streamConversationMessage(
        { sessionId: activeSessionId, message },
        {
          onToolStart: (text) => {
            localToolSteps = [...localToolSteps, text];
            setToolSteps(localToolSteps);
          },
          onToolEnd: (text) => {
            localToolSteps = [...localToolSteps, text];
            setToolSteps(localToolSteps);
          },
          onChunk: (text) => {
            setStreamingContent((prev) => prev + text);
            // 最终回答开始流出时，补一条「正在整理」进行中提示（仅一次，仅在有工具调用时）
            if (localToolSteps.length > 0 && localToolSteps[localToolSteps.length - 1] !== FINAL_OUTPUT_STEP) {
              localToolSteps = [...localToolSteps, FINAL_OUTPUT_STEP];
              setToolSteps(localToolSteps);
            }
          },
          onDone: (data) => {
            setStreamingContent("");
            setToolSteps([]);
            // 落库的过程消息剔除「正在整理」这类进行中提示，与历史回看保持一致
            const committedSteps = localToolSteps.filter((step) => step !== FINAL_OUTPUT_STEP);
            setMessages((prev) => [
              ...prev,
              ...(committedSteps.length > 0
                ? [{ role: "tool" as const, content: "", steps: committedSteps }]
                : []),
              { role: "assistant", content: data.reply },
            ]);
          },
          onError: (msg) => {
            setStreamingContent("");
            setToolSteps([]);
            setMessages((prev) => [...prev, { role: "assistant", content: `发送失败：${msg}` }]);
          },
        },
      );
    } catch {
      setStreamingContent("");
      setToolSteps([]);
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
          toolSteps={toolSteps}
        />
        <ChatMessageInput disabled={!activeSessionId || isSending} onSend={handleSend} />
      </div>
    </section>
  );
}

