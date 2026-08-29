import { memo, useEffect, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Copy, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { MessageContent, ToolStatusMessage } from "./chat-message-content";
import type { ChatMessage } from "../model/chat-message-tree";

export interface MessageBubbleProps {
  msg: ChatMessage;
  onSelectItem: (id: string) => void;
  onSelectChoice: (optionId: string, messageId: string) => void;
  selectedId: string | null;
  isEditing: boolean;
  onStartEdit: (messageId: string) => void;
  onCancelEdit: () => void;
  onConfirmEdit: (message: ChatMessage, content: string) => void;
  siblings: ChatMessage[];
  onSwitchSibling: (message: ChatMessage, direction: "prev" | "next") => void;
  isStreaming: boolean;
}

/** 单条历史消息的公共外壳，以及编辑、复制和分支操作。 */
function MessageBubble({
  msg,
  onSelectItem,
  onSelectChoice,
  selectedId,
  isEditing,
  onStartEdit,
  onCancelEdit,
  onConfirmEdit,
  siblings,
  onSwitchSibling,
  isStreaming,
}: MessageBubbleProps) {
  const isUser = msg.role === "user";
  const [editText, setEditText] = useState(msg.content || "");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isEditing) setEditText(msg.content || "");
  }, [isEditing, msg.content]);

  const handleCopy = async () => {
    if (!msg.content) return;
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error("Failed to copy text: ", error);
    }
  };

  if (isEditing) {
    return (
      <MessageEditor
        msg={msg}
        content={editText}
        isStreaming={isStreaming}
        onContentChange={setEditText}
        onCancel={onCancelEdit}
        onConfirm={onConfirmEdit}
      />
    );
  }

  if (msg.messageType === "tool_status") {
    return <ToolStatusMessage msg={msg} isStreaming={isStreaming} />;
  }

  return (
    <div className={cn("flex w-full mb-2", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "flex flex-col gap-1",
          isUser ? "max-w-[85%] items-end" : "max-w-[calc(100%-3rem)] w-full items-start mr-auto",
        )}
      >
        <Card
          className={cn(
            "border-none shadow-sm",
            isUser ? "bg-primary text-primary-foreground" : "bg-card w-full",
          )}
        >
          <CardContent className="p-3.5">
            <MessageContent
              msg={msg}
              onSelectItem={onSelectItem}
              onSelectChoice={onSelectChoice}
              selectedId={selectedId}
            />
          </CardContent>
        </Card>

        {!isStreaming && (
          <MessageActions
            msg={msg}
            isUser={isUser}
            copied={copied}
            siblings={siblings}
            onCopy={handleCopy}
            onStartEdit={onStartEdit}
            onSwitchSibling={onSwitchSibling}
          />
        )}
      </div>
    </div>
  );
}

function MessageEditor({
  msg,
  content,
  isStreaming,
  onContentChange,
  onCancel,
  onConfirm,
}: {
  msg: ChatMessage;
  content: string;
  isStreaming: boolean;
  onContentChange: (content: string) => void;
  onCancel: () => void;
  onConfirm: (message: ChatMessage, content: string) => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex w-full mb-3", isUser ? "justify-end" : "justify-start")}>
      <div className="w-[85%] border border-blue-500 rounded-2xl p-3 bg-card shadow-sm flex flex-col gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-200">
        <Textarea
          value={content}
          onChange={(event) => onContentChange(event.target.value)}
          placeholder="编辑您的问题..."
          className="w-full min-h-[60px] bg-transparent resize-none border-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 p-0 text-sm focus:outline-none"
          autoFocus
        />
        <div className="flex justify-end gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={onCancel}
            className="rounded-full px-4 h-7 text-xs border border-muted bg-transparent hover:bg-muted/10 text-foreground"
          >
            取消
          </Button>
          <Button
            size="sm"
            onClick={() => onConfirm(msg, content)}
            disabled={isStreaming || !content.trim()}
            className="rounded-full px-4 h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white"
          >
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}

function MessageActions({
  msg,
  isUser,
  copied,
  siblings,
  onCopy,
  onStartEdit,
  onSwitchSibling,
}: {
  msg: ChatMessage;
  isUser: boolean;
  copied: boolean;
  siblings: ChatMessage[];
  onCopy: () => void;
  onStartEdit: (messageId: string) => void;
  onSwitchSibling: (message: ChatMessage, direction: "prev" | "next") => void;
}) {
  const siblingIndex = siblings.findIndex((sibling) => sibling.messageId === msg.messageId);

  return (
    <div className="flex items-center gap-2.5 px-2.5 mt-0.5 text-xs text-muted-foreground/60 select-none">
      <button
        onClick={onCopy}
        className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5"
        title="复制文本"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-500 animate-in fade-in zoom-in-50 duration-200" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
      {isUser && (
        <button
          onClick={() => onStartEdit(msg.messageId)}
          className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5"
          title="编辑提问"
        >
          <Pencil className="h-3.5 w-3.5" />
        </button>
      )}
      {isUser && siblings.length > 1 && (
        <div className="flex items-center gap-1 border-l pl-2.5 ml-1 border-muted-foreground/20">
          <button
            onClick={() => onSwitchSibling(msg, "prev")}
            disabled={siblingIndex === 0}
            className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-[11px] font-medium min-w-[28px] text-center">
            {siblingIndex + 1} / {siblings.length}
          </span>
          <button
            onClick={() => onSwitchSibling(msg, "next")}
            disabled={siblingIndex === siblings.length - 1}
            className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}

export const MemoizedMessageBubble = memo(
  MessageBubble,
  (previous, next) =>
    previous.msg.messageId === next.msg.messageId &&
    previous.msg.content === next.msg.content &&
    previous.msg.messageType === next.msg.messageType &&
    previous.msg.payload === next.msg.payload &&
    previous.isEditing === next.isEditing &&
    previous.selectedId === next.selectedId &&
    previous.isStreaming === next.isStreaming &&
    previous.siblings.length === next.siblings.length &&
    previous.siblings.every(
      (sibling, index) => sibling.messageId === next.siblings[index]?.messageId,
    ) &&
    previous.onSelectItem === next.onSelectItem &&
    previous.onSelectChoice === next.onSelectChoice &&
    previous.onStartEdit === next.onStartEdit &&
    previous.onCancelEdit === next.onCancelEdit &&
    previous.onConfirmEdit === next.onConfirmEdit &&
    previous.onSwitchSibling === next.onSwitchSibling,
);

export { SourceListCard } from "./chat-message-content";
