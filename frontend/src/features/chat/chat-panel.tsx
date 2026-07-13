import { useState, useRef, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, Globe, Loader2, Sparkles, AlertCircle, FileText } from "lucide-react";

import { apiGet } from "@/lib/api";
import { streamPost } from "@/lib/sse";
import { useChatStore } from "@/store/chat-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PromptInput } from "@/components/ui/prompt-input";

type Message = {
  messageId: string;
  role: "user" | "assistant" | "tool";
  messageType: "text" | "source_card" | "source_list" | "tool_status" | "error";
  content: string | null;
  payload: any;
  createdAt: string;
};

/**
 * 中间对话面板：多轮消息列表 + 底部输入框。
 *
 * 单独组件，因为对话流是 Chat-first 的核心交互区，
 * 与侧边栏（导航）和编辑面板（创作）在职责上完全正交。
 */
export function ChatPanel() {
  const queryClient = useQueryClient();
  const { currentChatId, setSelectedSourceItemId, selectedSourceItemId } = useChatStore();
  const [inputText, setInputText] = useState("");

  // 流式交互临时状态
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [streamingSourceList, setStreamingSourceList] = useState<any | null>(null);
  const [streamingError, setStreamingError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 获取消息历史
  const { data: messages = [], isLoading } = useQuery<Message[]>({
    queryKey: ["messages", currentChatId],
    queryFn: () => apiGet(`/api/chats/${currentChatId}/messages`),
    enabled: !!currentChatId,
  });

  // 滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, agentStatus]);

  // ── 未选择对话时的欢迎空状态 ──
  if (!currentChatId) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center bg-muted/30 p-8">
        <Card className="max-w-sm border-none bg-card shadow-md">
          <CardContent className="flex flex-col items-center gap-3 p-6 text-center">
            <span className="text-3xl">👋</span>
            <p className="text-sm leading-relaxed text-muted-foreground">
              欢迎使用超级大脑！在下方粘贴知乎、小红书、V2EX 的链接，或输入采集主题开始深度分析。
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── 发送消息 ──
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || isStreaming) return;

    const content = inputText;
    setInputText("");
    setIsStreaming(true);
    setStreamingText("");
    setAgentStatus("发送中...");
    setStreamingSourceList(null);
    setStreamingError(null);

    // 乐观更新：立即追加用户消息到列表
    queryClient.setQueryData<Message[]>(["messages", currentChatId], (prev = []) => [
      ...prev,
      {
        messageId: "temp-user-msg",
        role: "user",
        messageType: "text",
        content,
        payload: null,
        createdAt: new Date().toISOString(),
      },
    ]);

    try {
      await streamPost(`/api/chats/${currentChatId}/messages/stream`, { content }, {
        onEvent: (event, data) => {
          if (event === "agent.status") {
            const statusMap: Record<string, string> = {
              routing_intent: "分析意图...",
              generating: "生成回复中...",
            };
            setAgentStatus(statusMap[data.status] || data.status);
          } else if (event === "tool.started") {
            const toolMap: Record<string, string> = {
              parse_url: "解析链接中...",
              collect: "采集帖子中...",
            };
            setAgentStatus(toolMap[data.tool_type] || `执行工具: ${data.tool_type}`);
          } else if (event === "message.delta") {
            setAgentStatus(null);
            setStreamingText((prev) => prev + data.delta);
          } else if (event === "source.list.completed") {
            setAgentStatus(null);
            setStreamingSourceList(data);
          } else if (event === "run.failed") {
            setAgentStatus(null);
            setStreamingError(data.message || "请求处理失败");
          }
        },
        onError: (err) => {
          setStreamingError(err.message);
          setIsStreaming(false);
          setAgentStatus(null);
        },
      });
    } catch {
      // onError 已处理
    } finally {
      setIsStreaming(false);
      setAgentStatus(null);
      setStreamingText("");
      setStreamingSourceList(null);
      queryClient.invalidateQueries({ queryKey: ["messages", currentChatId] });
    }
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/30">
      {/* ── 消息列表 ── */}
      <ScrollArea className="flex-1 min-h-0 p-4">
        <div className="flex w-full flex-col gap-4 px-2">
          {isLoading ? (
            <div className="space-y-3 py-8">
              <Skeleton className="mx-auto h-16 w-3/4 rounded-xl" />
              <Skeleton className="ml-auto h-10 w-1/2 rounded-xl" />
              <Skeleton className="h-16 w-3/4 rounded-xl" />
            </div>
          ) : (
            messages.map((msg) => (
              <MessageBubble
                key={msg.messageId}
                msg={msg}
                onSelectItem={setSelectedSourceItemId}
                selectedId={selectedSourceItemId}
              />
            ))
          )}

          {/* 实时流式响应 */}
          {isStreaming && (
            <div className="flex justify-start">
              <Card className="max-w-[85%] border-none bg-card shadow-sm">
                <CardContent className="p-3.5">
                  {agentStatus && (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      {agentStatus}
                    </div>
                  )}
                  {streamingText && (
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{streamingText}</p>
                  )}
                  {streamingSourceList && (
                    <SourceListCard
                      data={streamingSourceList}
                      onSelectItem={setSelectedSourceItemId}
                      selectedId={selectedSourceItemId}
                    />
                  )}
                  {streamingError && (
                    <div className="flex items-start gap-2 text-destructive">
                      <AlertCircle className="h-5 w-5 shrink-0" />
                      <div>
                        <p className="text-sm font-semibold">请求出错</p>
                        <p className="mt-1 text-xs">{streamingError}</p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* ── 底部输入框 ── */}
      <div className="shrink-0 border-t bg-card p-4 fixed-bottom-input-area">
        <PromptInput
          value={inputText}
          onChange={setInputText}
          onSubmit={() => handleSendMessage()}
          placeholder="粘贴链接或输入采集主题..."
          disabled={isStreaming}
        />
      </div>
    </div>
  );
}

// ── 消息气泡 ──────────────────────────────────────────────────────

/** 单条消息渲染；按角色区分气泡方向和样式 */
function MessageBubble({
  msg,
  onSelectItem,
  selectedId,
}: {
  msg: Message;
  onSelectItem: (id: string) => void;
  selectedId: string | null;
}) {
  const isUser = msg.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <Card
        className={cn(
          "max-w-[85%] border-none shadow-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-card",
        )}
      >
        <CardContent className="p-3.5">
          {msg.messageType === "text" && (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
          )}
          {msg.messageType === "error" && (
            <div className="flex items-start gap-2 text-destructive">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <div>
                <p className="text-sm font-semibold">请求出错</p>
                <p className="mt-1 text-xs">{msg.payload?.message || msg.content}</p>
              </div>
            </div>
          )}
          {msg.messageType === "source_list" && (
            <SourceListCard
              data={msg.payload || msg.content}
              onSelectItem={onSelectItem}
              selectedId={selectedId}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── 采集结果卡片列表 ──────────────────────────────────────────────

/** 渲染 Agent 返回的帖子列表；点击帖子选中后，右侧编辑面板加载对应文档 */
function SourceListCard({
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
      <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
        {toolType === "parse_url" ? (
          <>
            <Globe className="h-4 w-4 text-emerald-500" />
            解析到以下帖子内容：
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4 text-amber-500" />
            为您搜索采集到以下主题帖子：
          </>
        )}
      </div>

      <div className="grid gap-2.5">
        {items.map((item: any, idx: number) => {
          const itemId = item.id || item.externalId || `item-${idx}`;
          return (
            <Card
              key={itemId}
              onClick={() => onSelectItem(itemId)}
              className={cn(
                "cursor-pointer transition-all hover:shadow-sm",
                selectedId === itemId ? "border-primary/50 bg-primary/5" : "hover:border-muted-foreground/30",
              )}
            >
              <CardContent className="p-3">
                <h4 className="mb-1 truncate text-sm font-semibold">{item.title}</h4>
                {item.summary && (
                  <p className="mb-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {item.summary}
                  </p>
                )}
                <div className="flex items-center justify-between">
                  <Badge variant="secondary" className="text-[10px] uppercase">
                    {item.platform || "zhihu"}
                  </Badge>
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-primary">
                    <FileText className="h-3 w-3" />
                    开始创作回答
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
