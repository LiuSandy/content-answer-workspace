/**
 * LLM 配置分区；集中管理 Base URL、模型名称和 API Key，因为这三者都属于 LLM 接入参数。
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSettings, useUpdateLlm } from "./use-settings";

const BASE_URL_PRESETS = [
  { label: "智谱 AI（GLM）", value: "https://open.bigmodel.cn/api/paas/v4/" },
  { label: "DeepSeek", value: "https://api.deepseek.com/v1/" },
  { label: "OpenAI 官方", value: "https://api.openai.com/v1/" },
  { label: "本地 Ollama", value: "http://localhost:11434/v1/" },
];

export function LlmSettings() {
  const { data: settings, isLoading } = useSettings();
  const update = useUpdateLlm();

  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setBaseUrl(settings.llm.baseUrl);
    setModel(settings.llm.model);
    setApiKey("");
  }, [settings]);

  async function handleSave() {
    await update.mutateAsync({
      baseUrl,
      model,
      ...(apiKey ? { apiKey } : {}),
    });
    setSaved(true);
    setApiKey("");
    setTimeout(() => setSaved(false), 2000);
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label>Base URL</Label>
        <div className="flex gap-2">
          <Input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 font-mono text-sm"
          />
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          {BASE_URL_PRESETS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setBaseUrl(p.value)}
              className="rounded-full border px-3 py-0.5 text-xs hover:bg-muted transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>模型名称</Label>
        <Input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          placeholder="GLM-4.7 / deepseek-chat / gpt-4o"
          className="font-mono text-sm"
        />
      </div>

      <div className="space-y-1.5">
        <Label>API Key</Label>
        <Input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={settings?.llm.apiKey ?? "留空则不更新"}
          className="font-mono text-sm"
        />
        <p className="text-[11px] text-muted-foreground">
          当前：{settings?.llm.apiKey}，留空则不修改已有 Key
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={update.isPending}>
          {update.isPending ? "保存中…" : "保存"}
        </Button>
        {saved && <span className="text-sm text-green-600">已保存 ✓</span>}
        {update.isError && (
          <span className="text-sm text-destructive">{(update.error as Error)?.message}</span>
        )}
      </div>

      <p className="text-xs text-amber-600 bg-amber-50 rounded-md px-3 py-2 border border-amber-200">
        ⚠️ 修改 API Key 或 Base URL 后需点击「重启后端」使变更生效。
      </p>
    </div>
  );
}
