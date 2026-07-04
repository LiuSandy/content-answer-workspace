import { useEffect, useRef, useState } from "react";
import { Bot, Check, Copy, ExternalLink, LoaderCircle, RefreshCcw, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useWorkbenchStore } from "@/store/workbench-store";
import {
  clearStoredGenerationJob,
  readStoredGenerationJob,
  saveStoredGenerationJob,
  subscribeGenerationJob,
  type GenerationJobSubscription,
} from "@/features/workspace/generation-job-client";
import { cancelGenerationJob, createGenerationJob, getGenerationJob } from "@/features/workspace/workflow-api";
import type { GenerateOnePayload, WorkbenchItem } from "@/types/workflow";

function QuestionBrief({ item }: { item: WorkbenchItem }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3.5 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {item.sourceTopic && (
          <span className="rounded-[4px] bg-blue-50 px-1.5 py-[1px] text-[10px] font-semibold text-blue-700 ring-1 ring-blue-200">
            {item.sourceTopic}
          </span>
        )}
        <span className="text-[11px] text-slate-400">{item.answerCount} 个回答</span>
        {item.updatedTime && (
          <span className="text-[11px] text-slate-400">{item.updatedTime}</span>
        )}
        <button
          type="button"
          onClick={() => window.open(item.url, "_blank", "noreferrer")}
          className="ml-auto flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-700"
        >
          打开原链接
          <ExternalLink className="h-3 w-3" />
        </button>
      </div>
      <div className="text-[14px] font-semibold leading-snug text-slate-900">{item.title}</div>
      {item.excerpt && (
        <p className="mt-1.5 text-[12px] leading-relaxed text-slate-500">{item.excerpt}</p>
      )}
    </div>
  );
}

