import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, ClipboardList, Loader2, RefreshCw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { listQualityReviews, type QualityReviewRecordDTO } from "./quality-review-api";

const DIMENSION_LABELS: Record<string, string> = {
  relevance: "相关性",
  informationDensity: "信息密度",
  readability: "可读性",
  logicCoherence: "逻辑连贯",
  wordCountCompliance: "字数合规",
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
    <div className="flex min-w-[120px] flex-col gap-1">
      <div className="flex items-baseline gap-1.5">
        <span className="text-[10px] font-bold text-muted-foreground">综合评分</span>
        <span className={`text-lg font-bold ${scoreColor(score)}`}>{score}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full ${scoreBarColor(score)}`} style={{ width: `${Math.min(score, 100)}%` }} />
      </div>
    </div>
  );
}

function DimensionBars({ dimensions }: { dimensions: Record<string, number> }) {
  return (
    <div className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-5">
      {Object.entries(DIMENSION_LABELS).map(([key, label]) => {
        const score = dimensions[key];
        if (score === undefined) return null;
        return (
          <div key={key} className="flex flex-col gap-1">
            <span className="text-[9px] text-muted-foreground">{label}</span>
            <span className={`text-[11px] font-semibold ${scoreColor(score)}`}>{score}</span>
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div className={`h-full rounded-full ${scoreBarColor(score)}`} style={{ width: `${Math.min(score, 100)}%` }} />
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
}

export function QualityReviewDialog({ open, onOpenChange, documentId }: QualityReviewDialogProps) {
  const queryClient = useQueryClient();
  const {
    data: reviews = [],
    isLoading,
    error,
  } = useQuery<QualityReviewRecordDTO[]>({
    queryKey: ["quality-reviews", documentId],
    queryFn: () => listQualityReviews(documentId!),
    enabled: open && !!documentId,
  });
  const currentReview = reviews[0];

  let body: React.ReactNode;
  if (isLoading) {
    body = (
      <div className="flex items-center justify-center gap-2 py-16 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 加载自动评审报告…
      </div>
    );
  } else if (error) {
    body = (
      <div className="flex flex-col items-center gap-3 py-14 text-center">
        <AlertCircle className="h-7 w-7 text-destructive" />
        <p className="text-xs text-destructive">{error.message}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => queryClient.invalidateQueries({ queryKey: ["quality-reviews", documentId] })}
        >
          <RefreshCw className="h-3 w-3" /> 重试
        </Button>
      </div>
    );
  } else if (!currentReview) {
    body = (
      <div className="flex flex-col items-center gap-3 py-14 text-center">
        <ClipboardList className="h-7 w-7 text-muted-foreground" />
        <p className="text-xs text-muted-foreground">本次创作暂无自动评审报告。</p>
      </div>
    );
  } else if (currentReview.reviewStatus === "failed") {
    body = (
      <div className="flex flex-col items-center gap-3 py-14 text-center">
        <AlertCircle className="h-7 w-7 text-amber-500" />
        <p className="text-sm font-medium">内容已生成，但自动评审失败</p>
        <p className="text-xs text-muted-foreground">你仍可继续编辑当前内容。</p>
      </div>
    );
  } else {
    body = <ReportCard report={currentReview} />;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader className="border-b pb-3">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            自动质量评审
          </DialogTitle>
          <DialogDescription>查看本次创作完成后生成的只读评审结果</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[70vh]">
          <div className="pr-2">{body}</div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

export function ReportCard({ report }: { report: QualityReviewRecordDTO }) {
  const issues = report.issues ?? [];
  const suggestions = report.suggestions ?? [];
  const rounds = report.rounds ?? [];

  return (
    <div className="space-y-4 rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {typeof report.overallScore === "number" && <OverallScore score={report.overallScore} />}
        <DimensionBars dimensions={report.dimensionScores ?? {}} />
        <Badge variant={report.passed ? "default" : "secondary"} className="shrink-0">
          {report.passed ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
          {report.passed ? "已达标" : "未达标"}
        </Badge>
      </div>

      <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span>评审轮数：{report.iterations}</span>
        <span>选中轮次：第 {report.selectedIteration} 轮</span>
        {report.createdAt && <span>评审时间：{new Date(report.createdAt).toLocaleString()}</span>}
      </div>

      {report.iterations === 3 && !report.passed && (
        <div className="rounded-md border border-amber-300/50 bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
          已完成 3 轮评审，当前为三轮中评分最高的结果
        </div>
      )}

      {report.summary && <p className="text-xs leading-relaxed text-muted-foreground">{report.summary}</p>}

      {rounds.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-xs font-semibold">评审历程</h4>
          <div className="flex flex-wrap gap-2">
            {rounds.map((round) => (
              <Badge key={round.iteration} variant={round.iteration === report.selectedIteration ? "default" : "outline"}>
                第 {round.iteration} 轮 · {round.overallScore} 分 · {round.passed ? "达标" : "未达标"}
              </Badge>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h4 className="text-xs font-semibold">发现的问题</h4>
        {issues.length === 0 ? (
          <p className="text-xs text-muted-foreground">未发现需要说明的问题。</p>
        ) : (
          <ul className="space-y-2">
            {issues.map((issue, index) => (
              <li key={`${issue.description}-${index}`} className="rounded-md border bg-muted/30 p-2.5 text-xs">
                <Badge variant="outline" className="mr-2 h-4 px-1.5 text-[9px]">
                  {issue.severity === "major" ? "主要" : "次要"}
                </Badge>
                {issue.description}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <h4 className="text-xs font-semibold">优化建议</h4>
        {suggestions.length === 0 ? (
          <p className="text-xs text-muted-foreground">暂无优化建议。</p>
        ) : (
          <ul className="list-disc space-y-1.5 pl-5 text-xs text-muted-foreground">
            {suggestions.map((suggestion, index) => <li key={`${suggestion}-${index}`}>{suggestion}</li>)}
          </ul>
        )}
      </section>
    </div>
  );
}
