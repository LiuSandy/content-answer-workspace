import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  BadgeCheck,
  Check,
  ClipboardList,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  ApiError,
  adoptQualitySuggestion,
  listQualityReviews,
  runQualityReview,
  type QualityReviewDocumentStateDTO,
  type QualityReviewRecordDTO,
  type QualitySuggestionDTO,
} from "./quality-review-api";

const DIMENSION_LABELS: Record<string, string> = {
  relevance: "相关性",
  information_density: "信息密度",
  readability: "可读性",
  logic_coherence: "逻辑连贯",
  word_count_compliance: "字数合规",
};

function scoreColor(score: number): string {
  if (score >= 85) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 70) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

function scoreBarColor(score: number): string {
  if (score >= 85) return "bg-emerald-500";
  if (score >= 70) return "bg-amber-500";
  return "bg-red-500";
}

function OverallScore({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex flex-col gap-1 min-w-[120px]">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[10px] font-bold text-muted-foreground">综合评分</span>
          <span className={`text-lg font-bold ${scoreColor(score)}`}>{score}</span>
        </div>
        <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${scoreBarColor(score)}`}
            style={{ width: `${score}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function DimensionBars({ dims }: { dims: Record<string, number> }) {
  return (
    <div className="grid grid-cols-5 gap-2 flex-1">
      {Object.entries(DIMENSION_LABELS).map(([key, label]) => {
        const v = dims[key];
        if (v === undefined) return null;
        return (
          <div key={key} className="flex flex-col gap-1">
            <span className="text-[9px] text-muted-foreground">{label}</span>
            <span className={`text-[11px] font-semibold ${scoreColor(v)}`}>{v}</span>
            <div className="h-1 w-full bg-muted rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${scoreBarColor(v)}`}
                style={{ width: `${Math.min(v, 100)}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface QualityReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  documentId: string | null;
  lockVersion: number;
  // 采纳成功后的文档最新状态（编辑器需刷新内容）
  onAdopted?: (state: QualityReviewDocumentStateDTO) => void;
  // 乐观锁冲突时刷新编辑器，让用户基于最新内容操作
  onConflictRefresh?: () => void;
}

export function QualityReviewDialog({
  open,
  onOpenChange,
  documentId,
  lockVersion,
  onAdopted,
  onConflictRefresh,
}: QualityReviewDialogProps) {
  const queryClient = useQueryClient();
  const [latestLockVersion, setLatestLockVersion] = useState(lockVersion);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setLatestLockVersion(lockVersion);
      setConflictMessage(null);
    }
  }, [open, lockVersion]);

  const {
    data: reviews = [],
    isLoading: isListLoading,
    error: listError,
  } = useQuery<QualityReviewRecordDTO[]>({
    queryKey: ["quality-reviews", documentId],
    queryFn: () => listQualityReviews(documentId!),
    enabled: open && !!documentId,
  });

  const reviewMutation = useMutation({
    mutationFn: () => runQualityReview(documentId!),
    onSuccess: () => {
      setConflictMessage(null);
      queryClient.invalidateQueries({ queryKey: ["quality-reviews", documentId] });
    },
  });

  const adoptMutation = useMutation({
    mutationFn: (params: { reportId: string; suggestionId: string }) =>
      adoptQualitySuggestion(documentId!, {
        ...params,
        expectedLockVersion: latestLockVersion,
      }),
    onSuccess: (state) => {
      setConflictMessage(null);
      setLatestLockVersion(state.lockVersion);
      onAdopted?.(state);
      queryClient.invalidateQueries({ queryKey: ["quality-reviews", documentId] });
      queryClient.invalidateQueries({ queryKey: ["document", state.sourceItemId] });
      queryClient.invalidateQueries({ queryKey: ["versions", documentId] });
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError && err.code === "document_conflict") {
        setConflictMessage(err.message);
        onConflictRefresh?.();
      }
    },
  });

  const handleAdopt = (reportId: string, suggestion: QualitySuggestionDTO) => {
    if (suggestion.adopted || adoptMutation.isPending) return;
    adoptMutation.mutate({ reportId, suggestionId: suggestion.id });
  };

  // 空 / 加载 / 错误态
  let body: React.ReactNode;
  if (reviewMutation.isPending) {
    body = (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground">
        <Loader2 className="h-7 w-7 animate-spin text-indigo-600" />
        <span className="text-xs">AI 正在质检回答内容，请稍候…</span>
      </div>
    );
  } else if (isListLoading) {
    body = (
      <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 加载质检报告…
      </div>
    );
  } else if (listError) {
    body = (
      <div className="flex flex-col items-center gap-3 py-14 text-center">
        <AlertCircle className="h-7 w-7 text-destructive" />
        <p className="text-xs text-destructive">{listError.message}</p>
        <Button variant="outline" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: ["quality-reviews", documentId] })}>
          <RefreshCw className="h-3 w-3" /> 重试
        </Button>
      </div>
    );
  } else if (reviews.length === 0) {
    body = (
      <div className="flex flex-col items-center gap-3 py-14 text-center">
        <ClipboardList className="h-7 w-7 text-muted-foreground" />
        <p className="text-xs text-muted-foreground">还没有质检报告。点击下方按钮对当前内容执行一次质检。</p>
        <Button size="sm" onClick={() => reviewMutation.mutate()} disabled={reviewMutation.isPending}>
          <Sparkles className="h-3.5 w-3.5" /> 开始质检
        </Button>
        {reviewMutation.isError && (
          <p className="text-xs text-destructive">
            {(reviewMutation.error as Error).message || "质检失败，请稍后重试"}
          </p>
        )}
      </div>
    );
  } else {
    body = (
      <div className="flex flex-col gap-4">
        {conflictMessage && (
          <div className="flex items-start gap-2 rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-700 dark:text-amber-400">
            <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            <span>内容已发生变化：{conflictMessage}</span>
          </div>
        )}
        {reviews.map((report) => (
          <ReportCard
            key={report.reportId}
            report={report}
            adopting={adoptMutation.isPending}
            onAdopt={(suggestion) => handleAdopt(report.reportId, suggestion)}
          />
        ))}
      </div>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader className="border-b pb-3">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            质量评审
          </DialogTitle>
          <DialogDescription>
            查看质检报告并逐条采纳修改建议，采纳后生成新版本
          </DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[70vh]">
          <div className="space-y-4 pr-2">{body}</div>
        </ScrollArea>
        {reviews.length > 0 && !reviewMutation.isPending && (
          <div className="flex justify-end border-t pt-3">
            <Button size="sm" onClick={() => reviewMutation.mutate()} disabled={reviewMutation.isPending}>
              {reviewMutation.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
              重新质检
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReportCard({
  report,
  adopting,
  onAdopt,
}: {
  report: QualityReviewRecordDTO;
  adopting: boolean;
  onAdopt: (suggestion: QualitySuggestionDTO) => void;
}) {
  const suggestions = report.suggestions ?? [];
  const createdAt = report.createdAt
    ? new Date(report.createdAt).toLocaleString()
    : null;

  return (
    <div className="rounded-lg border bg-card p-3.5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <OverallScore score={report.overallScore ?? 0} />
        <DimensionBars dims={report.dimensionScores ?? {}} />
      </div>
      {createdAt && <p className="mb-2 text-[10px] text-muted-foreground">评审时间：{createdAt}</p>}
      {report.summary && (
        <p className="mb-3 text-xs text-muted-foreground leading-relaxed">{report.summary}</p>
      )}
      {suggestions.length === 0 ? (
        <p className="text-xs text-muted-foreground">本报告没有可采纳的建议。</p>
      ) : (
        <div className="space-y-2">
          {suggestions.map((sug) => (
            <div key={sug.id} className="flex items-start justify-between gap-3 rounded-md border bg-muted/30 p-2.5">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-1.5">
                  <span className="text-xs font-semibold">{sug.title}</span>
                  <Badge variant="secondary" className="h-4 px-1.5 text-[9px] uppercase shrink-0">
                    {DIMENSION_LABELS[sug.dimension] ?? sug.dimension}
                  </Badge>
                </div>
                {sug.reason && <p className="text-[11px] text-muted-foreground">{sug.reason}</p>}
              </div>
              <Button
                variant={sug.adopted ? "outline" : "default"}
                size="sm"
                className="h-7 px-2.5 text-xs shrink-0"
                disabled={sug.adopted || adopting}
                onClick={() => onAdopt(sug)}
              >
                {sug.adopted ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-emerald-500" /> 已采纳
                  </>
                ) : (
                  <>
                    <BadgeCheck className="h-3.5 w-3.5" /> 采纳
                  </>
                )}
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
