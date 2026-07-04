import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowUpRight, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useWorkbenchStore } from "@/store/workbench-store";
import { parseQuestionUrl } from "@/features/workspace/workflow-api";
import { supportedPlatforms } from "@/features/workspace/defaults";
import type { Platform, WorkbenchItem } from "@/types/workflow";

type StatusLevel = "idle" | "running" | "done" | "error";

function StatusDot({ label, status, value }: { label: string; status: StatusLevel; value: string }) {
  const dotClass: Record<StatusLevel, string> = {
    idle: "bg-slate-300",
    running: "bg-blue-500 animate-pulse",
    done: "bg-emerald-500",
    error: "bg-red-500",
  };
  const valueClass: Record<StatusLevel, string> = {
    idle: "text-slate-400",
    running: "text-blue-600",
    done: "text-emerald-600",
    error: "text-red-600",
  };
  return (
    <div className="flex items-center gap-1.5">
      <span className={`h-[6px] w-[6px] rounded-full shrink-0 ${dotClass[status]}`} />
      <span className="text-[11px] font-medium text-slate-500">{label}</span>
      <span className={`text-[11px] font-semibold ${valueClass[status]}`}>{value}</span>
    </div>
  );
}

/** URL 直接导入栏，解析单条问题并加入工作台。 */
export function WorkbenchUrlImportBar() {
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState<Platform>("zhihu");
  const [lastMessage, setLastMessage] = useState("");
  const { addItems } = useWorkbenchStore();

  const importMutation = useMutation({
    mutationFn: () =>
      parseQuestionUrl({ platform, url: url.trim() }),
    onSuccess: (data) => {
      const item: WorkbenchItem = {
        ...data.item,
        platform,
        addedAt: new Date().toISOString(),
        sourcePlatform: platform,
        sourceTopic: "",
        promptConfig: { answerStyle: "", systemPrompt: "", generationPrompt: "" },
        generationStatus: "idle",
      };
      const { added, skipped } = addItems([item]);
      setLastMessage(
        skipped > 0 ? `该问题已在工作台中，已跳过。` : `已加入：${data.item.title}`,
      );
      setUrl("");
    },
    onError: (error: Error) => {
      setLastMessage(error.message);
    },
  });

  const isPending = importMutation.isPending;

  return (
    <div className="border-b border-slate-200 bg-white px-5 py-3">
      <div className="flex items-center gap-2">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && url.trim() && !isPending) {
              importMutation.mutate();
            }
          }}
          placeholder="粘贴知乎问题链接，例如 https://www.zhihu.com/question/..."
          className="h-8 flex-1 rounded-md border-slate-200 bg-white text-[12px] shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
        />
        <Select value={platform} onValueChange={(v) => setPlatform(v as Platform)}>
          <SelectTrigger className="h-8 w-[100px] rounded-md border-slate-200 bg-white text-[12px]">
            <SelectValue placeholder="平台" />
          </SelectTrigger>
          <SelectContent>
            {supportedPlatforms.map((p) => (
              <SelectItem key={p.id} value={p.id} className="text-[12px]">
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          className="h-8 gap-1.5 rounded-md bg-slate-900 px-3.5 text-[12px] font-medium hover:bg-slate-800"
          disabled={!url.trim() || isPending}
          onClick={() => importMutation.mutate()}
        >
          {isPending ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ArrowUpRight className="h-3.5 w-3.5" />
          )}
          {isPending ? "解析中…" : "导入问题"}
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-4">
        <StatusDot
          label="URL 解析"
          status={isPending ? "running" : importMutation.isSuccess ? "done" : importMutation.isError ? "error" : "idle"}
          value={isPending ? "解析中" : importMutation.isSuccess ? "已完成" : "待检查"}
        />
        {lastMessage && (
          <span className="ml-auto text-[11px] text-slate-400">{lastMessage}</span>
        )}
      </div>
    </div>
  );
}
