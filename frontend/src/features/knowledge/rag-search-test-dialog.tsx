import { useState } from "react";
import {
  Search,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Layers,
  RefreshCw,
  Workflow,
  MinusCircle,
  XCircle,
  Ban,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { testKnowledgeRetrieval, type TestRetrievalResponse } from "./knowledge-api";

interface RagSearchTestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** 流程阶段状态的图标与配色映射；单独抽出避免在 JSX 里堆嵌套三元 */
const STEP_STATUS_META: Record<
  string,
  { icon: typeof CheckCircle2; className: string; label: string }
> = {
  ok: { icon: CheckCircle2, className: "text-emerald-600 dark:text-emerald-400", label: "成功" },
  skipped: { icon: MinusCircle, className: "text-zinc-400", label: "跳过" },
  error: { icon: XCircle, className: "text-red-500", label: "失败" },
  blocked: { icon: Ban, className: "text-amber-600 dark:text-amber-400", label: "中止" },
};

/** 检索流程执行时间线；展示每个阶段的状态、耗时与说明（标题由外层折叠按钮承担） */
function PipelineTimeline({ steps }: { steps: NonNullable<TestRetrievalResponse["pipelineSteps"]> }) {
  return (
    <div className="rounded-lg border bg-card divide-y">
      {steps.map((step, idx) => {
        const meta = STEP_STATUS_META[step.status] ?? STEP_STATUS_META.ok;
        const Icon = meta.icon;
        return (
          <div key={`${step.step}-${idx}`} className="flex items-start gap-3 px-3.5 py-2">
            <div className="flex items-center gap-2 w-36 shrink-0">
              <Icon className={`h-4 w-4 shrink-0 ${meta.className}`} />
              <span className="text-xs font-semibold">{step.title}</span>
            </div>
            <p className="flex-1 text-xs text-muted-foreground leading-relaxed break-all">
              {step.detail}
            </p>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground/70 mt-0.5">
              {step.durationMs} ms
            </span>
          </div>
        );
      })}
    </div>
  );
}

export function RagSearchTestDialog({ open, onOpenChange }: RagSearchTestDialogProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"normal" | "strict">("normal");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TestRetrievalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 流程明细默认折叠，节省结果区空间；每次新检索后重置为收起
  const [stepsExpanded, setStepsExpanded] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setStepsExpanded(false);
    try {
      const data = await testKnowledgeRetrieval(query.trim(), mode);
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "RAG 检索测试失败，请检查网络或配置");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      // 关闭时清空状态，避免下次打开残留上一次的结果
      setResult(null);
      setError(null);
      setLoading(false);
      setStepsExpanded(false);
    }
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col p-6 gap-4 overflow-hidden">
        <DialogHeader className="shrink-0 space-y-1">
          <DialogTitle className="flex items-center gap-2 text-lg font-bold">
            <Sparkles className="h-5 w-5 text-indigo-500" />
            RAG 检索效果测试
            <Badge variant="outline" className="ml-2 text-xs font-normal">
              100% 同源引擎测试
            </Badge>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            输入关键字或提问测试底层 RAG 检索引擎（查询改写 → BM25 + 向量双路 → RRF 融合 → LLM 重排打分 → 阈值判定）。
          </DialogDescription>
        </DialogHeader>

        {/* ── 检索控制栏 ── */}
        <div className="shrink-0 flex flex-col gap-3 rounded-lg border bg-muted/30 p-3.5">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="输入关键字测试（如：find 命令按时间查找、文件权限 644、LRU 缓存...）"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                className="pl-9 h-9 text-sm"
              />
            </div>
            <Button onClick={handleSearch} disabled={loading || !query.trim()} className="h-9 px-4 gap-1.5 font-semibold">
              {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
              {loading ? "检索中..." : "测试检索"}
            </Button>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <span className="font-medium text-muted-foreground">检索模式:</span>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name="rag-test-mode"
                checked={mode === "normal"}
                onChange={() => setMode("normal")}
                className="accent-indigo-600"
              />
              <span>普通模式 (normal)</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name="rag-test-mode"
                checked={mode === "strict"}
                onChange={() => setMode("strict")}
                className="accent-indigo-600"
              />
              <span>仅私有资料模式 (strict - 强拒答)</span>
            </label>
          </div>
        </div>

        {/* ── 结果展示区 ── */}
        {error && (
          <div className="shrink-0 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
            {error}
          </div>
        )}

        {/* min-h-0 是 flex 布局下可滚动的关键：否则内容会把容器撑开导致整体溢出 */}
        <ScrollArea className="flex-1 min-h-0 pr-2">
          {!result && !loading && (
            <div className="flex h-64 flex-col items-center justify-center text-center text-muted-foreground gap-2">
              <Layers className="h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm">在上方输入框中输入关键字并点击【测试检索】</p>
              <p className="text-xs text-muted-foreground/70">将展示检索流程明细、命中片段与 Agent 注入上下文</p>
            </div>
          )}

          {result && (
            <div className="space-y-4 pb-2">
              {/* ── 判定 + 流程明细合并卡片（流程可折叠，默认收起省空间） ── */}
              <div
                className={`rounded-lg border ${
                  result.hasEvidence
                    ? "border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-950/20"
                    : "border-amber-500/30 bg-amber-500/5 dark:bg-amber-950/20"
                }`}
              >
                <div className="p-4 space-y-1">
                  <div className="flex items-center gap-2">
                    {result.hasEvidence ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                    )}
                    <span className="font-bold text-sm">
                      {result.hasEvidence ? "已命中强相关证据（has_evidence = true）" : "私有资料证据不足（has_evidence = false）"}
                    </span>
                    <Badge variant={result.hasEvidence ? "default" : "outline"} className="text-[10px]">
                      模式: {mode}
                    </Badge>
                  </div>
                  {result.rewrittenQuery && (
                    <p className="text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">改写后查询词: </span>
                      {result.rewrittenQuery}
                    </p>
                  )}
                  {result.fallbackReason && (
                    <p className="text-xs text-amber-700 dark:text-amber-300">
                      降级提示: {result.fallbackReason}
                    </p>
                  )}
                </div>

                {/* 流程明细折叠区 */}
                {result.pipelineSteps && result.pipelineSteps.length > 0 && (
                  <div className="border-t border-inherit">
                    <button
                      onClick={() => setStepsExpanded((v) => !v)}
                      className="w-full flex items-center gap-1.5 px-4 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <Workflow className="h-3.5 w-3.5" />
                      <span className="font-semibold">检索流程执行明细</span>
                      <span className="text-muted-foreground/70">
                        {result.pipelineSteps.length} 个阶段 · 总耗时{" "}
                        {(result.pipelineSteps.reduce((sum, s) => sum + s.durationMs, 0) / 1000).toFixed(1)}s
                      </span>
                      {stepsExpanded ? (
                        <ChevronUp className="h-3.5 w-3.5 ml-auto" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 ml-auto" />
                      )}
                    </button>
                    {stepsExpanded && (
                      <div className="px-3 pb-3">
                        <PipelineTimeline steps={result.pipelineSteps} />
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ── 命中的源文件与切片 ── */}
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <FileText className="h-3.5 w-3.5" />
                  匹配命中的源文件与片段 ({result.sources?.length || 0})
                </h4>

                {(!result.sources || result.sources.length === 0) ? (
                  <div className="rounded-md border p-4 text-center text-xs text-muted-foreground">
                    未检索到任何符合条件的切片
                  </div>
                ) : (
                  <div className="space-y-3">
                    {result.sources.map((src, idx) => {
                      // 只按引用标签精确匹配：按 document_id 匹配会让同文档的
                      // 多个片段全部命中第一条 trace，展示出完全相同的评分
                      const traceHit = result.traceHits?.find(
                        (h) => h.citation_label != null && h.citation_label === src.label,
                      );
                      return (
                        <div key={src.label || idx} className="rounded-lg border bg-card p-3.5 space-y-2 text-xs">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0 space-y-1">
                              <div className="flex items-center gap-2 font-bold text-sm text-indigo-600 dark:text-indigo-400">
                                <span className="rounded bg-indigo-100 dark:bg-indigo-950 px-1.5 py-0.5 text-xs text-indigo-700 dark:text-indigo-300 font-mono">
                                  {src.label || `[S${idx + 1}]`}
                                </span>
                                <span className="truncate">{src.title}</span>
                              </div>
                              {/* 章节路径：告诉用户该片段来自文档的哪个位置 */}
                              {src.headingPath && (
                                <p className="text-[11px] text-muted-foreground truncate">
                                  📍 所在章节: {src.headingPath}
                                </p>
                              )}
                            </div>
                            {traceHit && (
                              <div className="flex items-center gap-2 shrink-0 font-mono text-[11px] text-muted-foreground">
                                <span title="该路召回来源">
                                  {traceHit.retrieval_source === "hybrid"
                                    ? "双路命中"
                                    : traceHit.retrieval_source === "bm25"
                                      ? "BM25 命中"
                                      : "向量命中"}
                                </span>
                                <span>BM25: {traceHit.bm25_score?.toFixed(2)}</span>
                                <span>向量: {traceHit.vector_score?.toFixed(2)}</span>
                                <span>RRF: #{traceHit.rank}</span>
                                <Badge variant="secondary" className="font-semibold text-indigo-600 dark:text-indigo-300">
                                  重排: {traceHit.rerank_score != null ? traceHit.rerank_score.toFixed(2) : "—"}
                                </Badge>
                              </div>
                            )}
                          </div>

                          <div className="rounded bg-muted/50 p-2.5 font-mono text-xs whitespace-pre-wrap leading-relaxed text-muted-foreground max-h-40 overflow-y-auto">
                            {src.text || traceHit?.context_snapshot || "(无切片预览)"}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ── Agent 注入的上下文 Preview ── */}
              {result.contextText && (
                <div className="space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Agent System Prompt 实际注入上下文 (Grounded Context)
                  </h4>
                  <div className="rounded-lg border bg-slate-950 p-3 font-mono text-xs text-slate-100 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                    {result.contextText}
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
