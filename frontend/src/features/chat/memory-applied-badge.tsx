import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";

interface MemoriesCountResponse {
  ok: boolean;
  data: { count: number };
}

async function fetchMemoriesCount(workspaceId = "default"): Promise<number> {
  const res = await fetch(`/api/memories?workspaceId=${encodeURIComponent(workspaceId)}`);
  const json = await res.json();
  return Array.isArray(json.data) ? json.data.length : 0;
}

export function MemoryAppliedBadge({ workspaceId = "default" }: { workspaceId?: string }) {
  const { data: count } = useQuery<number>({
    queryKey: ["memories-count", workspaceId],
    queryFn: () => fetchMemoriesCount(workspaceId),
    refetchInterval: 30000,
  });

  if (!count || count === 0) return null;

  return (
    <span
      title={`Agent 已记录 ${count} 条偏好/记忆，对话中会自动应用`}
      className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 font-medium shrink-0"
    >
      <Brain className="h-2.5 w-2.5" />
      已应用 {count} 条记忆
    </span>
  );
}