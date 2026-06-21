import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/workflow";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
};

export function ChatMessageThread({ messages, isLoading }: Props) {
  return (
    <div className="flex-1 min-h-0 space-y-3 overflow-y-auto p-4">
      {isLoading && <p className="text-sm text-muted-foreground">加载历史消息中...</p>}
      {!isLoading && messages.length === 0 && (
        <p className="text-sm text-muted-foreground">还没有消息，发一句话开始对话吧。</p>
      )}
      {messages.map((message, index) => (
        <div
          key={index}
          className={cn(
            "max-w-[75%] rounded-lg px-3 py-2 text-sm leading-relaxed",
            message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "bg-muted text-foreground",
          )}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      ))}
    </div>
  );
}