/** 工作台右侧回答工作区，使用问题自身的 promptConfig 生成回答。 */
export function WorkbenchAnswerPanel() {
  const {
    items,
    selectedItemId,
    updateItemAnswer,
    setItemGenerationStatus,
    startItemGenerationJob,
    restoreItemGenerationJob,
    appendItemStreamingAnswer,
    finishItemGenerationJob,
    failItemGenerationJob,
    interruptItemGenerationJob,
    cancelItemGenerationJob,
    globalPromptConfig,
  } = useWorkbenchStore();
  const item = items.find((i) => i.id === selectedItemId) ?? null;
  const [contentConstraint, setContentConstraint] = useState("");
  const [isCopied, setIsCopied] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const subscriptionRef = useRef<GenerationJobSubscription | null>(null);
  const restoredRef = useRef(false);

  function showStatus(type: "success" | "error" | "info", text: string) {
    setStatusMsg({ type, text });
    window.setTimeout(() => setStatusMsg(null), 3000);
  }

  function closeCurrentSubscription() {
    subscriptionRef.current?.close();
    subscriptionRef.current = null;
  }

  function buildGenerateOnePayload(target: WorkbenchItem): GenerateOnePayload {
    return {
      platform: target.sourcePlatform,
      item: target,
      answerStyle: globalPromptConfig.answerStyle,
      systemPrompt: globalPromptConfig.systemPrompt,
      generationPrompt: globalPromptConfig.generationPrompt,
      contentConstraint: contentConstraint || undefined,
    };
  }

  function persistJobProgress(targetId: string, jobId: string, eventId: number) {
    const latest = useWorkbenchStore.getState().items.find((i) => i.id === targetId);
    saveStoredGenerationJob({
      jobId,
      itemId: targetId,
      lastEventId: eventId,
      streamingAnswer: latest?.generationJob?.streamingAnswer || "",
    });
  }

  function subscribeToJob(target: WorkbenchItem, jobId: string, lastEventId: number) {
    closeCurrentSubscription();
    subscriptionRef.current = subscribeGenerationJob(jobId, lastEventId, {
      onChunk: (text, eventId) => {
        appendItemStreamingAnswer(target.id, text, eventId);
        persistJobProgress(target.id, jobId, eventId);
      },
      onDone: ({ data, id }) => {
        finishItemGenerationJob(target.id, {
          ...target,
          ...data.item,
          addedAt: target.addedAt,
          sourcePlatform: target.sourcePlatform,
          sourceTopic: target.sourceTopic,
          promptConfig: target.promptConfig,
        }, id);
        clearStoredGenerationJob();
        closeCurrentSubscription();
        showStatus("success", `已生成：${target.title}`);
      },
      onJobError: (message, eventId) => {
        failItemGenerationJob(target.id, message, eventId);
        clearStoredGenerationJob();
        closeCurrentSubscription();
        showStatus("error", message || "生成失败，请重试");
      },
      onCanceled: (message, eventId) => {
        cancelItemGenerationJob(target.id, message, eventId);
        clearStoredGenerationJob();
        closeCurrentSubscription();
        showStatus("info", message || "生成已取消");
      },
      onRecovering: () => {
        showStatus("info", "正在恢复生成连接...");
      },
      onInterrupted: (message) => {
        interruptItemGenerationJob(target.id, message);
        showStatus("error", message);
      },
    });
  }

  async function startGeneration(target: WorkbenchItem) {
    try {
      closeCurrentSubscription();
      setItemGenerationStatus(target.id, "creating");
      const { jobId } = await createGenerationJob(buildGenerateOnePayload(target));
      startItemGenerationJob(target.id, jobId);
      saveStoredGenerationJob({ jobId, itemId: target.id, lastEventId: 0, streamingAnswer: "" });
      subscribeToJob(target, jobId, 0);
    } catch (error) {
      const message = error instanceof Error ? error.message : "创建生成任务失败";
      failItemGenerationJob(target.id, message);
      showStatus("error", message);
    }
  }

  async function cancelGeneration(target: WorkbenchItem) {
    const jobId = target.generationJob?.jobId;
    if (!jobId) return;
    try {
      await cancelGenerationJob(jobId);
      cancelItemGenerationJob(target.id);
      clearStoredGenerationJob();
      closeCurrentSubscription();
      showStatus("info", "生成已取消");
    } catch (error) {
      const message = error instanceof Error ? error.message : "取消生成失败";
      showStatus("error", message);
    }
  }

  useEffect(() => {
    return () => closeCurrentSubscription();
  }, []);

  useEffect(() => {
    if (restoredRef.current) return;
    const stored = readStoredGenerationJob();
    if (!stored) return;
    const target = items.find((i) => i.id === stored.itemId);
    if (!target) return;
    restoredRef.current = true;
    void (async () => {
      try {
        const snapshot = await getGenerationJob(stored.jobId);
        if (snapshot.status === "done" && snapshot.finalItem) {
          finishItemGenerationJob(target.id, {
            ...target,
            ...snapshot.finalItem,
            addedAt: target.addedAt,
            sourcePlatform: target.sourcePlatform,
            sourceTopic: target.sourceTopic,
            promptConfig: target.promptConfig,
          }, snapshot.lastEventId);
          clearStoredGenerationJob();
          return;
        }
        if (snapshot.status === "pending" || snapshot.status === "running") {
          restoreItemGenerationJob(target.id, {
            jobId: stored.jobId,
            status: "generating",
            lastEventId: stored.lastEventId,
            streamingAnswer: stored.streamingAnswer,
          });
          subscribeToJob(target, stored.jobId, stored.lastEventId);
          return;
        }
        clearStoredGenerationJob();
      } catch {
        clearStoredGenerationJob();
        interruptItemGenerationJob(target.id, "任务不存在或已过期，可重新生成");
      }
    })();
  }, [items, finishItemGenerationJob, interruptItemGenerationJob, restoreItemGenerationJob]);

  const isGenerating = item?.generationStatus === "creating" || item?.generationStatus === "generating";
  const preview = item?.generationJob?.streamingAnswer || "";

  async function copyAnswer() {
    if (!item?.answer?.trim()) return;
    await navigator.clipboard.writeText(item.answer);
    setIsCopied(true);
    window.setTimeout(() => setIsCopied(false), 1500);
  }

  return (
    <div className="flex min-h-0 flex-col gap-3">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between gap-3">
        <span className={cn(
          "text-[11px] font-semibold tracking-wide transition-colors",
          statusMsg?.type === "error" ? "text-red-500" :
          statusMsg?.type === "success" ? "text-emerald-600" :
          statusMsg?.type === "info" ? "text-blue-600" :
          "uppercase text-slate-400",
        )}>
          {statusMsg ? statusMsg.text : "回答工作区"}
        </span>
        {item && (
          <div className="flex shrink-0 items-center gap-1.5">
            {isGenerating ? (
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 rounded-md border-slate-200 px-2.5 text-[12px] font-medium"
                onClick={() => cancelGeneration(item)}
              >
                <X className="h-3 w-3" />
                取消
              </Button>
            ) : item.answer?.trim() ? (
              <Button
                variant="outline"
                size="sm"
                className="h-7 gap-1.5 rounded-md border-slate-200 px-2.5 text-[12px] font-medium"
                onClick={() => startGeneration(item)}
              >
                <RefreshCcw className="h-3 w-3" />
                重新生成
              </Button>
            ) : (
              <Button
                size="sm"
                className="h-7 gap-1.5 rounded-md bg-slate-900 px-3 text-[12px] font-medium hover:bg-slate-800"
                onClick={() => startGeneration(item)}
              >
                <Sparkles className="h-3 w-3" />
                AI 生成
              </Button>
            )}
          </div>
        )}
      </div>

      {/* 内容约束 */}
      <div className="flex flex-col space-y-1.5">
        <Label className="text-[11px] font-medium text-slate-600">内容约束</Label>
        <Textarea
          rows={2}
          value={contentConstraint}
          onChange={(e) => setContentConstraint(e.target.value)}
          className="resize-none rounded-md border-slate-200 bg-white text-[12px] leading-relaxed shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
          placeholder="可选：对回答内容的额外约束或要求"
        />
      </div>

      {/* 空状态 */}
      {!item ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-md border border-dashed border-slate-200 bg-slate-50/50">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100">
            <Bot className="h-5 w-5 text-slate-400" />
          </div>
          <div className="text-center">
            <div className="text-[13px] font-semibold text-slate-700">未选中问题</div>
            <div className="mt-1 text-[12px] text-slate-400">从左侧问题列表选择一个题目</div>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <QuestionBrief item={item} />

          <div className="relative">
            {isGenerating ? (
              <div className="min-h-[320px] rounded-md border border-blue-300 bg-white px-3 py-3 text-[14px] leading-7 text-slate-800">
                {preview.trim() ? (
                  <div className="whitespace-pre-wrap break-words">{preview}</div>
                ) : (
                  <div className="text-slate-400">AI 正在生成回答…</div>
                )}
              </div>
            ) : (
              <MarkdownEditor
                className="min-h-[320px] rounded-md border border-slate-200 bg-white transition-colors"
                placeholder="点击 AI 生成 按钮自动撰写，或直接手工编辑内容。"
                value={item.answer || ""}
                onChange={(v) => updateItemAnswer(item.id, v)}
              />
            )}
            {item.answer?.trim() && !isGenerating && (
              <button
                type="button"
                onClick={copyAnswer}
                className="absolute right-2 top-[7px] z-10 flex items-center gap-1 rounded px-1.5 py-[3px] text-[11px] font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
              >
                {isCopied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
                {isCopied ? "已复制" : "复制"}
              </button>
            )}
            {isGenerating && (
              <div className="pointer-events-none absolute right-3 top-3">
                <div className="flex items-center gap-2 rounded-full border border-blue-200 bg-white/95 px-3.5 py-2 text-[12px] font-medium text-blue-600 shadow-sm">
                  <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  AI 正在生成回答…
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
