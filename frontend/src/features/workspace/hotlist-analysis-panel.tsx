import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { AnalysisStatus, HotlistAnalysisResult } from "@/types/workflow";

import { parseAnalysisResult } from "./hotlist-analysis-parser";
import { streamAgentChat } from "./workflow-api";

export function HotlistAnalysisPanel() {
  const [status, setStatus] = useState<AnalysisStatus>({ type: "idle" });
  const navigate = useNavigate();
  const setTopicDraft = useWorkspaceStore((s) => s.setTopicDraft);

  async function handleAnalyze() {
    setStatus({ type: "loading" });
    try {
      await streamAgentChat(
        {
          sessionId: "hotlist_analysis",
          message: "请分析当前热榜，给出内容策略建议",
        },
        {
          onDone: (data) => {
            const parsed = parseAnalysisResult(data.reply);
            if (parsed) {
              setStatus({ type: "success", data: parsed });
            } else {
              setStatus({ type: "error", raw: data.reply });
            }
          },
          onError: (msg) => {
            setStatus({ type: "error", raw: `请求失败：${msg}` });
          },
        },
      );
    } catch {
      setStatus({ type: "error", raw: "请求失败，请重试" });
    }
  }

  function handleAdopt(rec: HotlistAnalysisResult["recommendations"][0]) {
    setTopicDraft({ name: rec.topic, keywords: rec.keywords });
    navigate("/collect");
  }

  return (
    <div className="w-96 border-l flex flex-col shrink-0">
      <div className="p-3 border-b flex items-center justify-between">
        <span className="text-sm font-medium">AI 分析</span>
        <button
          className="text-sm px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
          disabled={status.type === "loading"}
          onClick={handleAnalyze}
        >
          {status.type === "loading" ? "分析中…" : "开始分析"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {status.type === "idle" && <AnalysisEmpty />}
        {status.type === "loading" && <AnalysisLoading />}
        {status.type === "error" && <AnalysisError raw={status.raw} />}
        {status.type === "success" && (
          <AnalysisResult data={status.data} onAdopt={handleAdopt} />
        )}
      </div>
    </div>
  );
}

function AnalysisEmpty() {
  return (
    <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
      点击「开始分析」生成内容策略建议
    </div>
  );
}

function AnalysisLoading() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="h-16 bg-muted/50 rounded animate-pulse" />
      ))}
    </div>
  );
}

function AnalysisError({ raw }: { raw: string }) {
  return (
    <div className="space-y-2">
      <p className="text-sm text-destructive font-medium">解析失败，原始内容：</p>
      <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-words bg-muted/30 rounded p-2 max-h-64 overflow-y-auto">
        {raw}
      </pre>
    </div>
  );
}

function AnalysisResult({
  data,
  onAdopt,
}: {
  data: HotlistAnalysisResult;
  onAdopt: (rec: HotlistAnalysisResult["recommendations"][0]) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium text-muted-foreground mb-1">受众情绪基调</p>
        <p className="text-sm">{data.audienceMood}</p>
      </div>

      {data.topicDistribution.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">话题分布</p>
          <div className="space-y-1">
            {data.topicDistribution.map((d) => (
              <div key={d.field} className="flex items-center gap-2 text-sm">
                <span className="font-medium">{d.field}</span>
                <span className="text-muted-foreground">×{d.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.contentOpportunities.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">内容机会</p>
          <div className="space-y-2">
            {data.contentOpportunities.map((op) => (
              <div key={op.direction} className="border rounded p-2 space-y-0.5">
                <p className="text-sm font-medium">{op.direction}</p>
                <p className="text-xs text-muted-foreground">{op.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {data.recommendations.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">推荐选题</p>
          <div className="space-y-2">
            {data.recommendations.map((rec, i) => (
              <RecommendationCard key={rec.topic} rec={rec} index={i} onAdopt={onAdopt} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RecommendationCard({
  rec,
  index,
  onAdopt,
}: {
  rec: HotlistAnalysisResult["recommendations"][0];
  index: number;
  onAdopt: (rec: HotlistAnalysisResult["recommendations"][0]) => void;
}) {
  return (
    <div className="border rounded p-3 space-y-1">
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium">
          {index + 1}. {rec.topic}
        </span>
        <button
          className="text-xs px-2 py-1 border rounded hover:bg-muted shrink-0"
          onClick={() => onAdopt(rec)}
        >
          采用 →
        </button>
      </div>
      <p className="text-xs text-muted-foreground">{rec.reason}</p>
      {rec.keywords.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {rec.keywords.map((kw) => (
            <span key={kw} className="text-xs bg-muted px-1.5 py-0.5 rounded">
              {kw}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
