import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Pencil, Check, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { apiGet, apiPost, apiDelete, apiPut } from "@/lib/api";
import { useChatStore } from "@/store/chat-store";
import { useAlertDialog } from "@/hooks/use-alert-dialog";
import { Button } from "@/components/ui/button";
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
  const navigate = useNavigate();
  const { currentChatId, setCurrentChatId } = useChatStore();
  const { confirm } = useAlertDialog();

  const [editingChatId, setEditingChatId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // 获取对话列表
  const { data: chats = [], isLoading } = useQuery<ChatItem[]>({
    queryKey: ["chats"],
    queryFn: () => apiGet("/api/chats"),
  });



  // 重命名对话
  const renameMutation = useMutation({
    mutationFn: ({ chatId, title }: { chatId: string; title: string }) =>
      apiPut(`/api/chats/${chatId}`, { title }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      setEditingChatId(null);
    },
  });

  // 删除对话
  const deleteMutation = useMutation({
    mutationFn: (chatId: string) => apiDelete(`/api/chats/${chatId}`),
    onSuccess: (_, chatId) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (currentChatId === chatId) {
        setCurrentChatId(null);
        navigate("/");
      }
    },
  });

  const handleSave = (chatId: string, oldTitle: string) => {
    const trimmed = editingTitle.trim();
    if (trimmed && trimmed !== oldTitle) {
      renameMutation.mutate({ chatId, title: trimmed });
    } else {
      setEditingChatId(null);
    }
  };

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r bg-card">
      {/* 新建采集按钮 */}
      <div className="p-3">
        <Button className="w-full" onClick={() => navigate("/")}>
          <Plus className="h-4 w-4" />
          开启新对话
        </Button>
      </div>

      {/* 会话列表 */}
      <ScrollArea className="flex-1 px-2 pb-2 [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0">
        {isLoading ? (
          <div className="space-y-2 p-1">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : chats.length === 0 ? (
          <p className="p-4 text-center text-xs text-muted-foreground">暂无历史对话</p>
        ) : (
          <div className="space-y-1 w-full min-w-0">
            {chats.map((chat) => {
              const isEditing = editingChatId === chat.chatId;
              return (
                <div
                  key={chat.chatId}
                  onClick={() => !isEditing && navigate(`/chat/${chat.chatId}`)}
                  className={cn(
                    "group flex cursor-pointer flex-col w-full min-w-0 transition-colors",
                    isEditing
                      ? "rounded-full border border-blue-500 bg-background px-4 py-1.5"
                      : cn(
                          "rounded-lg border p-2.5",
                          currentChatId === chat.chatId
                            ? "border-primary/40 bg-muted"
                            : "border-transparent hover:bg-muted/60",
                        )
                  )}
                >
                  <div className="flex items-center justify-between gap-2 min-w-0 w-full">
                    {isEditing ? (
                      <div className="flex items-center gap-1 w-full min-w-0" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="text"
                          value={editingTitle}
                          onChange={(e) => setEditingTitle(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              handleSave(chat.chatId, chat.title);
                            } else if (e.key === "Escape") {
                              setEditingChatId(null);
                            }
                          }}
                          className="h-6 flex-1 bg-transparent border-none outline-none focus:outline-none p-0 text-sm font-medium leading-snug min-w-0 shadow-none"
                          autoFocus
                          onFocus={(e) => {
                            const val = e.target.value;
                            e.target.setSelectionRange(val.length, val.length);
                          }}
                        />
                        <div className="flex items-center gap-0.5 shrink-0">
                          {/* 确认对号按钮 */}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-emerald-500 hover:text-emerald-600 hover:bg-emerald-500/10"
                                onClick={() => handleSave(chat.chatId, chat.title)}
                              >
                                <Check className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>保存</TooltipContent>
                          </Tooltip>

                          {/* 取消 X 按钮 */}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-muted-foreground hover:text-foreground hover:bg-muted"
                                onClick={() => setEditingChatId(null)}
                              >
                                <X className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>取消</TooltipContent>
                          </Tooltip>
                        </div>
                      </div>
                    ) : (
                      <>
                        <span
                          className="truncate text-sm font-medium leading-snug flex-1"
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            setEditingChatId(chat.chatId);
                            setEditingTitle(chat.title);
                          }}
                        >
                          {chat.title}
                        </span>
                        <div className="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                          {/* 重命名按钮 */}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-muted-foreground hover:text-foreground"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingChatId(chat.chatId);
                                  setEditingTitle(chat.title);
                                }}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent>重命名</TooltipContent>
                          </Tooltip>

                          {/* 删除按钮 */}
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-muted-foreground hover:text-destructive"
                                onClick={async (e) => {
                                  e.stopPropagation();
                                  const confirmed = await confirm({
                                    description: "确定要删除此对话吗？",
                                    variant: "destructive",
                                    confirmText: "删除",
                                  });
                                  if (confirmed) {
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
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </aside>
  );
}
