import { AlertCircle, Clock, FileText, Globe, Sparkles, Wrench } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { MarkdownContent } from "@/components/ui/markdown-content";
import { SourceList } from "@/features/knowledge/source-list";
import { cn } from "@/lib/utils";
import { getChatMarkdownComponents } from "./chat-markdown-components";
import type { ChatMessage } from "../model/chat-message-tree";

const USER_MARKDOWN_COMPONENTS = getChatMarkdownComponents(true);
const ASSISTANT_MARKDOWN_COMPONENTS = getChatMarkdownComponents(false);

interface MessageContentProps {
  msg: ChatMessage;
  onSelectItem: (id: string) => void;
  onSelectChoice: (optionId: string, messageId: string) => void;
  selectedId: string | null;
}

/** 根据消息类型选择对应的内容组件；公共气泡外壳由 MessageBubble 统一负责。 */
export function MessageContent(props: MessageContentProps) {
  switch (props.msg.messageType) {
    case "text":
      return <TextMessageContent {...props} />;
    case "error":
      return <ErrorMessageContent msg={props.msg} />;
    case "source_list":
      return <SourceListMessageContent {...props} />;
    case "choice_request":
      return <ChoiceRequestMessageContent {...props} />;
    case "source_card":
      return <SourceCardMessageContent {...props} />;
    case "tool_status":
      return null;
  }
}

function TextMessageContent({ msg, onSelectItem, selectedId }: MessageContentProps) {
  const isUser = msg.role === "user";

  return (
    <div
      className={cn(
        "text-sm leading-relaxed max-w-none",
        isUser ? "text-primary-foreground" : "text-foreground/90",
      )}
    >
      <MarkdownContent
        components={isUser ? USER_MARKDOWN_COMPONENTS : ASSISTANT_MARKDOWN_COMPONENTS}
      >
        {msg.content || ""}
      </MarkdownContent>
      {!isUser && msg.payload?.ragSources && (
        <SourceList
          sources={msg.payload.ragSources}
          fallbackNotice={msg.payload.ragFallback}
          traceId={msg.payload.traceId}
        />
      )}
      {!isUser && (msg.payload?.sourceList || msg.payload?.source_list) && (
        <div className="mt-4 pt-3 border-t border-border/30">
          <SourceListCard
            data={msg.payload.sourceList || msg.payload.source_list}
            onSelectItem={onSelectItem}
            selectedId={selectedId}
          />
        </div>
      )}
    </div>
  );
}

function ErrorMessageContent({ msg }: { msg: ChatMessage }) {
  return (
    <div className="flex items-start gap-2.5 text-destructive bg-destructive/5 border border-destructive/20 rounded-xl p-3 w-full animate-in fade-in slide-in-from-bottom-2 duration-200">
      <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
      <div>
        <p className="text-sm font-semibold">请求出错</p>
        <p className="mt-1 text-xs leading-relaxed opacity-90">
          {msg.payload?.message || msg.content}
        </p>
      </div>
    </div>
  );
}

function SourceListMessageContent({ msg, onSelectItem, selectedId }: MessageContentProps) {
  return (
    <SourceListCard
      data={msg.payload || msg.content}
      onSelectItem={onSelectItem}
      selectedId={selectedId}
    />
  );
}

