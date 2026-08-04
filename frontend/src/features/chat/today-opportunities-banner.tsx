import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Sparkles, X } from "lucide-react";
import { fetchOpportunities, startPlan, type Opportunity } from "@/features/knowledge/opportunity-api";
import { Button } from "@/components/ui/button";

function platformBadge(p: string) {
  switch (p.toLowerCase()) {
    case "zhihu": return "知乎";
    case "xiaohongshu": return "小红书";
    default: return p;
  }
}

function OpportunityCard({ opp }: { opp: Opportunity }) {
  const qc = useQueryClient();
  const startPlanMutation = useMutation({
    mutationFn: () => startPlan(opp.id),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["opportunities"] });
      // 广播 planId，chat-panel 监听后展示 TaskPlanCard
      const planId = data?.data?.planId;
      if (planId) {
        window.dispatchEvent(
          new CustomEvent("taskplan:created", { detail: { planId } })
        );
      }
    },
  });

  return (
    <div className="flex flex-col gap-1 border border-border rounded-lg p-2.5 bg-card min-w-[220px] shrink-0">
      <div className="flex items-center gap-1.5">
        <span className="text-[9px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">
          {platformBadge(opp.platform)}
        </span>
        <span className="text-[9px] text-muted-foreground ml-auto">
          热度 {Math.round(opp.hotScore * 100)}
        </span>
      </div>
      <a href={opp.questionUrl} target="_blank" rel="noopener noreferrer"
         className="text-[10px] font-semibold hover:text-primary line-clamp-2">
        {opp.questionTitle}
      </a>
      <div className="flex items-center gap-2 text-[9px] text-muted-foreground">
        <span>匹配 {Math.round(opp.matchScore * 100)}%</span>
        <span>已有 {opp.existingAnswerCount} 回答</span>
      </div>
      <Button
        className="inline-flex items-center justify-center h-6 text-[10px] mt-1 cursor-pointer px-2 rounded bg-slate-700 text-white hover:bg-slate-800"
        onClick={() => startPlanMutation.mutate()}
      >
        {startPlanMutation.isPending ? (
          <><Loader2 className="h-3 w-3 animate-spin mr-1" /> 启动中...</>
        ) : (
          <><Sparkles className="h-3 w-3 mr-1" /> 一键创作</>
        )}
      </Button>
    </div>
  );
}

export function TodayOpportunitiesBanner({ workspaceId = "default" }: { workspaceId?: string }) {
  const [collapsed, setCollapsed] = useState(false);
  const { data, isLoading } = useQuery<Opportunity[]>({
    queryKey: ["opportunities", workspaceId],
    queryFn: () => fetchOpportunities(workspaceId),
    refetchInterval: 60 * 60 * 1000,  // 每小时刷新
  });

  if (collapsed || !data || data.length === 0) {
    return null;
  }

  return (
    <div className="border-b border-border bg-gradient-to-r from-blue-50 to-purple-50 dark:from-blue-950/20 dark:to-purple-950/20 px-4 py-2.5 shrink-0">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          <span className="text-[11px] font-bold">今日内容机会</span>
          <span className="text-[9px] text-muted-foreground">基于热榜与你的兴趣领域</span>
        </div>
        <button onClick={() => setCollapsed(true)} className="text-muted-foreground hover:text-foreground">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex gap-2.5 overflow-x-auto pb-1">
        {isLoading ? (
          <div className="flex items-center gap-2 py-3 text-[10px] text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> 扫描机会中…
          </div>
        ) : (
          data.map((opp) => <OpportunityCard key={opp.id} opp={opp} />)
        )}
      </div>
    </div>
  );
}