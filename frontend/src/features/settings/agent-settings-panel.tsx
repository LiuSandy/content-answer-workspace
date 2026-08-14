import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AgentSettingsData {
  proactiveSensingEnabled: boolean;
  interestTags: string[];
  pushTimeWindow: { start?: number; end?: number };
  scanIntervalHours: number;
}

async function fetchSettings(): Promise<AgentSettingsData> {
  const res = await fetch("/api/opportunities/agent-settings?workspaceId=default");
  const json = await res.json();
  return json.data || {};
}

async function updateSettings(data: Partial<AgentSettingsData>): Promise<void> {
  await fetch("/api/opportunities/agent-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspaceId: "default", ...data }),
  });
}

export function AgentSettingsPanel() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery<AgentSettingsData>({
    queryKey: ["agent-settings"],
    queryFn: fetchSettings,
  });

  const [tagsInput, setTagsInput] = useState("");
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (data) {
      setEnabled(data.proactiveSensingEnabled ?? true);
      setTagsInput((data.interestTags || []).join(", "));
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: () =>
      updateSettings({
        proactiveSensingEnabled: enabled,
        interestTags: tagsInput.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-settings"] }),
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> 加载…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <label className="text-sm font-medium block mb-1.5">主动感知总开关</label>
        <p className="text-xs text-muted-foreground mb-2">
          开启后每小时自动扫描热榜,推送与你的兴趣领域匹配的机会卡片。
        </p>
        <button
          onClick={() => setEnabled((v) => !v)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            enabled ? "bg-primary" : "bg-muted"
          }`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
              enabled ? "translate-x-5" : "translate-x-0.5"
            }`}
          />
        </button>
        <span className="ml-2 text-xs">{enabled ? "已开启" : "已关闭"}</span>
      </div>

      <div>
        <label className="text-sm font-medium block mb-1.5">感兴趣的领域 Tag</label>
        <p className="text-xs text-muted-foreground mb-2">
          用英文逗号分隔,影响机会匹配度评分。
        </p>
        <input
          type="text"
          value={tagsInput}
          onChange={(e) => setTagsInput(e.target.value)}
          placeholder="AI, 算法, 个人网站"
          className="w-full rounded border border-border bg-background px-3 py-1.5 text-sm"
        />
      </div>

      <Button
        size="sm"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
        className="h-8"
      >
        {mutation.isPending ? (
          <><Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> 保存中…</>
        ) : mutation.isSuccess ? (
          <><Check className="h-3.5 w-3.5 mr-1.5" /> 已保存</>
        ) : (
          "保存配置"
        )}
      </Button>
    </div>
  );
}