function ChoiceRequestMessageContent({ msg, onSelectChoice }: MessageContentProps) {
  const options: Array<{ id: string; label: string; description?: string }> =
    msg.payload?.options || [];
  if (options.length === 0) return null;

  return (
    <div className="mt-1 rounded-xl border border-amber-300/50 dark:border-amber-700/40 bg-amber-50/40 dark:bg-amber-950/10 p-3">
      <p className="text-xs font-semibold text-amber-800 dark:text-amber-300">
        {msg.payload?.question || "需要你选择一个处理方式："}
      </p>
      <div className="mt-2 flex flex-col gap-1.5">
        {options.map((option) => (
          <button
            key={option.id}
            onClick={() => onSelectChoice(option.id, msg.messageId)}
            className="text-left text-xs px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-800/50 bg-white/60 dark:bg-zinc-900/40 hover:bg-amber-100/60 dark:hover:bg-amber-900/20 transition-colors"
          >
            <span className="font-medium text-amber-900 dark:text-amber-200">{option.label}</span>
            {option.description && (
              <span className="block text-[10px] text-muted-foreground mt-0.5">
                {option.description}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function SourceCardMessageContent({ msg, onSelectItem, selectedId }: MessageContentProps) {
  let item = msg.payload || msg.content;
  if (typeof item === "string") {
    try {
      item = JSON.parse(item);
    } catch {
      item = {};
    }
  }

  const itemId = item?.id || item?.externalId || "source-card-item";
  return (
    <div className="space-y-2.5">
      <SourceSectionHeader toolType="parse_url" />
      <SelectableSourceCard
        item={item}
        itemId={itemId}
        onSelectItem={onSelectItem}
        selectedId={selectedId}
        presentation="single"
      />
    </div>
  );
}

export function ToolStatusMessage({
  msg,
  isStreaming,
}: {
  msg: ChatMessage;
  isStreaming: boolean;
}) {
  const isCompleted = msg.payload?.status === "completed" || !isStreaming;

  return (
    <div className="flex w-full justify-start mb-2 px-2">
      <div className="flex items-center gap-2 rounded-xl border border-border/30 bg-muted/20 px-3 py-1.5 text-xs text-muted-foreground select-none">
        <Wrench className="h-3.5 w-3.5 text-amber-500 shrink-0" />
        <span>
          执行工具:{" "}
          <code className="font-mono bg-muted/60 px-1 py-0.5 rounded text-[11px] border border-border/20">
            {msg.payload?.tool_type || msg.content}
          </code>
        </span>
        <Badge
          variant="outline"
          className={cn(
            "text-[10px] py-0 h-4 px-1.5",
            isCompleted
              ? "text-emerald-500 border-emerald-500/20 bg-emerald-500/5"
              : "text-amber-500 border-amber-500/20 bg-amber-500/5 animate-pulse",
          )}
        >
          {isCompleted ? "已完成" : "运行中"}
        </Badge>
      </div>
    </div>
  );
}

export function SourceListCard({
  data,
  onSelectItem,
  selectedId,
}: {
  data: any;
  onSelectItem: (id: string) => void;
  selectedId: string | null;
}) {
  const items = data?.items || [];
  const toolType = data?.tool_type || "parse_url";

  return (
    <div className="space-y-3">
      <SourceSectionHeader toolType={toolType} />
      <div className="grid gap-2.5">
        {items.map((item: any, index: number) => {
          const itemId = item.id || item.externalId || `item-${index}`;
          return (
            <SelectableSourceCard
              key={itemId}
              item={item}
              itemId={itemId}
              onSelectItem={onSelectItem}
              selectedId={selectedId}
              presentation="list"
              showMetadata
            />
          );
        })}
      </div>
    </div>
  );
}

function SourceSectionHeader({ toolType }: { toolType: string }) {
  const isParsedUrl = toolType === "parse_url";
  return (
    <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
      {isParsedUrl ? (
        <Globe className="h-4 w-4 text-emerald-500" />
      ) : (
        <Sparkles className="h-4 w-4 text-amber-500" />
      )}
      {isParsedUrl ? "解析到以下帖子内容：" : "为您搜索采集到以下主题帖子："}
    </div>
  );
}

function SelectableSourceCard({
  item,
  itemId,
  onSelectItem,
  selectedId,
  presentation,
  showMetadata = false,
}: {
  item: any;
  itemId: string;
  onSelectItem: (id: string) => void;
  selectedId: string | null;
  presentation: "list" | "single";
  showMetadata?: boolean;
}) {
  return (
    <Card
      onClick={() => onSelectItem(itemId)}
      className={cn(
        "cursor-pointer transition-all hover:shadow-sm",
        presentation === "single" && "w-full",
        selectedId === itemId
          ? "border-primary/50 bg-primary/5"
          : "hover:border-muted-foreground/30",
      )}
    >
      <CardContent className={presentation === "list" ? "p-3" : "p-3.5"}>
        <h4 className="mb-1 truncate text-sm font-semibold">
          {item?.title || (presentation === "single" ? "未知标题" : undefined)}
        </h4>
        {item?.summary && (
          <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
            {item.summary}
          </p>
        )}
        {showMetadata && (
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground mb-2 flex-wrap">
            {item?.publishedAt && (
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {item.publishedAt}
              </span>
            )}
            {item?.metrics?.likes && (
              <span className="inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3 text-amber-500" />
                {item.metrics.likes}
              </span>
            )}
            {item?.author && <span>作者：{item.author}</span>}
          </div>
        )}
        <div className="flex items-center justify-between">
          <Badge variant="secondary" className="text-[10px] uppercase">
            {item?.platform || "zhihu"}
          </Badge>
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-primary">
            <FileText className="h-3 w-3" />
            开始创作回答
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
