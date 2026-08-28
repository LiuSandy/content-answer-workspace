import { memo, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  FileText,
  Globe,
  Pencil,
  Sparkles,
  Wrench,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { Textarea } from "@/components/ui/textarea";
import { SourceList } from "@/features/knowledge/source-list";
import { cn } from "@/lib/utils";
import { getChatMarkdownComponents } from "./chat-markdown-components";
import type { ChatMessage } from "./chat-message-tree";

const USER_MARKDOWN_COMPONENTS = getChatMarkdownComponents(true);
const ASSISTANT_MARKDOWN_COMPONENTS = getChatMarkdownComponents(false);

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

/** 单条历史消息及其编辑、复制、来源和分支操作。 */
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
      <div className={cn("flex w-full mb-3", isUser ? "justify-end" : "justify-start")}>
        <div className="w-[85%] border border-blue-500 rounded-2xl p-3 bg-card shadow-sm flex flex-col gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <Textarea
            value={editText}
            onChange={(event) => setEditText(event.target.value)}
            placeholder="编辑您的问题..."
            className="w-full min-h-[60px] bg-transparent resize-none border-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 p-0 text-sm focus:outline-none"
            autoFocus
          />
          <div className="flex justify-end gap-2 shrink-0">
            <Button variant="outline" size="sm" onClick={onCancelEdit} className="rounded-full px-4 h-7 text-xs border border-muted bg-transparent hover:bg-muted/10 text-foreground">
              取消
            </Button>
            <Button size="sm" onClick={() => onConfirmEdit(msg, editText)} disabled={isStreaming || !editText.trim()} className="rounded-full px-4 h-7 text-xs bg-blue-600 hover:bg-blue-700 text-white">
              发送
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (msg.messageType === "tool_status") {
    return (
      <div className="flex w-full justify-start mb-2 px-2">
        <div className="flex items-center gap-2 rounded-xl border border-border/30 bg-muted/20 px-3 py-1.5 text-xs text-muted-foreground select-none">
          <Wrench className="h-3.5 w-3.5 text-amber-500 shrink-0" />
          <span>
            执行工具: <code className="font-mono bg-muted/60 px-1 py-0.5 rounded text-[11px] border border-border/20">{msg.payload?.tool_type || msg.content}</code>
          </span>
          {msg.payload?.status === "completed" || !isStreaming ? (
            <Badge variant="outline" className="text-[10px] py-0 h-4 px-1.5 text-emerald-500 border-emerald-500/20 bg-emerald-500/5">已完成</Badge>
          ) : (
            <Badge variant="outline" className="text-[10px] py-0 h-4 px-1.5 text-amber-500 border-amber-500/20 bg-amber-500/5 animate-pulse">运行中</Badge>
          )}
        </div>
      </div>
    );
  }

  const siblingIndex = siblings.findIndex((sibling) => sibling.messageId === msg.messageId);

  return (
    <div className={cn("flex w-full mb-2", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("flex flex-col gap-1", isUser ? "max-w-[85%] items-end" : "max-w-[calc(100%-3rem)] w-full items-start mr-auto")}>
        <Card className={cn("border-none shadow-sm", isUser ? "bg-primary text-primary-foreground" : "bg-card w-full")}>
          <CardContent className="p-3.5">
            {msg.messageType === "text" && (
              <div className={cn("text-sm leading-relaxed max-w-none", isUser ? "text-primary-foreground" : "text-foreground/90")}>
                <MarkdownContent components={isUser ? USER_MARKDOWN_COMPONENTS : ASSISTANT_MARKDOWN_COMPONENTS}>
                  {msg.content || ""}
                </MarkdownContent>
                {!isUser && msg.payload?.ragSources && (
                  <SourceList sources={msg.payload.ragSources} fallbackNotice={msg.payload.ragFallback} traceId={msg.payload.traceId} />
                )}
                {!isUser && (msg.payload?.sourceList || msg.payload?.source_list) && (
                  <div className="mt-4 pt-3 border-t border-border/30">
                    <SourceListCard data={msg.payload.sourceList || msg.payload.source_list} onSelectItem={onSelectItem} selectedId={selectedId} />
                  </div>
                )}
              </div>
            )}
            {msg.messageType === "error" && (
              <div className="flex items-start gap-2.5 text-destructive bg-destructive/5 border border-destructive/20 rounded-xl p-3 w-full animate-in fade-in slide-in-from-bottom-2 duration-200">
                <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold">请求出错</p>
                  <p className="mt-1 text-xs leading-relaxed opacity-90">{msg.payload?.message || msg.content}</p>
                </div>
              </div>
            )}
            {msg.messageType === "source_list" && <SourceListCard data={msg.payload || msg.content} onSelectItem={onSelectItem} selectedId={selectedId} />}
            {msg.messageType === "choice_request" && <ChoiceRequestCard payload={msg.payload || {}} messageId={msg.messageId} onSelect={onSelectChoice} />}
            {msg.messageType === "source_card" && <SourceCardView data={msg.payload || msg.content} onSelectItem={onSelectItem} selectedId={selectedId} />}
          </CardContent>
        </Card>

        {!isStreaming && (
          <div className="flex items-center gap-2.5 px-2.5 mt-0.5 text-xs text-muted-foreground/60 select-none">
            <button onClick={handleCopy} className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5" title="复制文本">
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-500 animate-in fade-in zoom-in-50 duration-200" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
            {isUser && (
              <button onClick={() => onStartEdit(msg.messageId)} className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5" title="编辑提问">
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
            {isUser && siblings.length > 1 && (
              <div className="flex items-center gap-1 border-l pl-2.5 ml-1 border-muted-foreground/20">
                <button onClick={() => onSwitchSibling(msg, "prev")} disabled={siblingIndex === 0} className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed">
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <span className="text-[11px] font-medium min-w-[28px] text-center">{siblingIndex + 1} / {siblings.length}</span>
                <button onClick={() => onSwitchSibling(msg, "next")} disabled={siblingIndex === siblings.length - 1} className="cursor-pointer hover:text-muted-foreground transition-colors p-0.5 disabled:opacity-30 disabled:cursor-not-allowed">
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export const MemoizedMessageBubble = memo(MessageBubble, (previous, next) => (
  previous.msg.messageId === next.msg.messageId &&
  previous.msg.content === next.msg.content &&
  previous.msg.messageType === next.msg.messageType &&
  previous.msg.payload === next.msg.payload &&
  previous.isEditing === next.isEditing &&
  previous.selectedId === next.selectedId &&
  previous.isStreaming === next.isStreaming &&
  previous.siblings.length === next.siblings.length &&
  previous.siblings.every((sibling, index) => sibling.messageId === next.siblings[index]?.messageId) &&
  previous.onSelectItem === next.onSelectItem &&
  previous.onSelectChoice === next.onSelectChoice &&
  previous.onStartEdit === next.onStartEdit &&
  previous.onCancelEdit === next.onCancelEdit &&
  previous.onConfirmEdit === next.onConfirmEdit &&
  previous.onSwitchSibling === next.onSwitchSibling
));

function ChoiceRequestCard({ payload, messageId, onSelect }: { payload: any; messageId: string; onSelect: (optionId: string, messageId: string) => void }) {
  const options: Array<{ id: string; label: string; description?: string }> = payload?.options || [];
  if (options.length === 0) return null;
  return (
    <div className="mt-1 rounded-xl border border-amber-300/50 dark:border-amber-700/40 bg-amber-50/40 dark:bg-amber-950/10 p-3">
      <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">{payload?.question || "需要你选择一个处理方式："}</p>
      <div className="mt-2 flex flex-col gap-1.5">
        {options.map((option) => (
          <button key={option.id} onClick={() => onSelect(option.id, messageId)} className="text-left text-xs px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-white/60 dark:bg-zinc-900/40 hover:bg-amber-100/60 dark:hover:bg-amber-900/20 transition-colors">
            <span className="font-medium text-amber-900 dark:text-amber-200">{option.label}</span>
            {option.description && <span className="block text-[10px] text-muted-foreground mt-0.5">{option.description}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SourceListCard({ data, onSelectItem, selectedId }: { data: any; onSelectItem: (id: string) => void; selectedId: string | null }) {
  const items = data?.items || [];
  const toolType = data?.tool_type || "parse_url";
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        {toolType === "parse_url" ? <><Globe className="h-4 w-4 text-emerald-500" />解析到以下帖子内容：</> : <><Sparkles className="h-4 w-4 text-amber-500" />为您搜索采集到以下主题帖子：</>}
      </div>
      <div className="grid gap-2.5">
        {items.map((item: any, index: number) => {
          const itemId = item.id || item.externalId || `item-${index}`;
          return (
            <Card key={itemId} onClick={() => onSelectItem(itemId)} className={cn("cursor-pointer transition-all hover:shadow-sm", selectedId === itemId ? "border-primary/50 bg-primary/5" : "hover:border-muted-foreground/30")}>
              <CardContent className="p-3">
                <h4 className="mb-1 truncate text-sm font-semibold">{item.title}</h4>
                {item.summary && <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.summary}</p>}
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground mb-2 flex-wrap">
                  {item.publishedAt && <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{item.publishedAt}</span>}
                  {item.metrics?.likes && <span className="inline-flex items-center gap-1"><Sparkles className="h-3 w-3 text-amber-500" />{item.metrics.likes}</span>}
                  {item.author && <span>作者：{item.author}</span>}
                </div>
                <div className="flex items-center justify-between">
                  <Badge variant="secondary" className="text-[10px] uppercase">{item.platform || "zhihu"}</Badge>
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-primary"><FileText className="h-3 w-3" />开始创作回答</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function SourceCardView({ data, onSelectItem, selectedId }: { data: any; onSelectItem: (id: string) => void; selectedId: string | null }) {
  let item = data;
  if (typeof data === "string") {
    try {
      item = JSON.parse(data);
    } catch {
      item = {};
    }
  }
  const itemId = item?.id || item?.externalId || "source-card-item";
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground"><Globe className="h-4 w-4 text-emerald-500" />解析到以下帖子内容：</div>
      <Card onClick={() => onSelectItem(itemId)} className={cn("cursor-pointer transition-all hover:shadow-sm w-full", selectedId === itemId ? "border-primary/50 bg-primary/5" : "hover:border-muted-foreground/30")}>
        <CardContent className="p-3.5">
          <h4 className="mb-1 truncate text-sm font-semibold">{item?.title || "未知标题"}</h4>
          {item?.summary && <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.summary}</p>}
          <div className="flex items-center justify-between">
            <Badge variant="secondary" className="text-[10px] uppercase">{item?.platform || "zhihu"}</Badge>
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-primary transition-colors"><FileText className="h-3 w-3" />开始创作回答</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
