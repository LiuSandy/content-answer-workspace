import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2, AlertTriangle } from "lucide-react";
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

export interface UserMemoryDTO {
  id: string;
  memoryType: "explicit" | "implicit" | "work_pattern";
  content: string;
  confidence: number;
  source?: string | null;
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

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border">
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
                <span className="text-[9px] text-muted-foreground ml-auto">
                  置信度 {Math.round(m.confidence * 100)}%
                </span>
                <button
                  onClick={() => deleteMutation.mutate(m.id)}
                  className="text-muted-foreground hover:text-red-500"
                  title="删除"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
              <p className="text-[11px] leading-relaxed text-foreground">{m.content}</p>
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