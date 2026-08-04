import { useState } from "react";
import { Users, Loader2, XCircle, CheckCircle2, Clock } from "lucide-react";

export interface AgentStatus {
  name: string;
  status: string;
  message?: string;
  resultPreview?: string;
}

export interface MultiAgentRunResult {
  runId: string;
  status: string;
  agents: AgentStatus[];
  finalContent?: string;
}

const AGENT_LABEL: Record<string, string> = {
  orchestrator: "Orchestrator 编排",
  research: "Research 调研",
  writing: "Writing 写作",
  review: "Review 自评",
  memory: "Memory 记忆",
};

function AgentRow({ agent }: { agent: AgentStatus }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="flex flex-col gap-0.5 border-l-2 pl-2 ml-1 border-border">
      <button
        onClick={() => agent.resultPreview && setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-left hover:bg-muted/50 rounded px-1"
      >
        {agent.status === "done" ? (
          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
        ) : agent.status === "failed" ? (
          <XCircle className="h-3 w-3 text-red-500" />
        ) : agent.status === "running" ? (
          <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
        ) : (
          <Clock className="h-3 w-3 text-muted-foreground" />
        )}
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 font-semibold">
          {AGENT_LABEL[agent.name] || agent.name}
        </span>
        <span className="text-[10px] text-muted-foreground">{agent.status}</span>
      </button>
      {expanded && agent.resultPreview && (
        <pre className="text-[9px] text-muted-foreground bg-muted/30 rounded p-2 mt-0.5 whitespace-pre-wrap overflow-x-auto">
          {agent.resultPreview}
        </pre>
      )}
    </div>
  );
}

/**
 * Agent 协作执行状态卡片。
 * 不再自带输入框——目标由主对话输入框提供（goal prop），
 * 本组件只负责展示 5 个子 Agent 的执行进度与最终结果。
 */
export function AgentWorkspacePanel({
  goal,
  running,
  result,
}: {
  goal?: string;
  running: boolean;
  result: MultiAgentRunResult | null;
}) {
  const [collapsed, setCollapsed] = useState(false);

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="flex items-center gap-1.5 text-[10px] text-violet-600 dark:text-violet-400 hover:underline shrink-0"
      >
        <Users className="h-3 w-3" /> 展开 Agent 协作
      </button>
    );
  }

  return (
    <div className="border border-violet-200/60 dark:border-violet-900/40 rounded-lg p-2.5 my-2 bg-violet-50/40 dark:bg-violet-950/10">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Users className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
        <span className="text-[10px] font-bold">Agent 协作</span>
        {goal && (
          <span className="text-[9px] text-muted-foreground truncate flex-1">
            目标：{goal}
          </span>
        )}
        <button
          onClick={() => setCollapsed(true)}
          className="text-muted-foreground hover:text-foreground text-[10px] px-1 ml-auto"
          title="收起"
        >
          ✕
        </button>
      </div>
      {running && (
        <div className="flex items-center gap-2 py-1 text-[10px] text-violet-600 dark:text-violet-400">
          <Loader2 className="h-3 w-3 animate-spin" /> 5 个子 Agent 执行中，通常需 1-3 分钟…
        </div>
      )}
      {result && (
        <div className="space-y-1">
          {result.agents.map((a) => (
            <AgentRow key={a.name} agent={a} />
          ))}
          {result.finalContent && (
            <div className="text-[10px] text-foreground/80 bg-muted/40 rounded p-2 mt-1 line-clamp-4">
              {result.finalContent}
            </div>
          )}
        </div>
      )}
    </div>
  );
}