import { useQuery } from "@tanstack/react-query";
import { Brain } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface MemoryDTO {
  id: string;
  memoryType: string;
  content: string;
  evidence?: string | null;
  status: string;
}

async function fetchMemories(workspaceId = "default"): Promise<MemoryDTO[]> {
  const res = await fetch(`/api/memories?workspaceId=${encodeURIComponent(workspaceId)}`);
  const json = await res.json();
  return (json.data || []).filter((m: MemoryDTO) => m.status === "active");
}

const TYPE_LABEL: Record<string, string> = {
  explicit: "显式记忆",
  implicit: "隐式偏好",
  work_pattern: "工作习惯",
};

export function MemoryAppliedBadge({ workspaceId = "default" }: { workspaceId?: string }) {
  const { data: active } = useQuery<MemoryDTO[]>({
    queryKey: ["memories-active", workspaceId],
    queryFn: () => fetchMemories(workspaceId),
    refetchInterval: 30000,
  });

  const count = active?.length || 0;
  if (count === 0) return null;

  const preview = (active || [])
    .slice(0, 3)
    .map(
      (m) =>
        `${TYPE_LABEL[m.memoryType] || m.memoryType}: ${m.content}${m.evidence ? ` (证据: ${m.evidence.length > 30 ? m.evidence.slice(0, 30) + "…" : m.evidence})` : ""}`,
    )
    .join("\n");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 font-medium shrink-0 cursor-default">
          <Brain className="h-2.5 w-2.5" />
          已应用 {count} 条记忆
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-72 text-[10px] whitespace-pre-line">
        {preview}
        {count > 3 && `\n…等 ${count - 3} 条`}
      </TooltipContent>
    </Tooltip>
  );
}
