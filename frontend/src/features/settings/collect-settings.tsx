/**
 * 采集默认值分区；管理平台、上限、排序模式等采集参数，因为这些字段都影响每次采集行为。
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useSettings, useUpdateCollect } from "./use-settings";

const PLATFORMS = ["zhihu", "xiaohongshu"];
const SORT_MODE_OPTIONS = [
  { value: "latest", label: "最新" },
  { value: "answer_count", label: "回答数" },
  { value: "created", label: "创建时间" },
];

export function CollectSettings() {
  const { data: settings, isLoading } = useSettings();
  const update = useUpdateCollect();

  const [defaultPlatform, setDefaultPlatform] = useState("zhihu");
  const [maxPushCount, setMaxPushCount] = useState(10);
  const [sortModes, setSortModes] = useState<string[]>(["latest", "answer_count"]);
  const [skipAnswerGeneration, setSkipAnswerGeneration] = useState(false);
  const [userAgent, setUserAgent] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setDefaultPlatform(settings.collect.defaultPlatform);
    setMaxPushCount(settings.collect.maxPushCount);
    setSortModes(settings.collect.sortModes);
    setSkipAnswerGeneration(settings.collect.skipAnswerGeneration);
    setUserAgent(settings.collect.userAgent);
  }, [settings]);

  function toggleSortMode(mode: string) {
    setSortModes((prev) =>
      prev.includes(mode) ? prev.filter((m) => m !== mode) : [...prev, mode],
    );
  }

  async function handleSave() {
    await update.mutateAsync({
      defaultPlatform,
      maxPushCount,
      sortModes,
      skipAnswerGeneration,
      userAgent,
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>默认平台</Label>
          <Select value={defaultPlatform} onValueChange={setDefaultPlatform}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLATFORMS.map((p) => (
                <SelectItem key={p} value={p}>{p}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>单次采集上限</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={maxPushCount}
            onChange={(e) => setMaxPushCount(Number(e.target.value))}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>排序模式</Label>
        <div className="flex gap-2">
          {SORT_MODE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggleSortMode(opt.value)}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                sortModes.includes(opt.value)
                  ? "bg-slate-900 text-white border-slate-900"
                  : "hover:bg-muted"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-lg border px-4 py-3">
        <div>
          <p className="text-sm font-medium">跳过 AI 生成</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">采集后不自动生成回答</p>
        </div>
        <Switch checked={skipAnswerGeneration} onCheckedChange={setSkipAnswerGeneration} />
      </div>

      <button
        type="button"
        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "▾" : "▸"} 高级选项
      </button>

      {showAdvanced && (
        <div className="space-y-1.5">
          <Label>User-Agent</Label>
          <Input
            value={userAgent}
            onChange={(e) => setUserAgent(e.target.value)}
            className="font-mono text-xs"
          />
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={update.isPending}>
          {update.isPending ? "保存中…" : "保存"}
        </Button>
        {saved && <span className="text-sm text-green-600">已保存 ✓</span>}
        {update.isError && (
          <span className="text-sm text-destructive">
            {(update.error as Error)?.message}
          </span>
        )}
      </div>
    </div>
  );
}
