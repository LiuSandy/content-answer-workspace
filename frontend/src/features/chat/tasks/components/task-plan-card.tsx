import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCw, CheckCircle2, XCircle, Clock, Play, Pause } from "lucide-react";
import {
  getTaskPlan,
  retrySubTask,
  interruptTaskPlan,
  resumeTaskPlan,
  type TaskPlanDTO,
  type SubTaskDTO,
} from "../api/task-plan-api";

const TYPE_LABEL: Record<string, string> = {
  search: "搜索",
  analyze: "分析",
  outline: "提纲",
  write: "写作",
  review: "自评",
};

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "done":
      return <CheckCircle2 className="h-3 w-3 text-emerald-500" />;
    case "running":
      return <Loader2 className="h-3 w-3 animate-spin text-blue-500" />;
    case "failed":
      return <XCircle className="h-3 w-3 text-red-500" />;
    default:
      return <Clock className="h-3 w-3 text-muted-foreground" />;
  }
}

function TaskNode({ task }: { task: SubTaskDTO }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="flex flex-col gap-0.5 border-l-2 pl-2 ml-1 border-border">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 text-left hover:bg-muted/50 rounded px-1"
      >
        <StatusIcon status={task.status} />
        <span className="text-[9px] font-mono text-muted-foreground">{task.taskId}</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-semibold">
          {TYPE_LABEL[task.type] || task.type}
        </span>
        <span className="text-[10px] text-foreground/80 line-clamp-1">{task.description}</span>
      </button>
      {expanded && task.result && (
        <pre className="text-[9px] text-muted-foreground bg-muted/30 rounded p-2 mt-0.5 whitespace-pre-wrap overflow-x-auto">
          {task.result}
        </pre>
      )}
    </div>
  );
}

export function TaskPlanCard({ planId }: { planId: string }) {
  const qc = useQueryClient();
  const { data: plan, isLoading } = useQuery<TaskPlanDTO>({
    queryKey: ["task-plan", planId],
    queryFn: () => getTaskPlan(planId),
    refetchInterval: (q) => {
      const st = q.state.data?.status;
      return st === "running" || st === "pending" ? 1000 : false;
    },
  });

  const [retrying, setRetrying] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 text-[10px] text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> 加载 TaskPlan…
      </div>
    );
  }
  if (!plan) return null;

  const failedTask = plan.tasks.find((t) => t.status === "failed");
  const isRunning = plan.status === "running" || plan.status === "pending";

  const handleInterrupt = async () => {
    setBusy(true);
    await interruptTaskPlan(plan.planId);
    qc.invalidateQueries({ queryKey: ["task-plan", planId] });
    setBusy(false);
  };

  const handleResume = async () => {
    setBusy(true);
    await resumeTaskPlan(plan.planId);
    qc.invalidateQueries({ queryKey: ["task-plan", planId] });
    setBusy(false);
  };

  return (
    <div className="border border-border rounded-lg p-2.5 my-2 bg-muted/20">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-[10px] font-bold">TaskPlan</span>
        <span
          className={`text-[9px] px-1.5 py-0.5 rounded ${
            plan.status === "done"
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
              : plan.status === "failed"
                ? "bg-red-100 text-red-700"
                : plan.status === "running"
                  ? "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400"
                  : plan.status === "interrupted"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-muted text-muted-foreground"
          }`}
        >
          {plan.status}
        </span>
        <span className="text-[10px] text-muted-foreground ml-auto">{plan.goal}</span>
      </div>
      <div className="space-y-1">
        {plan.tasks.map((t) => (
          <TaskNode key={t.taskId} task={t} />
        ))}
      </div>
      <div className="flex items-center gap-3 mt-2">
        {isRunning && (
          <button
            disabled={busy}
            className="inline-flex items-center gap-1 text-[10px] text-amber-600 hover:underline"
            onClick={handleInterrupt}
          >
            <Pause className="h-3 w-3" /> 中断
          </button>
        )}
        {plan.status === "interrupted" && (
          <button
            disabled={busy}
            className="inline-flex items-center gap-1 text-[10px] text-emerald-600 hover:underline"
            onClick={handleResume}
          >
            <Play className="h-3 w-3" /> 恢复执行
          </button>
        )}
        {failedTask && planId && (
          <button
            className="inline-flex items-center gap-1 text-[10px] text-primary hover:underline"
            onClick={async () => {
              setRetrying(failedTask.taskId);
              await retrySubTask(plan.planId, failedTask.taskId);
              setRetrying(null);
            }}
          >
            <RotateCw
              className={`h-3 w-3 ${retrying === failedTask.taskId ? "animate-spin" : ""}`}
            />
            重试 {failedTask.taskId}
          </button>
        )}
      </div>
    </div>
  );
}
