import React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";

interface RetrievalHit {
  chunkId: string;
  retrievalSource: string;
  rank: number;
  bm25Score?: number;
  vectorScore?: number;
  rrfScore?: number;
  rerankScore?: number;
  includedInContext: boolean;
  citationLabel?: string;
}

interface RetrievalTrace {
  id: string;
  originalQuery: string;
  rewrittenQuery?: string;
  ragDecision: boolean;
  decisionReason?: string;
  mode: string;
  fallbackReason?: string;
  latencyMs?: number;
  embeddingModel?: string;
  rerankerModel?: string;
  hits: RetrievalHit[];
}

interface RetrievalTraceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  traceId?: string | null;
  traceData?: any; // fallback for inline data
}

const sourceColor = (src: string) => {
  if (src === "bm25") return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
  if (src === "vector")
    return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300";
  if (src === "reranked")
    return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300";
  return "bg-muted text-muted-foreground";
};

export const RetrievalTraceDialog: React.FC<RetrievalTraceDialogProps> = ({
  open,
  onOpenChange,
  traceId,
  traceData,
}) => {
  const {
    data: fetchedTrace,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["retrieval-trace", traceId],
    queryFn: async () => {
      const res = await apiGet<{ ok: boolean; data: RetrievalTrace }>(
        `/api/retrieval-traces/${traceId}?debug=true`,
      );
      return res.data;
    },
    enabled: open && !!traceId,
  });

  const trace: RetrievalTrace | undefined =
    fetchedTrace ?? (traceData as RetrievalTrace | undefined);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[680px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            🔍 检索调试日志 (Retrieval Trace)
            <Badge variant="outline">Debug Mode</Badge>
          </DialogTitle>
        </DialogHeader>

        {isLoading && (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        )}

        {error && !traceData && (
          <div className="text-xs text-destructive p-3 bg-destructive/10 rounded-md">
            加载 Trace 失败，请确认 Debug 模式已开启
          </div>
        )}

        {trace && (
          <div className="space-y-4 text-xs">
            {/* 基础信息 */}
            <div className="grid grid-cols-3 gap-2 p-3 bg-muted/40 rounded-md">
              <div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-0.5">
                  RAG 决策
                </div>
                <Badge
                  variant={trace.ragDecision ? "default" : "secondary"}
                  className="text-[10px]"
                >
                  {trace.ragDecision ? "需要检索" : "跳过检索"}
                </Badge>
              </div>
              <div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-0.5">
                  检索模式
                </div>
                <Badge variant="outline" className="text-[10px]">
                  {trace.mode}
                </Badge>
              </div>
              {trace.latencyMs != null && (
                <div>
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-0.5">
                    耗时
                  </div>
                  <span className="font-mono font-semibold">{trace.latencyMs}ms</span>
                </div>
              )}
              {trace.embeddingModel && (
                <div className="col-span-2">
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-0.5">
                    Embedding
                  </div>
                  <span className="font-mono text-[10px]">{trace.embeddingModel}</span>
                </div>
              )}
              {trace.rerankerModel && (
                <div>
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-0.5">
                    Reranker
                  </div>
                  <span className="font-mono text-[10px]">{trace.rerankerModel}</span>
                </div>
              )}
            </div>

            {/* 查询信息 */}
            <div className="space-y-1.5">
              <div className="text-[9px] text-muted-foreground uppercase tracking-wide">
                原始查询
              </div>
              <div className="p-2 bg-muted/30 rounded">{trace.originalQuery}</div>
              {trace.rewrittenQuery && (
                <>
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wide mt-2">
                    改写查询
                  </div>
                  <div className="p-2 bg-primary/5 border border-primary/20 rounded">
                    {trace.rewrittenQuery}
                  </div>
                </>
              )}
            </div>

            {/* 决策 / 降级原因 */}
            {trace.decisionReason && (
              <div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-1">
                  决策原因
                </div>
                <p className="text-muted-foreground">{trace.decisionReason}</p>
              </div>
            )}
            {trace.fallbackReason && (
              <div className="p-2 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800/40 rounded text-amber-700 dark:text-amber-300">
                ⚠️ 降级原因：{trace.fallbackReason}
              </div>
            )}

            {/* 命中列表 */}
            {trace.hits && trace.hits.length > 0 && (
              <div>
                <div className="text-[9px] text-muted-foreground uppercase tracking-wide mb-2">
                  检索命中（{trace.hits.length} 条）
                </div>
                <div className="space-y-1">
                  {trace.hits.map((hit, idx) => (
                    <div
                      key={idx}
                      className={`p-2 rounded border flex items-center gap-2 text-[10px] ${
                        hit.includedInContext
                          ? "border-primary/30 bg-primary/5"
                          : "border-border/40 bg-muted/20 opacity-60"
                      }`}
                    >
                      <span
                        className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-medium ${sourceColor(hit.retrievalSource)}`}
                      >
                        {hit.retrievalSource}
                      </span>
                      <span className="font-mono text-[9px] text-muted-foreground">
                        #{hit.rank}
                      </span>
                      {hit.citationLabel && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                          {hit.citationLabel}
                        </Badge>
                      )}
                      <div className="ml-auto flex gap-2 text-[9px] text-muted-foreground font-mono">
                        {hit.bm25Score != null && <span>BM25:{hit.bm25Score.toFixed(3)}</span>}
                        {hit.vectorScore != null && <span>Vec:{hit.vectorScore.toFixed(3)}</span>}
                        {hit.rrfScore != null && <span>RRF:{hit.rrfScore.toFixed(4)}</span>}
                        {hit.rerankScore != null && (
                          <span className="text-green-600 dark:text-green-400">
                            Rank:{hit.rerankScore.toFixed(3)}
                          </span>
                        )}
                      </div>
                      {hit.includedInContext && (
                        <span className="text-[9px] text-primary font-semibold">✓</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!trace && !isLoading && !error && (
          <div className="my-2 p-3 bg-muted font-mono text-xs overflow-auto max-h-[350px] rounded border">
            <pre>
              {JSON.stringify(traceData || { message: "No trace data available" }, null, 2)}
            </pre>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
