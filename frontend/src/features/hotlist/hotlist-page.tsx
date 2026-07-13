import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Flame, MessageSquarePlus, ExternalLink, RefreshCw, Loader2 } from "lucide-react";
import { apiGet, apiPost } from "@/lib/api";
import { useChatStore } from "@/store/chat-store";

type HotlistItem = {
  rank: number;
  title: string;
  url: string;
  thumbnailUrl: string;
  summary: string;
  heat: string;
};

type HotlistResponse = {
  items: HotlistItem[];
  fetchedAt: string;
};

export function HotlistPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { setCurrentChatId } = useChatStore();

  const { data, isLoading, isRefetching, refetch, error } = useQuery<HotlistResponse>({
    queryKey: ["hotlist"],
    queryFn: () => apiGet("/api/hotlist"),
  });

  const createChatMutation = useMutation({
    mutationFn: (topicTitle: string) =>
      apiPost<{ chatId: string; title: string }>("/api/chats", {
        title: `分析热点：${topicTitle.slice(0, 15)}`,
      }),
    onSuccess: (chatData, topicTitle) => {
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      // 切换到新创建的对话
      setCurrentChatId(chatData.chatId);
      // 跳转到 Chat 工作区首页，并可以通过 query param 或 session 传递初始提示词
      navigate("/", { state: { initialMessage: `分析热点帖：${topicTitle}` } });
    },
  });

  const items = data?.items || [];

  return (
    <div className="flex-1 flex flex-col h-full bg-zinc-50 dark:bg-zinc-950 overflow-hidden">
      {/* 头部 */}
      <div className="p-6 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex justify-between items-center shrink-0">
        <div>
          <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
            <Flame className="w-5 h-5 text-red-500 animate-pulse" />
            实时热榜分析
          </h2>
          <p className="text-xs text-zinc-500 mt-1">
            聚合知乎平台实时热度最高的内容，点击可用其一键开启 AI 回答编写流程。
          </p>
        </div>

        <button
          onClick={() => refetch()}
          disabled={isLoading || isRefetching}
          className="p-2 border border-zinc-200 dark:border-zinc-800 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50 text-zinc-700 dark:text-zinc-300"
          title="刷新热榜"
        >
          <RefreshCw className={`w-4 h-4 ${(isLoading || isRefetching) ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* 列表区 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {isLoading ? (
          <div className="flex justify-center items-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-500 border border-red-200 dark:border-red-800 rounded-xl bg-red-50/50 dark:bg-red-950/20 max-w-lg mx-auto mt-10">
            <h4 className="font-semibold text-sm">热榜数据获取失败</h4>
            <p className="text-xs mt-1 text-zinc-500">{(error as any).message}</p>
          </div>
        ) : items.length === 0 ? (
          <div className="text-center text-xs text-zinc-500 py-10">暂无热榜数据</div>
        ) : (
          <div className="grid gap-4 max-w-4xl mx-auto">
            {items.map((item) => (
              <div
                key={item.rank}
                className="p-4 rounded-xl border border-zinc-200/60 dark:border-zinc-800/80 bg-white dark:bg-zinc-900 hover:shadow-sm transition-all flex gap-4"
              >
                {/* 排名序号 */}
                <div className="flex flex-col items-center justify-center min-w-[32px] h-[32px] rounded-lg bg-zinc-100 dark:bg-zinc-800 shrink-0">
                  <span className={`text-sm font-black ${
                    item.rank <= 3 ? "text-amber-500" : "text-zinc-400"
                  }`}>
                    {item.rank}
                  </span>
                </div>

                {/* 文本内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-4 mb-1">
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug hover:text-indigo-600 transition-colors">
                      {item.title}
                    </h3>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 px-2 py-0.5 rounded font-bold flex items-center gap-0.5">
                        <Flame className="w-3 h-3 shrink-0" />
                        {item.heat}
                      </span>
                    </div>
                  </div>

                  <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed mb-3">
                    {item.summary}
                  </p>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => createChatMutation.mutate(item.title)}
                      disabled={createChatMutation.isPending}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all flex items-center gap-1.5"
                    >
                      {createChatMutation.isPending ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <MessageSquarePlus className="w-3.5 h-3.5" />
                      )}
                      使用此热点新建对话
                    </button>

                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 flex items-center gap-1 transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      在知乎打开
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
