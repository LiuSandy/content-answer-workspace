export type SubTaskType = "search" | "analyze" | "outline" | "write" | "review";
export type SubTaskStatus = "pending" | "running" | "done" | "failed" | "cancelled";
export type PlanStatus = "pending" | "running" | "done" | "failed" | "interrupted";

export interface SubTaskDTO {
  taskId: string;
  type: SubTaskType;
  description: string;
  dependsOn: string[];
  status: SubTaskStatus;
  result?: string | null;
}

export interface TaskPlanDTO {
  planId: string;
  goal: string;
  status: PlanStatus;
  tasks: SubTaskDTO[];
}

export async function createTaskPlan(goal: string, chatId?: string, workspaceId = "default"): Promise<TaskPlanDTO> {
  const res = await fetch("/api/task-plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, chatId, workspaceId }),
  });
  const json = await res.json();
  if (!json.ok) throw new Error(json.error?.message || "create plan failed");
  return json.data;
}

export async function getTaskPlan(planId: string): Promise<TaskPlanDTO> {
  const res = await fetch(`/api/task-plans/${planId}`);
  const json = await res.json();
  if (!json.ok) throw new Error(json.error?.message || "get plan failed");
  return json.data;
}

export async function retrySubTask(planId: string, taskId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/task-plans/${planId}/tasks/${taskId}/retry`, { method: "POST" });
  const json = await res.json();
  return json.data || { status: "failed" };
}

export async function interruptTaskPlan(planId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/task-plans/${planId}/interrupt`, { method: "POST" });
  const json = await res.json();
  return json.data || { status: "interrupted" };
}

export async function resumeTaskPlan(planId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/task-plans/${planId}/resume`, { method: "POST" });
  const json = await res.json();
  return json.data || { status: "pending" };
}

export async function streamTaskPlan(planId: string): Promise<EventSource> {
  // 用 fetch + ReadableStream 而非 EventSource，因为后者不支持 POST
  return new EventSource(`/api/task-plans/${planId}/stream`);
}