import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { ChatCollectResult, ChatMessage, ChatRunUiStatus } from "@/types/workflow";

import {
  clearStoredChatRun,
  readStoredChatRun,
  saveStoredChatRun,
  subscribeChatConversationRun,
  type ChatConversationRunSubscription,
  type StoredChatRun,
} from "./chat-conversation-run-client";
import { appendConversationTurn, FINAL_OUTPUT_STEP } from "./chat-collect-result-utils";
import { ChatMessageInput } from "./chat-message-input";
import { ChatMessageThread } from "./chat-message-thread";
import {
  createChatConversationRun,
  getChatConversationRun,
  getConversationHistory,
} from "./workflow-api";

const SESSION_LIST_QUERY_KEY = ["chat-session-list"];

function ensureUserMessage(messages: ChatMessage[], content: string): ChatMessage[] {
  if (!content || messages.some((message) => message.role === "user" && message.content === content)) {
    return messages;
  }
  return [...messages, { role: "user", content }];
}

export function ChatPage() {
  const activeSessionId = useWorkspaceStore((s) => s.activeSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [toolSteps, setToolSteps] = useState<string[]>([]);
  const [liveCollectResults, setLiveCollectResults] = useState<ChatCollectResult[]>([]);
  const [runStatus, setRunStatus] = useState<ChatRunUiStatus | null>(null);
  const [runStatusLabel, setRunStatusLabel] = useState<string | null>(null);
  const subscriptionRef = useRef<ChatConversationRunSubscription | null>(null);
  const activeRunRef = useRef<StoredChatRun | null>(null);
  const queryClient = useQueryClient();

  const historyQuery = useQuery({
    queryKey: ["chat-history", activeSessionId],
    queryFn: () => getConversationHistory(activeSessionId as string),
    enabled: Boolean(activeSessionId),
  });

  const clearLiveRun = useCallback(() => {
    subscriptionRef.current?.close();
    subscriptionRef.current = null;
    activeRunRef.current = null;
    clearStoredChatRun();
    setIsSending(false);
    setStreamingContent("");
    setToolSteps([]);
    setLiveCollectResults([]);
    setRunStatus(null);
    setRunStatusLabel(null);
  }, []);

  const updateActiveRun = useCallback((patch: Partial<StoredChatRun>) => {
    if (!activeRunRef.current) return null;
    const next = { ...activeRunRef.current, ...patch };
    activeRunRef.current = next;
    saveStoredChatRun(next);
    return next;
  }, []);

  const finishRun = useCallback((reply: string, collectResults: ChatCollectResult[]) => {
    const current = activeRunRef.current;
    const committedSteps = current?.toolSteps ?? [];
    const finalCollectResults = collectResults.length > 0 ? collectResults : current?.collectResults ?? [];

    setMessages((prev) =>
      appendConversationTurn(prev, {
        toolSteps: committedSteps,
        collectResults: finalCollectResults,
        reply,
      }),
    );
    clearLiveRun();
    queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["chat-history", activeSessionId] });
  }, [activeSessionId, clearLiveRun, queryClient]);

  const failRun = useCallback((message: string, status: ChatRunUiStatus) => {
    setMessages((prev) => [...prev, { role: "assistant", content: message }]);
    clearLiveRun();
    setRunStatus(status);
    queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["chat-history", activeSessionId] });
  }, [activeSessionId, clearLiveRun, queryClient]);

  const startSubscription = useCallback((runId: string, lastEventId: number) => {
    subscriptionRef.current?.close();
    subscriptionRef.current = subscribeChatConversationRun(runId, lastEventId, {
      onToolStart: (text, eventId) => {
        const current = activeRunRef.current;
        const nextSteps = [...(current?.toolSteps ?? []), text];
        updateActiveRun({ toolSteps: nextSteps, lastEventId: eventId, status: "streaming", error: null });
        setToolSteps(nextSteps);
        setIsSending(true);
        setRunStatus("streaming");
        setRunStatusLabel(null);
      },
      onToolEnd: (text, eventId) => {
        const current = activeRunRef.current;
        const nextSteps = [...(current?.toolSteps ?? []), text];
        updateActiveRun({ toolSteps: nextSteps, lastEventId: eventId, status: "streaming", error: null });
        setToolSteps(nextSteps);
        setIsSending(true);
        setRunStatus("streaming");
        setRunStatusLabel(null);
      },
      onCollectResult: (result, eventId) => {
        const current = activeRunRef.current;
        const nextResults = [...(current?.collectResults ?? []), result];
        updateActiveRun({ collectResults: nextResults, lastEventId: eventId, status: "streaming", error: null });
        setLiveCollectResults(nextResults);
        setIsSending(true);
        setRunStatus("streaming");
        setRunStatusLabel(null);
      },
      onChunk: (text, eventId) => {
        const current = activeRunRef.current;
        const currentSteps = current?.toolSteps ?? [];
        const nextSteps =
          currentSteps.length > 0 && currentSteps[currentSteps.length - 1] !== FINAL_OUTPUT_STEP
            ? [...currentSteps, FINAL_OUTPUT_STEP]
            : currentSteps;
        const nextContent = `${current?.streamingContent ?? ""}${text}`;
        updateActiveRun({
          streamingContent: nextContent,
          toolSteps: nextSteps,
          lastEventId: eventId,
          status: "streaming",
          error: null,
        });
        setStreamingContent(nextContent);
        setToolSteps(nextSteps);
        setIsSending(true);
        setRunStatus("streaming");
        setRunStatusLabel(null);
      },
      onDone: (event) => {
        finishRun(event.data.reply, event.data.collectResults ?? []);
      },
      onChatError: (message, eventId) => {
        updateActiveRun({ lastEventId: eventId, status: "error", error: message });
        failRun(`发送失败：${message}`, "error");
      },
      onCanceled: (message, eventId) => {
        updateActiveRun({ lastEventId: eventId, status: "canceled", error: message });
        failRun(message || "对话已取消", "canceled");
      },
      onRecovering: () => {
        updateActiveRun({ status: "recovering" });
        setIsSending(true);
        setRunStatus("recovering");
        setRunStatusLabel("连接中断，正在恢复...");
      },
      onInterrupted: (message) => {
        updateActiveRun({ status: "interrupted", error: message });
        subscriptionRef.current?.close();
        subscriptionRef.current = null;
        setIsSending(false);
        setRunStatus("interrupted");
        setRunStatusLabel(message);
        setMessages((prev) => [...prev, { role: "assistant", content: message }]);
      },
    });
  }, [failRun, finishRun, updateActiveRun]);

  useEffect(() => {
    const baseMessages = historyQuery.data?.messages ?? [];
    const activeRun = activeRunRef.current;
    if (activeRun && activeRun.sessionId === activeSessionId && activeRun.message) {
      setMessages(ensureUserMessage(baseMessages, activeRun.message));
      return;
    }
    setMessages(baseMessages);
  }, [activeSessionId, historyQuery.data]);

  useEffect(() => {
    if (!activeSessionId) return;
    const stored = readStoredChatRun();
    if (!stored || stored.sessionId !== activeSessionId) return;

    let ignore = false;
    getChatConversationRun(stored.runId)
      .then((snapshot) => {
        if (ignore) return;
        if (snapshot.status === "done" || snapshot.status === "error" || snapshot.status === "canceled") {
          clearStoredChatRun();
          queryClient.invalidateQueries({ queryKey: ["chat-history", activeSessionId] });
          return;
        }

        const restored: StoredChatRun = {
          ...stored,
          message: stored.message || snapshot.message,
          status: stored.status === "interrupted" ? "streaming" : stored.status,
          error: null,
        };
        activeRunRef.current = restored;
        saveStoredChatRun(restored);
        setMessages((prev) => ensureUserMessage(prev, restored.message || snapshot.message));
        setStreamingContent(restored.streamingContent);
        setToolSteps(restored.toolSteps);
        setLiveCollectResults(restored.collectResults);
        setIsSending(true);
        setRunStatus("streaming");
        setRunStatusLabel(null);
        startSubscription(restored.runId, restored.lastEventId);
      })
      .catch(() => {
        if (ignore) return;
        clearStoredChatRun();
      });

    return () => {
      ignore = true;
    };
  }, [activeSessionId, queryClient, startSubscription]);

  useEffect(() => {
    return () => {
      subscriptionRef.current?.close();
    };
  }, []);

  async function handleSend(message: string) {
    if (!activeSessionId || isSending) {
      return;
    }

    clearLiveRun();
    setMessages((prev) => [...prev, { role: "user", content: message }]);
    setIsSending(true);
    setRunStatus("creating");
    setRunStatusLabel("正在创建对话运行...");

    try {
      const created = await createChatConversationRun({ sessionId: activeSessionId, message });
      const stored: StoredChatRun = {
        runId: created.runId,
        sessionId: activeSessionId,
        message,
        lastEventId: 0,
        streamingContent: "",
        toolSteps: [],
        collectResults: [],
        status: "streaming",
        error: null,
      };
      activeRunRef.current = stored;
      saveStoredChatRun(stored);
      setRunStatus("streaming");
      setRunStatusLabel(null);
      startSubscription(created.runId, 0);
    } catch {
      failRun("发送失败，请重试", "error");
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
          liveCollectResults={liveCollectResults}
          liveStatusLabel={runStatusLabel ?? (runStatus === "creating" ? "正在创建对话运行..." : null)}
        />
        <ChatMessageInput disabled={!activeSessionId || isSending} onSend={handleSend} />
      </div>
    </section>
  );
}
