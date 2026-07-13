import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus, Trash2 } from "lucide-react";

import { apiGet, apiPost, apiDelete } from "@/lib/api";
import { useChatStore } from "@/store/chat-store";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type ChatItem = {
  chatId: string;
  title: string;
  createdAt: string;
};

/**
 * 左侧会话侧边栏：新建采集入口 + 历史会话列表。
 *
 * 单独成组件，因为它是全局持久存在的导航区，状态（当前会话）与右侧工作区解耦。
 */
export function ChatSidebar() {
  const queryClient = useQueryClient();
  const { currentChatId, setCurrentChatId } = useChatStore();

  // 获取对话列表
  const { data: chats = [], isLoading } = useQuery<ChatItem[]>({
    queryKey: ["chats"],
    queryFn: () => apiGet("/api/chats"),
  });

  // 创建新对话
  const createMutation = useMutation({
    mutationFn: () => apiPost<{ chatId: string; title: string }>("/api/chats", { title: "新对话" }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      setCurrentChatId(data.chatId);
    },
  });

  // 删除对话
  const deleteMutation = useMutation({
    mutationFn: (chatId: string) => apiDelete(`/api/chats/${chatId}`),
    onSuccess: (_, chatId) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (currentChatId === chatId) {
        setCurrentChatId(null);
      }
    },
  });

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r bg-card">
      {/* 新建采集按钮 */}
      <div className="p-3">
        <Button className="w-full" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
          <Plus className="h-4 w-4" />
          新建采集
        </Button>
      </div>

      {/* 会话列表 */}
      <ScrollArea className="flex-1 px-2 pb-2">
        {isLoading ? (
          <div className="space-y-2 p-1">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : chats.length === 0 ? (
          <p className="p-4 text-center text-xs text-muted-foreground">暂无历史对话</p>
        ) : (
          <div className="space-y-1">
            {chats.map((chat) => (
              <div
                key={chat.chatId}
                onClick={() => setCurrentChatId(chat.chatId)}
                className={cn(
                  "group flex cursor-pointer flex-col gap-1.5 rounded-lg border p-2.5 transition-colors",
                  currentChatId === chat.chatId
                    ? "border-primary/40 bg-muted"
                    : "border-transparent hover:bg-muted/60",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="line-clamp-2 text-sm font-medium leading-snug">{chat.title}</span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm("确定要删除此对话吗？")) {
                            deleteMutation.mutate(chat.chatId);
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>删除对话</TooltipContent>
                  </Tooltip>
                </div>
                <div className="flex items-center gap-1.5">
                  <MessageSquare className="h-3 w-3 text-muted-foreground" />
                  <Badge variant="secondary" className="text-[10px]">
                    未采集
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
}
