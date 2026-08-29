/**
 * 发布配置分区；管理测试模式开关和 CTA 文本，因为这两个字段共同决定内容发布形态。
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useSettings, useUpdatePublish } from "./use-settings";

export function PublishSettings() {
  const { data: settings, isLoading } = useSettings();
  const update = useUpdatePublish();

  const [testMode, setTestMode] = useState(true);
  const [officialAccountName, setOfficialAccountName] = useState("");
  const [ctaText, setCtaText] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setTestMode(settings.publish.testMode);
    setOfficialAccountName(settings.publish.officialAccountName);
    setCtaText(settings.publish.ctaText);
  }, [settings]);

  async function handleSave() {
    await update.mutateAsync({ testMode, officialAccountName, ctaText });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  const resolvedCta = ctaText.replace("{{OFFICIAL_ACCOUNT_NAME}}", officialAccountName);

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between rounded-lg border px-4 py-3">
        <div>
          <p className="text-sm font-medium">测试模式</p>
          <p className="text-[11px] text-muted-foreground mt-0.5">开启时不追加公众号 CTA 文本</p>
        </div>
        <Switch checked={testMode} onCheckedChange={setTestMode} />
      </div>

      <div className="space-y-1.5">
        <Label>公众号名称</Label>
        <Input
          value={officialAccountName}
          onChange={(e) => setOfficialAccountName(e.target.value)}
          placeholder="你的公众号"
        />
      </div>

      <div className="space-y-1.5">
        <Label>CTA 文本模版</Label>
        <Textarea
          value={ctaText}
          onChange={(e) => setCtaText(e.target.value)}
          rows={3}
          placeholder="更多专题内容，欢迎关注公众号：{{OFFICIAL_ACCOUNT_NAME}}"
        />
        <p className="text-[11px] text-muted-foreground">
          支持 {"{{OFFICIAL_ACCOUNT_NAME}}"} 占位符
        </p>
      </div>

      {!testMode && officialAccountName && (
        <div className="rounded-md border bg-muted/40 px-3 py-2">
          <p className="text-[11px] text-muted-foreground mb-1">预览（正式模式）：</p>
          <p className="text-sm">{resolvedCta}</p>
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={update.isPending}>
          {update.isPending ? "保存中…" : "保存"}
        </Button>
        {saved && <span className="text-sm text-green-600">已保存 ✓</span>}
        {update.isError && (
          <span className="text-sm text-destructive">{(update.error as Error)?.message}</span>
        )}
      </div>
    </div>
  );
}
