import { useEffect, useMemo, useRef } from "react";

import { cn } from "@/lib/utils";
import type { ChatCollectResult, ChatMessage } from "@/types/workflow";

import { ChatToolProcess } from "./chat-tool-process";
import { ChatTaskResultMessage } from "./chat-task-result-message";
import { MarkdownMessage } from "./markdown-message";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
  isSending: boolean;
  streamingContent?: string;
  toolSteps?: string[];
  /** 实时采集结果：工具调用完成但 LLM 尚未输出最终回答时展示 */
  liveCollectResult?: ChatCollectResult | null;
  liveCollectResults?: ChatCollectResult[];
  liveStatusLabel?: string | null;
};

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 px-3 py-2">
      <span className="text-sm text-muted-foreground">思考中</span>
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="inline-block h-1 w-1 rounded-full bg-muted-foreground animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </span>
    </div>
  );
}

export function ChatMessageThread({
  messages,
  isLoading,
  isSending,
  streamingContent,
  toolSteps = [],
  liveCollectResult,
  liveCollectResults,
  liveStatusLabel,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeCollectResults = useMemo(
    () => liveCollectResults ?? (liveCollectResult ? [liveCollectResult] : []),
    [liveCollectResult, liveCollectResults],
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, streamingContent, toolSteps, activeCollectResults]);

  return (
    <div className="flex-1 min-h-0 space-y-4 overflow-y-auto p-4">
      {isLoading && <p className="text-sm text-muted-foreground">加载历史消息中...</p>}
      {!isLoading && messages.length === 0 && (
        <p className="text-sm text-muted-foreground">还没有消息，发一句话开始对话吧。</p>
      )}
      {messages.map((message, index) => {
        if (message.role === "tool") {
          return (
            <div key={index} className="flex justify-start">
              <ChatToolProcess steps={message.steps ?? []} />
            </div>
          );
        }
        if (message.role === "collect" && message.collectResult) {
          return (
            <div key={index} className="flex justify-start">
              <ChatTaskResultMessage content="" collectResults={[message.collectResult]} />
            </div>
          );
        }
        if (message.role === "assistant" && message.collectResults?.length) {
          return (
            <div key={index} className="flex justify-start">
              <ChatTaskResultMessage
                content={message.content}
                steps={message.steps}
                collectResults={message.collectResults}
              />
            </div>
          );
        }
        return (
          <div
            key={index}
            className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}
          >
            <div
              className={cn(
                "w-fit max-w-[75%] rounded-lg px-4 py-3 text-sm leading-relaxed",
                message.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground",
              )}
            >
              <MarkdownMessage content={message.content} />
            </div>
          </div>
        );
      })}
      {isSending && (toolSteps.length > 0 || activeCollectResults.length > 0 || streamingContent) && (
        <div className="flex justify-start">
          <ChatTaskResultMessage
            content={streamingContent || ""}
            steps={toolSteps}
            collectResults={activeCollectResults}
            live
            statusLabel={liveStatusLabel ?? undefined}
          />
        </div>
      )}
      {isSending && !streamingContent && toolSteps.length === 0 && activeCollectResults.length === 0 && (
        <div className="flex justify-start">
          <div className="rounded-lg bg-muted">
            <ThinkingDots />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
