import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { apiGet } from "@/lib/api";

export interface QualityDimensionScore {
  relevance: number;
  information_density: number;
  readability: number;
  logic_coherence: number;
  word_count_compliance: number;
}

export interface QualityScore {
  id: string;
  iteration: number;
  overallScore: number;
  dimensions: QualityDimensionScore;
  weaknessSummary: string | null;
  refinementInstruction: string | null;
  converged: boolean;
  createdAt: string;
}

const DIMENSION_LABELS: { key: keyof QualityDimensionScore; label: string }[] = [
  { key: "relevance", label: "相关性" },
  { key: "information_density", label: "信息密度" },
  { key: "readability", label: "可读性" },
  { key: "logic_coherence", label: "逻辑连贯" },
  { key: "word_count_compliance", label: "字数合规" },
];

function scoreColor(score: number): string {
  if (score >= 0.75) return "text-emerald-600";
  if (score >= 0.6) return "text-amber-600";
  return "text-red-600";
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
      <div
        className={`h-full rounded-full transition-all ${
          value >= 0.75 ? "bg-emerald-500" : value >= 0.6 ? "bg-amber-500" : "bg-red-500"
        }`}
        style={{ width: `${Math.round(value * 100)}%` }}
      />
    </div>
  );
}

function RadarDimensions({ dims }: { dims: QualityDimensionScore }) {
  // 纯 SVG 雷达图（不引入额外图表库），5 维
  const size = 120;
  const center = size / 2;
  const radius = 45;
  const values = DIMENSION_LABELS.map((d) => dims[d.key] ?? 0);
  const points = values.map((v, i) => {
    const angle = (Math.PI * 2 * i) / 5 - Math.PI / 2;
    const r = radius * v;
    return [center + r * Math.cos(angle), center + r * Math.sin(angle)];
  });
  const polygonPoints = points.map((p) => p.join(",")).join(" ");

  return (
    <svg width={size} height={size} className="shrink-0">
      {[0.25, 0.5, 0.75, 1].map((r) => (
        <polygon
          key={r}
          points={Array.from({ length: 5 }, (_, i) => {
            const a = (Math.PI * 2 * i) / 5 - Math.PI / 2;
            return `${center + radius * r * Math.cos(a)},${center + radius * r * Math.sin(a)}`;
          }).join(" ")}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={0.5}
        />
      ))}
      <polygon points={polygonPoints} fill="rgba(59,130,246,0.2)" stroke="#3b82f6" strokeWidth={1.5} />
      {points.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={2} fill="#3b82f6" />
      ))}
    </svg>
  );
}

export function QualityScorePanel({ documentId }: { documentId: string | null }) {
  const { data, isLoading } = useQuery<QualityScore[]>({
    queryKey: ["quality-scores", documentId],
    queryFn: () => apiGet<QualityScore[]>(`/api/documents/${documentId}/quality-scores`),
    enabled: !!documentId,
  });

  if (!documentId) return null;
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 text-[10px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> 加载质量评分…
      </div>
    );
  }
  if (!data || data.length === 0) return null;

  const latest = data[data.length - 1];

  return (
    <div className="border-t border-border px-4 py-3 bg-muted/30">
      <div className="flex items-center gap-4">
        {/* 综合评分进度条 */}
        <div className="flex flex-col gap-1 min-w-[160px]">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[10px] font-bold text-muted-foreground">综合评分</span>
            <span className={`text-lg font-bold ${scoreColor(latest.overallScore)}`}>
              {latest.overallScore.toFixed(2)}
            </span>
          </div>
          <ProgressBar value={latest.overallScore} />
          <span className="text-[9px] text-muted-foreground">
            已自评 {data.length} 轮，{latest.converged ? "已收敛" : "未收敛"}
          </span>
        </div>

        {/* 雷达图 */}
        <RadarDimensions dims={latest.dimensions} />

        {/* 维度细分明细 */}
        <div className="flex-1 grid grid-cols-5 gap-1.5">
          {DIMENSION_LABELS.map((d) => {
            const v = latest.dimensions[d.key] ?? 0;
            return (
              <div key={d.key} className="flex flex-col gap-0.5">
                <span className="text-[9px] text-muted-foreground">{d.label}</span>
                <span className={`text-[10px] font-semibold ${scoreColor(v)}`}>{v.toFixed(2)}</span>
                <ProgressBar value={v} />
              </div>
            );
          })}
        </div>

        {/* 修正历程按钮 */}
        {data.length > 1 && (
          <details className="shrink-0">
            <summary className="cursor-pointer text-[10px] text-primary hover:underline">
              查看修正历程（{data.length} 轮）
            </summary>
            <div className="mt-2 space-y-1 max-h-[200px] overflow-y-auto">
              {data.map((s) => (
                <div key={s.id} className="text-[9px] border border-border rounded p-1.5">
                  <div className="flex justify-between">
                    <span className="font-semibold">第 {s.iteration} 轮</span>
                    <span className={scoreColor(s.overallScore)}>{s.overallScore.toFixed(2)}</span>
                  </div>
                  {s.weaknessSummary && <p className="mt-0.5 text-muted-foreground">{s.weaknessSummary}</p>}
                  {s.refinementInstruction && (
                    <p className="mt-0.5 text-amber-700 dark:text-amber-400">指令：{s.refinementInstruction}</p>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}