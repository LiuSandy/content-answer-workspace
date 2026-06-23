/**
 * 默认提示词分区；管理全局 System Prompt、回答风格和生成提示词，因为这三者共同决定 AI 输出风格。
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useSettings, useUpdatePrompts } from "./use-settings";

export function PromptsSettings() {
  const { data: settings, isLoading } = useSettings();
  const update = useUpdatePrompts();

  const [systemPrompt, setSystemPrompt] = useState("");
  const [answerStyle, setAnswerStyle] = useState("");
  const [generationPrompt, setGenerationPrompt] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!settings) return;
    setSystemPrompt(settings.prompts.systemPrompt);
    setAnswerStyle(settings.prompts.answerStyle);
    setGenerationPrompt(settings.prompts.generationPrompt);
  }, [settings]);

  async function handleSave() {
    await update.mutateAsync({ systemPrompt, answerStyle, generationPrompt });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  if (isLoading) return <div className="text-sm text-muted-foreground">加载中…</div>;

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted-foreground">
        这里设置全局默认提示词。主题级别的提示词可在「主题管理」中单独覆盖。
      </p>

      <div className="space-y-1.5">
        <Label>System Prompt</Label>
        <Textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={6}
          placeholder="你是一个内容创作助手…"
          className="font-mono text-xs resize-y"
        />
      </div>

      <div className="space-y-1.5">
        <Label>回答风格</Label>
        <Textarea
          value={answerStyle}
          onChange={(e) => setAnswerStyle(e.target.value)}
          rows={3}
          placeholder="简短、结构清晰，适合知乎回答风格…"
          className="resize-y"
        />
      </div>

      <div className="space-y-1.5">
        <Label>生成提示词（Generation Prompt）</Label>
        <Textarea
          value={generationPrompt}
          onChange={(e) => setGenerationPrompt(e.target.value)}
          rows={4}
          placeholder="根据以下问题和背景生成回答…"
          className="font-mono text-xs resize-y"
        />
      </div>

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
