import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, AlertTriangle, Check, X, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface UserMemoryDTO {
  id: string;
  memoryType: "explicit" | "implicit" | "work_pattern";
  content: string;
  confidence: number;
  source?: string | null;
  status: string;
  evidence?: string | null;
  createdAt: string;
  activationCount: number;
}

async function fetchMemories(workspaceId = "default"): Promise<UserMemoryDTO[]> {
  const res = await fetch(`/api/memories?workspaceId=${encodeURIComponent(workspaceId)}`);
  const json = await res.json();
  return json.data || [];
}

async function deleteMemory(id: string, workspaceId = "default") {
  await fetch(`/api/memories/${id}?workspaceId=${encodeURIComponent(workspaceId)}`, { method: "DELETE" });
}

async function clearAllMemories(workspaceId = "default") {
  await fetch(`/api/memories?workspaceId=${encodeURIComponent(workspaceId)}`, { method: "DELETE" });
}

const TYPE_LABEL: Record<string, { label: string; color: string }> = {
  explicit: { label: "显式记忆", color: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400" },
  implicit: { label: "隐式偏好", color: "bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-400" },
  work_pattern: { label: "工作习惯", color: "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400" },
};

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  pending_confirmation: { label: "待确认", color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-400" },
  rejected: { label: "已拒绝", color: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400" },
};

export function MemoryPanel({ workspaceId = "default" }: { workspaceId?: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<UserMemoryDTO[]>({
    queryKey: ["memories", workspaceId],
    queryFn: () => fetchMemories(workspaceId),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteMemory(id, workspaceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories", workspaceId] }),
  });

  const clearMutation = useMutation({
    mutationFn: () => clearAllMemories(workspaceId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories", workspaceId] }),
  });

  // R5 生命周期
  async function act(id: string, action: "confirm" | "reject") {
    await fetch(`/api/memories/${id}/${action}`, { method: "POST" });
    qc.invalidateQueries({ queryKey: ["memories", workspaceId] });
  }

  const [newContent, setNewContent] = useState("");
  const createMutation = useMutation({
    mutationFn: async (content: string) => {
      await fetch("/api/memories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, memoryType: "explicit", workspaceId }),
      });
    },
    onSuccess: () => {
      setNewContent("");
      qc.invalidateQueries({ queryKey: ["memories", workspaceId] });
    },
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
        <span className="text-sm font-bold">我的记忆</span>
        <div className="flex gap-2">
          {data && data.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="h-7 text-[11px] px-2.5">
                  <Trash2 className="h-3 w-3 mr-1" /> 全部清空
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>清空全部记忆</AlertDialogTitle>
                  <AlertDialogDescription>
                    此操作不可恢复。所有偏好、隐式学习与工作习惯记录将被删除。
                    Agent 后续将不再记得你的偏好，直到你再次告知或其重新学习。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>取消</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => clearMutation.mutate()}
                    className="bg-red-600 hover:bg-red-700 text-white"
                  >
                    确认清空
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      {/* R5 手动创建 */}
      <div className="px-4 py-2 border-b border-border shrink-0">
        <div className="flex gap-1.5">
          <input
            className="flex-1 h-7 text-[11px] px-2 rounded border border-border bg-background"
            placeholder="添加显式记忆，如：用户偏好简洁风格"
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newContent.trim()) {
                createMutation.mutate(newContent.trim());
              }
            }}
          />
          <Button
            size="sm"
            className="h-7 text-[11px] px-2 shrink-0"
            disabled={!newContent.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate(newContent.trim())}
          >
            <Plus className="h-3 w-3 mr-0.5" /> 添加
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" /> 加载…
          </div>
        ) : !data || data.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <AlertTriangle className="h-6 w-6 mb-2 opacity-50" />
            <p className="text-xs">尚无记忆条目</p>
            <p className="text-[10px] mt-1">在对话中告知偏好，Agent 会自动记录</p>
          </div>
        ) : (
          data.map((m) => (
            <div key={m.id} className="border border-border rounded p-2.5 bg-card">
              <div className="flex items-center gap-1.5 mb-1">
                <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold ${TYPE_LABEL[m.memoryType]?.color || ""}`}>
                  {TYPE_LABEL[m.memoryType]?.label || m.memoryType}
                </span>
                {m.status !== "active" && STATUS_LABEL[m.status] && (
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold ${STATUS_LABEL[m.status].color}`}>
                    {STATUS_LABEL[m.status].label}
                  </span>
                )}
                <span className="text-[9px] text-muted-foreground ml-auto">
                  置信度 {Math.round(m.confidence * 100)}%
                </span>
                {m.status === "pending_confirmation" && (
                  <div className="flex gap-0.5">
                    <button
                      onClick={() => act(m.id, "confirm")}
                      className="text-green-500 hover:text-green-700"
                      title="确认"
                    >
                      <Check className="h-3 w-3" />
                    </button>
                    <button
                      onClick={() => act(m.id, "reject")}
                      className="text-red-400 hover:text-red-700"
                      title="拒绝"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )}
                <button
                  onClick={() => deleteMutation.mutate(m.id)}
                  className="text-muted-foreground hover:text-red-500"
                  title="删除"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
              <p className="text-[11px] leading-relaxed text-foreground">{m.content}</p>
              {m.evidence && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <p className="text-[9px] text-muted-foreground mt-0.5 cursor-default italic">
                      证据：{m.evidence.length > 40 ? m.evidence.slice(0, 40) + "…" : m.evidence}
                    </p>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="max-w-64 text-[10px]">
                    {m.evidence}
                  </TooltipContent>
                </Tooltip>
              )}
              <div className="text-[9px] text-muted-foreground mt-1 flex gap-2">
                <span>激活 {m.activationCount} 次</span>
                {m.source && <span>来自 {m.source}</span>}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
