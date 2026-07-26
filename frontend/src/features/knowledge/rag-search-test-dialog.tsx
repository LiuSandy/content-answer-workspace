import { useState } from "react";
import { Search, Sparkles, CheckCircle2, AlertTriangle, FileText, Layers, RefreshCw } from "lucide-react";
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

export function RagSearchTestDialog({ open, onOpenChange }: RagSearchTestDialogProps) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"normal" | "strict">("normal");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TestRetrievalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await testKnowledgeRetrieval(query.trim(), mode);
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "RAG 检索测试失败，请检查网络或配置");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[85vh] flex flex-col p-6 gap-4">
        <DialogHeader className="space-y-1">
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
        <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3.5">
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
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
            {error}
          </div>
        )}

        <ScrollArea className="flex-1 min-h-[360px] pr-2">
          {!result && !loading && (
            <div className="flex h-64 flex-col items-center justify-center text-center text-muted-foreground gap-2">
              <Layers className="h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm">在上方输入框中输入关键字并点击【测试检索】</p>
              <p className="text-xs text-muted-foreground/70">将展示全链路检索匹配指标与 Agent 注入上下文</p>
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* ── 判定卡片 ── */}
              <div
                className={`rounded-lg border p-4 flex items-start justify-between ${
                  result.hasEvidence
                    ? "border-emerald-500/30 bg-emerald-500/5 dark:bg-emerald-950/20"
                    : "border-amber-500/30 bg-amber-500/5 dark:bg-amber-950/20"
                }`}
              >
                <div className="space-y-1">
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
                      const traceHit = result.traceHits?.find(h => h.document_id === src.documentId || h.citation_label === src.label);
                      return (
                        <div key={idx} className="rounded-lg border bg-card p-3.5 space-y-2 text-xs">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 font-bold text-sm text-indigo-600 dark:text-indigo-400">
                              <span className="rounded bg-indigo-100 dark:bg-indigo-950 px-1.5 py-0.5 text-xs text-indigo-700 dark:text-indigo-300 font-mono">
                                {src.label || `[S${idx + 1}]`}
                              </span>
                              <span>{src.title}</span>
                            </div>
                            {traceHit && (
                              <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                                <span>BM25: {traceHit.bm25_score?.toFixed(2)}</span>
                                <span>向量距: {traceHit.vector_score?.toFixed(2)}</span>
                                <span>RRF: #{traceHit.rank}</span>
                                <Badge variant="secondary" className="font-semibold text-indigo-600 dark:text-indigo-300">
                                  Reranker: {traceHit.rerank_score?.toFixed(2)}
                                </Badge>
                              </div>
                            )}
                          </div>

                          <div className="rounded bg-muted/50 p-2.5 font-mono text-xs whitespace-pre-wrap leading-relaxed text-muted-foreground">
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
