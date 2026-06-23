import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/workflow";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
  isSending: boolean;
  streamingContent?: string;
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

export function ChatMessageThread({ messages, isLoading, isSending, streamingContent }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, streamingContent]);

  return (
    <div className="flex-1 min-h-0 space-y-3 overflow-y-auto p-4">
      {isLoading && <p className="text-sm text-muted-foreground">加载历史消息中...</p>}
      {!isLoading && messages.length === 0 && (
        <p className="text-sm text-muted-foreground">还没有消息，发一句话开始对话吧。</p>
      )}
      {messages.map((message, index) => (
        <div
          key={index}
          className={cn("flex", message.role === "user" ? "justify-end" : "justify-start")}
        >
          <div
            className={cn(
              "w-fit max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed",
              message.role === "user"
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-foreground",
            )}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        </div>
      ))}
      {isSending && !streamingContent && (
        <div className="flex justify-start">
          <div className="rounded-lg bg-muted">
            <ThinkingDots />
          </div>
        </div>
      )}
      {isSending && streamingContent && (
        <div className="flex justify-start">
          <div className="w-fit max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed bg-muted text-foreground">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
