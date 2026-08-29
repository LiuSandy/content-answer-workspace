import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Sparkles } from "lucide-react";
import { apiGet } from "@/lib/api";
import { PromptInput } from "@/components/ui/prompt-input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatStore } from "@/store/chat-store";
import { AgentWorkspacePanel } from "../../tasks/components/agent-workspace-panel";
import { getChatMarkdownComponents } from "./chat-markdown-components";
import { MemoizedMessageBubble, SourceListCard } from "./chat-message-bubble";
import {
  findActiveLeafDescendant,
  getActiveMessagePath,
  getUserMessageSiblings,
  resolveParentIds,
  type ChatMessage,
} from "../model/chat-message-tree";
import { MemoryAppliedBadge } from "./memory-applied-badge";
import { StreamingMessageCard } from "./streaming-message-card";
import { TaskPlanCard } from "../../tasks/components/task-plan-card";
import { useChatScroll } from "../hooks/use-chat-scroll";
import { useChatStream } from "../hooks/use-chat-stream";

/** 中间对话面板：负责组合消息路径、流式会话和输入区域。 */
export function ChatPanel() {
  const {
    currentChatId,
    setSelectedSourceItemId,
    selectedSourceItemId,
    activeLeafMessageId,
    setActiveLeafMessageId,
  } = useChatStore();
  const [inputText, setInputText] = useState("");
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const markdownComponents = useMemo(() => getChatMarkdownComponents(false), []);

  const {
    isUserScrolledUp,
    messagesEndRef,
    handleScrollCapture,
    handleStreamingContentChange,
    resetScrollTracking,
    resumeAutoScroll,
  } = useChatScroll(activeLeafMessageId);
  const {
    isStreaming,
    activeTaskPlanId,
    multiAgentResult,
    streamingController,
    sendMessage,
    selectChoice,
  } = useChatStream(resetScrollTracking);

  const { data: messages = [], isLoading } = useQuery<ChatMessage[]>({
    queryKey: ["messages", currentChatId],
    queryFn: () => apiGet(`/api/chats/${currentChatId}/messages`),
    enabled: Boolean(currentChatId),
  });
  const resolvedMessages = useMemo(() => resolveParentIds(messages), [messages]);
  const { path: selectedBranchMessages, leafId: calculatedLeafId } = useMemo(
    () => getActiveMessagePath(resolvedMessages, activeLeafMessageId),
    [activeLeafMessageId, resolvedMessages],
  );

  console.log("selectedBranchMessages", selectedBranchMessages);

  useEffect(() => {
    if (calculatedLeafId && calculatedLeafId !== activeLeafMessageId) {
      setActiveLeafMessageId(calculatedLeafId);
    }
  }, [activeLeafMessageId, calculatedLeafId, setActiveLeafMessageId]);

  useEffect(() => {
    setEditingMessageId(null);
  }, [currentChatId]);

  const handleSendMessage = useCallback(() => {
    const content = inputText.trim();
    if (!content || isStreaming) return;
    setInputText("");
    void sendMessage(content);
  }, [inputText, isStreaming, sendMessage]);

  const handleConfirmEdit = useCallback(
    (message: ChatMessage, content: string) => {
      setEditingMessageId(null);
      void sendMessage(content, message.parentMessageId);
    },
    [sendMessage],
  );

  const handleSwitchSibling = useCallback(
    (message: ChatMessage, direction: "prev" | "next") => {
      const siblings = getUserMessageSiblings(resolvedMessages, message);
      const currentIndex = siblings.findIndex((sibling) => sibling.messageId === message.messageId);
      const targetIndex = direction === "prev" ? currentIndex - 1 : currentIndex + 1;
      const target = siblings[targetIndex];
      if (!target) return;
      setActiveLeafMessageId(findActiveLeafDescendant(resolvedMessages, target.messageId));
    },
    [resolvedMessages, setActiveLeafMessageId],
  );

  const handleStartEdit = useCallback((messageId: string) => {
    setEditingMessageId(messageId);
  }, []);
  const handleCancelEdit = useCallback(() => setEditingMessageId(null), []);

  const renderStreamingSourceList = useCallback(
    (data: unknown) => (
      <SourceListCard
        data={data}
        onSelectItem={setSelectedSourceItemId}
        selectedId={selectedSourceItemId}
      />
    ),
    [selectedSourceItemId, setSelectedSourceItemId],
  );

  const streamingMessageCard = (
    <StreamingMessageCard
      controller={streamingController}
      markdownComponents={markdownComponents}
      renderSourceList={renderStreamingSourceList}
      onContentChange={handleStreamingContentChange}
    />
  );

  if (!currentChatId) {
    return (
      <div className="flex flex-col flex-1 bg-zinc-50/50 dark:bg-zinc-950/20 items-center justify-center p-6 select-none overflow-y-auto min-h-0">
        <div className="max-w-2xl w-full flex flex-col items-center gap-6 my-auto">
          <div className="flex flex-col items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-500 text-white shadow-md shadow-indigo-500/20">
              <Sparkles className="h-6 w-6" />
            </div>
            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2 mt-1">
              欢迎使用超级大脑，请开启你的对话
            </h1>
          </div>
          <div className="w-full">
            <PromptInput
              value={inputText}
              onChange={setInputText}
              onSubmit={handleSendMessage}
              placeholder="粘贴链接或输入采集主题..."
              disabled={isStreaming}
            />
            <div className="mt-4">{streamingMessageCard}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/30 relative">
      <div className="relative flex-1 min-h-0 flex flex-col">
        <ScrollArea className="flex-1 min-h-0 p-4" onScrollCapture={handleScrollCapture}>
          <div className="flex w-full flex-col gap-4 px-2">
            {isLoading ? (
              <div className="space-y-3 py-8">
                <Skeleton className="mx-auto h-16 w-3/4 rounded-xl" />
                <Skeleton className="ml-auto h-10 w-1/2 rounded-xl" />
                <Skeleton className="h-16 w-3/4 rounded-xl" />
              </div>
            ) : (
              selectedBranchMessages.map((message) => (
                <MemoizedMessageBubble
                  key={message.messageId}
                  msg={message}
                  onSelectItem={setSelectedSourceItemId}
                  onSelectChoice={selectChoice}
                  selectedId={selectedSourceItemId}
                  isEditing={editingMessageId === message.messageId}
                  onStartEdit={handleStartEdit}
                  onCancelEdit={handleCancelEdit}
                  onConfirmEdit={handleConfirmEdit}
                  siblings={getUserMessageSiblings(resolvedMessages, message)}
                  onSwitchSibling={handleSwitchSibling}
                  isStreaming={isStreaming}
                />
              ))
            )}

            {streamingMessageCard}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {isUserScrolledUp && (
          <button
            type="button"
            onClick={resumeAutoScroll}
            className="absolute bottom-3 right-6 z-20 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-background/90 backdrop-blur-sm border border-border/80 shadow-md rounded-full text-foreground hover:bg-muted transition-all animate-in fade-in zoom-in-95 cursor-pointer"
          >
            <ChevronDown className="h-3.5 w-3.5" />
            <span>回到底部</span>
            {isStreaming && <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />}
          </button>
        )}
      </div>

      {activeTaskPlanId && <TaskPlanCard planId={activeTaskPlanId} />}
      {multiAgentResult && (
        <AgentWorkspacePanel
          goal=""
          running={multiAgentResult.status === "running" || multiAgentResult.status === "pending"}
          result={multiAgentResult}
        />
      )}

      <div className="shrink-0 border-t bg-card p-4 fixed-bottom-input-area">
        <div className="flex items-center gap-2 mb-2">
          <MemoryAppliedBadge />
        </div>
        <PromptInput
          value={inputText}
          onChange={setInputText}
          onSubmit={handleSendMessage}
          placeholder="粘贴链接或输入采集主题..."
          disabled={isStreaming}
        />
      </div>
    </div>
  );
}
