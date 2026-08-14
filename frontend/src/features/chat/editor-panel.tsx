import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "@tiptap/markdown";
import {
  Loader2,
  Sparkles,
  Wand2,
  Undo2,
  RefreshCw,
  AlertCircle,
  Copy,
  Check,
  X,
  Save,
  History,
  ExternalLink,
  ClipboardList,
  ListTree,
  Bot,
} from "lucide-react";

import { apiGet, apiPut, apiPost } from "@/lib/api";
import { streamPost } from "@/lib/sse";
import { useChatStore } from "@/store/chat-store";
import { useAlertDialog } from "@/hooks/use-alert-dialog";
import { InlineRefineMenu, type InlineRefineParams } from "./inline-refine-menu";
import { SelectionHighlight } from "./selection-highlight-extension";
import { QualityReviewDialog, ReportCard } from "./quality-review-dialog";
import type { QualityReviewRecordDTO } from "./quality-review-api";
import {
  compactOutlineLabel,
  compactReviewLabel,
  currentVersionBadgeClass,
  modelLabel,
} from "./version-history";
import {
  initialCreationProgress,
  reduceCreationProgress,
} from "./creation-review-lifecycle";
import { OutlineDialog } from "./outline-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { PromptInput } from "@/components/ui/prompt-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Drawer,
  DrawerTrigger,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
} from "@/components/ui/drawer";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type DocumentState = {
  documentId: string;
  sourceItemId: string;
  currentContent: string | null;
  currentVersionId: string | null;
  lockVersion: number;
  sourceItem?: {
    title: string;
    content: string | null;
    url: string;
    platform: string;
    author: string | null;
  } | null;
};

/**
 * run.failed 事件携带的业务层错误负载；后端把工作流内部异常（如选区不匹配、
 * 锁版本冲突）包装成这个 SSE 事件而不是 HTTP 错误状态码，因此不会触发
 * streamPost 的 onError，必须在 onEvent 里单独识别。
 */
type RunFailedPayload = {
  errorCode?: string;
  message?: string;
};

/**
 * 三处流式调用（生成 / 精修 / 重写）共用的 run.failed 处理逻辑：提示错误信息。
 * notify 由调用组件通过 useAlertDialog() 传入，因为该函数定义在组件外部，
 * 无法直接调用依赖 Context 的 Hook。
 */
function handleRunFailed(data: RunFailedPayload, notify: (options: { description: string }) => Promise<void>) {
  void notify({ description: data.message || "操作失败，请稍后重试" });
}

type VersionSummary = {
  id: string;
  versionNumber: number;
  versionType: string;
  instruction: string | null;
  provider: string | null;
  model: string | null;
  outlineOperationId: string | null;
  outlineVersionNumber: number | null;
  outlineStatus: "draft" | "confirmed" | null;
  outlineSections: Array<{
    id?: string;
    order?: number;
    heading: string;
    keyPoints: string[];
    wordCountEstimate: number;
  }>;
  qualityReview: QualityReviewRecordDTO | null;
  contentSummary: string;
  createdAt: string;
};



/**
 * 右侧编辑面板：选中帖子后展示回答生成 / 编辑 / 版本历史。
 *
 * 独立组件，因为编辑区的状态（文档版本、Tiptap 实例、AI 操作）与对话流无关，
 * 只受 selectedSourceItemId 驱动。
 */
export function EditorPanel() {
  const queryClient = useQueryClient();
  const { selectedSourceItemId, setSelectedSourceItemId } = useChatStore();
  const { confirm, notify } = useAlertDialog();

  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [creationProgress, setCreationProgress] = useState(initialCreationProgress);
  const isGeneratingRef = useRef(isGenerating);
  useEffect(() => {
    isGeneratingRef.current = isGenerating;
  }, [isGenerating]);
  const [copied, setCopied] = useState(false);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);
  const [wordCount, setWordCount] = useState<number>(1000);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [qualityDialogOpen, setQualityDialogOpen] = useState(false);
  const [outlineDialogOpen, setOutlineDialogOpen] = useState(false);

  const STYLE_DESCRIPTIONS: Record<string, string> = {
    professional: "- 专业严谨：语言条理清晰，论证逻辑严密，多用客观事实与专业数据支撑观点。",
    humorous: "- 幽默风趣：语言轻松幽默，多采用比喻和口语化的表达方式，生动有趣且接地气。",
    detailed: "- 干货满满：内容充实深刻，包含大量实操性强的要点、步骤与具体方法，无多余废话。",
    emotional: "- 感性生动：注重与读者的情感共鸣，描写生动具体，带有较强的心理感染力与情境代入感。",
    concise: "- 简明扼要：言简意赅，直奔主题，只保留最核心的观点，精简文字篇幅与不必要的铺垫。",
  };

  const getStyleRulesPayload = () => {
    if (selectedStyles.length === 0) {
      return "";
    }
    const lines = selectedStyles.map((id) => STYLE_DESCRIPTIONS[id]).filter(Boolean);
    return lines.join("\n");
  };

  const handleCopy = async () => {
    if (!editor) return;
    try {
      await navigator.clipboard.writeText((editor as any).getMarkdown());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      void notify("复制失败");
    }
  };

  // 1. 获取文档状态
  const { data: docState, isLoading: isDocLoading, error: docError } = useQuery<DocumentState>({
    queryKey: ["document", selectedSourceItemId],
    queryFn: () => apiGet(`/api/source-items/${selectedSourceItemId}/document`),
    enabled: !!selectedSourceItemId,
  });

  // 使用 Ref 避免 Tiptap 回调中的过期闭包 (Stale Closure) 问题
  const docStateRef = useRef(docState);
  useEffect(() => {
    docStateRef.current = docState;
  }, [docState]);

  const onUpdateRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    onUpdateRef.current = () => {
      if (isGeneratingRef.current || !editor) return;
      debouncedSave((editor as any).getMarkdown());
    };
  });

  // Tiptap 编辑器实例
  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown.configure({
        markedOptions: {
          gfm: true,
          breaks: true,
        }
      }),
      Placeholder.configure({
        placeholder: "点击上方「生成回答」开始创作，或者在此手动输入内容...",
      }),
      SelectionHighlight,
    ],
    content: "",
    onUpdate: () => {
      onUpdateRef.current?.();
    },
  }, [selectedSourceItemId]);

  // 页面切换或文档加载完成后同步内容
  useEffect(() => {
    if (editor && docState) {
      const currentContent = docState.currentContent || "";
      const hasMarkdownMarkers = currentContent.includes("**") || currentContent.includes("###") || /^\s*[-*]\s+/m.test(currentContent);
      const isHtml = (currentContent.includes("<p>") || currentContent.includes("<strong>") || currentContent.includes("<ul>") || currentContent.includes("<li>")) && !hasMarkdownMarkers;

      let cleanContent = currentContent;
      if (!isHtml && cleanContent.startsWith("<p>") && cleanContent.endsWith("</p>")) {
        cleanContent = cleanContent.slice(3, -4);
        cleanContent = cleanContent.replace(/<br\s*\/?>/gi, "\n");
        cleanContent = cleanContent.replace(/<\/p>\s*<p>/gi, "\n\n");
      }

      const editorValue = isHtml ? editor.getHTML() : editor.getMarkdown();
      if (editorValue !== cleanContent) {
        (editor.commands as any).setContent(cleanContent, {
          contentType: isHtml ? "html" : "markdown",
          emitUpdate: false,
        });
      }
    }
  }, [docState, editor]);

  // 2. 自动保存
  const autoSaveMutation = useMutation({
    mutationFn: (args: { content: string; lockVersion: number }) =>
      apiPut<DocumentState>(`/api/documents/${docStateRef.current?.documentId}`, {
        content: args.content,
        expectedLockVersion: args.lockVersion,
      }),
    onSuccess: (updatedState) => {
      queryClient.setQueryData(["document", selectedSourceItemId], updatedState);
    },
    onError: (err: any) => {
      console.error("Auto save failed:", err);
      queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
    },
  });

  const saveTimeoutRef = useRef<any>(null);
  const cancelDebouncedSave = () => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
    }
  };

  const flushPendingSave = async () => {
    const currentDocState = docStateRef.current;
    if (saveTimeoutRef.current && currentDocState && editor) {
      clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = null;
      const currentMarkdown = (editor as any).getMarkdown();
      try {
        const updatedState = await autoSaveMutation.mutateAsync({
          content: currentMarkdown,
          lockVersion: currentDocState.lockVersion,
        });
        return updatedState;
      } catch (err) {
        console.error("Failed to flush pending save:", err);
      }
    }
    return null;
  };

  const debouncedSave = (content: string) => {
    const currentDocState = docStateRef.current;
    if (!currentDocState) return;
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      autoSaveMutation.mutate({ content, lockVersion: currentDocState.lockVersion });
    }, 1500);
  };

  const hasContent = !!editor?.getText()?.trim();

  // 乐观锁冲突：让编辑器基于最新内容操作
  const handleQualityConflictRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
    queryClient.invalidateQueries({ queryKey: ["versions", docState?.documentId] });
  };

  // 3. 手动保存版本
  const saveCheckpointMutation = useMutation({
    mutationFn: () =>
      apiPost<DocumentState>(`/api/documents/${docStateRef.current?.documentId}/versions`, {
        expectedLockVersion: docStateRef.current?.lockVersion,
      }),
    onSuccess: (updatedState) => {
      queryClient.setQueryData(["document", selectedSourceItemId], updatedState);
      queryClient.invalidateQueries({ queryKey: ["versions", docStateRef.current?.documentId] });
      queryClient.invalidateQueries({ queryKey: ["outline", docStateRef.current?.documentId] });
      queryClient.invalidateQueries({ queryKey: ["outline-versions", docStateRef.current?.documentId] });
    },
  });

  // 历史版本列表
  const { data: versions = [] } = useQuery<VersionSummary[]>({
    queryKey: ["versions", docState?.documentId],
    queryFn: () => apiGet(`/api/documents/${docState?.documentId}/versions`),
    enabled: !!docState?.documentId,
  });

  // 恢复历史版本
  const restoreVersionMutation = useMutation({
    mutationFn: (versionId: string) =>
      apiPost<DocumentState>(`/api/documents/${docStateRef.current?.documentId}/versions/${versionId}/restore`, {
        expectedLockVersion: docStateRef.current?.lockVersion,
      }),
    onSuccess: (updatedState) => {
      queryClient.setQueryData(["document", selectedSourceItemId], updatedState);
      queryClient.invalidateQueries({ queryKey: ["versions", docStateRef.current?.documentId] });
      if (editor) {
        const restoredContent = updatedState.currentContent || "";
        const isHtml = restoredContent.includes("<p>") || restoredContent.includes("<strong>") || restoredContent.includes("<ul>") || restoredContent.includes("<li>");
        (editor.commands as any).setContent(restoredContent, {
          contentType: isHtml ? "html" : "markdown",
          emitUpdate: false,
        });
      }
      setHistoryDrawerOpen(false);
    },
  });

  // 4. AI 生成回答 (Stream)
  const handleGenerateAnswer = async () => {
    const cachedDocState = queryClient.getQueryData<DocumentState>(["document", selectedSourceItemId]);
    const currentDocState = cachedDocState || docStateRef.current;
    if (!currentDocState || isGenerating || !editor) return;
    cancelDebouncedSave();
    setIsGenerating(true);
    setCreationProgress(reduceCreationProgress(initialCreationProgress, "run.started", {}));
    editor.commands.setContent("");
    let terminalEventReceived = false;

    try {
      await streamPost(
        `/api/source-items/${selectedSourceItemId}/document/generate`,
        {
          expectedLockVersion: currentDocState.lockVersion,
          platform: currentDocState.sourceItem?.platform || "zhihu",
          styleRules: getStyleRulesPayload(),
          wordCount: wordCount,
          instruction: rewriteInstruction.trim() || undefined,
        },
        {
          onEvent: (event, data) => {
            if (["run.started", "review.started", "review.completed", "rewrite.started", "document.completed", "run.completed", "run.failed"].includes(event)) {
              setCreationProgress((state) => reduceCreationProgress(state, event, data));
            }
            if (event === "document.delta") {
              editor.commands.insertContent(data.delta);
            } else if (event === "document.completed") {
              queryClient.setQueryData(["document", selectedSourceItemId], data);
              queryClient.invalidateQueries({ queryKey: ["versions", data.documentId] });
              queryClient.invalidateQueries({ queryKey: ["quality-reviews", data.documentId] });
              (editor.commands as any).setContent(data.currentContent || "", {
                contentType: "markdown",
                emitUpdate: false,
              });
            } else if (event === "run.completed") {
              terminalEventReceived = true;
              setIsGenerating(false);
            } else if (event === "run.failed") {
              terminalEventReceived = true;
              setIsGenerating(false);
              handleRunFailed(data, notify);
              queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
            }
          },
          onError: (err) => {
            terminalEventReceived = true;
            setIsGenerating(false);
            setCreationProgress((state) => reduceCreationProgress(state, "run.failed", {}));
            void notify(`生成失败: ${err.message}`);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      if (!terminalEventReceived) {
        setIsGenerating(false);
        setCreationProgress((state) => reduceCreationProgress(state, "run.failed", {}));
      }
    }
  };

  // 5. 局部精修 (Stream)：由 InlineRefineMenu 在提交对话框时携带选区快照调用
  const handleInlineRefinement = async ({ from, to, text: selectedText, instruction }: InlineRefineParams) => {
    const cachedDocState = queryClient.getQueryData<DocumentState>(["document", selectedSourceItemId]);
    const currentDocState = cachedDocState || docStateRef.current;
    if (!currentDocState || isGenerating || !editor) return;

    // 立即保存挂起的修改，确保后端内容最新，并获取最新 lockVersion
    const updatedState = await flushPendingSave();
    const activeCachedState = queryClient.getQueryData<DocumentState>(["document", selectedSourceItemId]);
    const activeLockVersion = updatedState
      ? updatedState.lockVersion
      : (activeCachedState ? activeCachedState.lockVersion : currentDocState.lockVersion);

    setIsGenerating(true);
    editor.commands.deleteRange({ from, to });

    try {
      await streamPost(
        `/api/documents/${currentDocState.documentId}/refine`,
        {
          expectedLockVersion: activeLockVersion,
          instruction,
          selection: { fromPos: from, toPos: to, text: selectedText },
        },
        {
          onEvent: (event, data) => {
            if (event === "document.delta") {
              editor.commands.insertContent(data.delta);
            } else if (event === "document.completed") {
              queryClient.setQueryData(["document", selectedSourceItemId], data);
              queryClient.invalidateQueries({ queryKey: ["versions", data.documentId] });
              (editor.commands as any).setContent(data.currentContent || "", {
                contentType: "markdown",
                emitUpdate: false,
              });
            } else if (event === "run.failed") {
              // run.failed 走的是业务层错误通道（HTTP 200 + SSE 事件），不经过 onError，
              // 因此这里之前已执行的 deleteRange 从未被撤销——必须在这个分支里手动恢复。
              handleRunFailed(data, notify);
              editor.commands.insertContentAt(from, selectedText);
              queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
            }
          },
          onError: (err) => {
            void notify(`精修失败: ${err.message}`);
            editor.commands.insertContentAt(from, selectedText);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      setIsGenerating(false);
    }
  };

  // 6. 全文重写 (Stream)
  const handleFullRewrite = async () => {
    const cachedDocState = queryClient.getQueryData<DocumentState>(["document", selectedSourceItemId]);
    const currentDocState = cachedDocState || docStateRef.current;
    if (!currentDocState || isGenerating || !editor) return;

    const hasContent = !!editor.getText()?.trim();
    if (!hasContent || !rewriteInstruction.trim()) {
      await handleGenerateAnswer();
      return;
    }
    
    // 立即保存挂起的修改，确保获取最新 lockVersion
    const updatedState = await flushPendingSave();
    const activeCachedState = queryClient.getQueryData<DocumentState>(["document", selectedSourceItemId]);
    const activeLockVersion = updatedState 
      ? updatedState.lockVersion 
      : (activeCachedState ? activeCachedState.lockVersion : currentDocState.lockVersion);
    
    setIsGenerating(true);
    editor.commands.setContent("");

    try {
      await streamPost(
        `/api/documents/${currentDocState.documentId}/rewrite`,
        {
          expectedLockVersion: activeLockVersion,
          instruction: rewriteInstruction,
          platform: currentDocState.sourceItem?.platform || "zhihu",
          styleRules: getStyleRulesPayload(),
          wordCount: wordCount,
        },
        {
          onEvent: (event, data) => {
            if (event === "document.delta") {
              editor.commands.insertContent(data.delta);
            } else if (event === "document.completed") {
              queryClient.setQueryData(["document", selectedSourceItemId], data);
              queryClient.invalidateQueries({ queryKey: ["versions", data.documentId] });
              (editor.commands as any).setContent(data.currentContent || "", {
                contentType: "markdown",
                emitUpdate: false,
              });
            } else if (event === "run.failed") {
              handleRunFailed(data, notify);
              queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
            }
          },
          onError: (err) => {
            void notify(`重写失败: ${err.message}`);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      setIsGenerating(false);
      setRewriteInstruction("");
    }
  };

  // ── 空状态：未选帖子 ──
  if (!selectedSourceItemId) {
    return (
      <aside className="flex h-full w-full flex-col items-center justify-center border-l bg-muted/30 p-8 text-center">
        {/* 渐变圆形图标（参考设计稿） */}
        <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-violet-200 via-pink-100 to-amber-100 shadow-sm dark:from-violet-900/40 dark:via-pink-900/30 dark:to-amber-900/30">
          <Sparkles className="h-7 w-7 text-violet-500 dark:text-violet-300" />
        </div>
        <p className="text-sm text-muted-foreground">
          等待 Agent 完成分析与生成…
        </p>
      </aside>
    );
  }

  // ── 加载态 ──
  if (isDocLoading) {
    return (
      <aside className="flex h-full w-full items-center justify-center border-l bg-muted/30">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
      </aside>
    );
  }

  // ── 错误态 ──
  if (docError) {
    return (
      <aside className="flex h-full w-full flex-col items-center justify-center border-l bg-muted/30 p-8 text-center">
        <AlertCircle className="mb-2 h-8 w-8 text-destructive" />
        <p className="text-sm font-semibold text-destructive">文档加载失败</p>
        <p className="mt-1 text-xs text-muted-foreground">{docError.message}</p>
      </aside>
    );
  }

  // ── 正常编辑态 ──
  return (
    <aside className="flex h-full w-full flex-col min-h-0 overflow-hidden border-l bg-card">

      {/* ── 头部：原文信息 + 操作按钮 ── */}
      <div className="border-b bg-zinc-50/50 dark:bg-zinc-950/20 px-4 py-3 shrink-0">
        <div className="flex items-start justify-between gap-3 min-w-0">

          {/* 左侧：平台标签 + 标题 + 作者 + 摘要 */}
          <div className="flex flex-col gap-1.5 min-w-0 flex-1">
            {/* 平台 badge + 可点击标题 */}
            <div className="flex items-center gap-2 min-w-0">
              {docState?.sourceItem?.platform && (
                <Badge
                  variant="outline"
                  className="text-[10px] uppercase font-bold text-indigo-600 border-indigo-600/30 dark:text-indigo-400 dark:border-indigo-400/30 shrink-0"
                >
                  {docState.sourceItem.platform}
                </Badge>
              )}
              {docState?.sourceItem ? (
                docState.sourceItem.url ? (
                  <a
                    href={docState.sourceItem.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-1 min-w-0"
                    title="点击查看原文"
                  >
                    <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {docState.sourceItem.title}
                    </h3>
                    <ExternalLink className="h-3 w-3 shrink-0 text-zinc-400 group-hover:text-indigo-500 transition-colors" />
                  </a>
                ) : (
                  <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                    {docState.sourceItem.title}
                  </h3>
                )
              ) : null}
            </div>

            {/* 作者 */}
            {docState?.sourceItem?.author && (
              <p className="text-[11px] text-muted-foreground">
                作者：{docState.sourceItem.author}
              </p>
            )}

            {/* 原文摘要（最多 3 行） */}
            {docState?.sourceItem?.content && (
              <p className="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed line-clamp-3 whitespace-pre-wrap">
                {docState.sourceItem.content}
              </p>
            )}
          </div>

          {/* 右侧：操作按钮组 */}
          <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
            {/* 复制按钮 */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  disabled={!hasContent}
                  className="h-7 px-2 text-xs gap-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5 text-green-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{copied ? "已复制" : "复制内容"}</TooltipContent>
            </Tooltip>

            <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-700" />

            {/* 已保存 / 保存中 → 点击打开历史版本 Drawer */}
            <Drawer
              open={historyDrawerOpen}
              onOpenChange={setHistoryDrawerOpen}
              swipeDirection="left"
            >
              <DrawerTrigger
                render={
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={autoSaveMutation.isPending}
                    className="h-7 px-2 text-xs gap-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                  />
                }
              >
                {autoSaveMutation.isPending ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>保存中</span>
                  </>
                ) : (
                  <>
                    <Save className="h-3 w-3" />
                    <span>已保存</span>
                    {versions.length > 0 && (
                      <Badge variant="secondary" className="h-4 px-1 text-[10px] rounded-full">
                        {versions.length}
                      </Badge>
                    )}
                  </>
                )}
              </DrawerTrigger>

              <DrawerContent className="w-[31rem] max-w-[calc(100vw-0.75rem)] overflow-hidden border-l-slate-200 bg-[#fbfbf8] dark:border-slate-800 dark:bg-slate-950">
                <DrawerHeader className="border-b border-slate-200/80 px-6 py-5 dark:border-slate-800">
                  <DrawerTitle className="flex items-center gap-2.5 text-lg font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950">
                      <History className="h-4 w-4" />
                    </span>
                    创作档案
                  </DrawerTitle>
                  <DrawerDescription className="pl-10 text-xs leading-5 text-slate-500 dark:text-slate-400">
                    回看每次创作使用的模型、大纲与评审结果
                  </DrawerDescription>
                </DrawerHeader>

                <HistoryDrawerContent
                  versions={versions}
                  currentVersionId={docState?.currentVersionId ?? null}
                  onRestore={async (versionId) => {
                    const confirmed = await confirm({
                      description: "确认恢复此版本？当前编辑中的内容将被覆盖。",
                    });
                    if (confirmed) {
                      restoreVersionMutation.mutate(versionId);
                    }
                  }}
                />
              </DrawerContent>
            </Drawer>

            <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-700" />

            {/* 质检评审入口 */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs gap-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
                  onClick={() => setQualityDialogOpen(true)}
                >
                  <ClipboardList className="h-3.5 w-3.5" />
                  查看评审
                </Button>
              </TooltipTrigger>
              <TooltipContent>查看本次创作的自动评审结果</TooltipContent>
            </Tooltip>

            <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-700" />

            {/* 关闭面板 */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground hover:text-foreground hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg"
                  onClick={() => setSelectedSourceItemId(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>关闭编辑面板</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* ── 编辑器主体（始终显示） ── */}
      <EditorTabContent
        editor={editor}
        isGenerating={isGenerating}
        progressLabel={creationProgress.label}
        rewriteInstruction={rewriteInstruction}
        setRewriteInstruction={setRewriteInstruction}
        onRewrite={handleFullRewrite}
        onInlineRefine={handleInlineRefinement}
        selectedStyles={selectedStyles}
        setSelectedStyles={setSelectedStyles}
        wordCount={wordCount}
        onWordCountChange={setWordCount}
        onOpenOutline={() => setOutlineDialogOpen(true)}
      />

      {/* 质检评审 Dialog */}
      <QualityReviewDialog
        open={qualityDialogOpen}
        onOpenChange={setQualityDialogOpen}
        documentId={docState?.documentId ?? null}
      />

      {/* 大纲 Dialog */}
      <OutlineDialog
        open={outlineDialogOpen}
        onOpenChange={setOutlineDialogOpen}
        documentId={docState?.documentId ?? null}
        sourceItemId={docState?.sourceItemId ?? null}
        lockVersion={docState?.lockVersion ?? 1}
        onLockConflict={handleQualityConflictRefresh}
      />
    </aside>
  );
}

function EditorTabContent({
  editor,
  isGenerating,
  progressLabel,
  rewriteInstruction,
  setRewriteInstruction,
  onRewrite,
  onInlineRefine,
  selectedStyles,
  setSelectedStyles,
  wordCount,
  onWordCountChange,
  onOpenOutline,
}: {
  editor: ReturnType<typeof useEditor>;
  isGenerating: boolean;
  progressLabel: string;
  rewriteInstruction: string;
  setRewriteInstruction: (v: string) => void;
  onRewrite: () => void;
  onInlineRefine: (params: InlineRefineParams) => void;
  selectedStyles: string[];
  setSelectedStyles: (styles: string[]) => void;
  wordCount: number;
  onWordCountChange: (v: number) => void;
  onOpenOutline: () => void;
}) {
  const hasContent = !!editor?.getText()?.trim();

  return (
    <div className="relative flex flex-1 flex-col min-h-0 overflow-hidden">
      {/* Tiptap 编辑区 */}
      <ScrollArea className="flex-1 min-h-0 p-4">
        <EditorContent editor={editor} className="prose dark:prose-invert max-w-none outline-none min-h-[300px]" />
        <InlineRefineMenu editor={editor} isGenerating={isGenerating} onRefine={onInlineRefine} />
      </ScrollArea>

      {/* 居中加载浮层 */}
      {isGenerating && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-white/40 dark:bg-zinc-950/40 backdrop-blur-[1px] select-none pointer-events-auto">
          <div className="flex items-center gap-2.5 rounded-xl border border-indigo-100 dark:border-indigo-900 bg-white/95 dark:bg-zinc-900/95 px-5 py-3.5 shadow-xl">
            <Loader2 className="h-4.5 w-4.5 animate-spin text-indigo-600 dark:text-indigo-400" />
            <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 animate-pulse">
              {progressLabel || "正在生成内容"}
            </span>
          </div>
        </div>
      )}

      {/* 底部 AI 操作栏 */}
      <div className="border-t bg-muted/30 p-4 fixed-bottom-input-area">
        <PromptInput
          value={rewriteInstruction}
          onChange={setRewriteInstruction}
          onSubmit={onRewrite}
          placeholder="输入重写指令进行重写，或直接发送以重新生成"
          disabled={isGenerating}
          allowEmpty={true}
          submitLabel={hasContent ? "重新生成" : "一键生成"}
          submitIcon={hasContent ? <RefreshCw className="h-3.5 w-3.5" /> : <Wand2 className="h-3.5 w-3.5" />}
          selectedStyles={selectedStyles}
          onSelectedStylesChange={setSelectedStyles}
          wordCount={wordCount}
          onWordCountChange={onWordCountChange}
          afterWordCountActions={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs gap-1 text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              onClick={onOpenOutline}
              disabled={isGenerating}
              title="生成或编辑回答大纲"
            >
              <ListTree className="h-3.5 w-3.5" />
              大纲
            </Button>
          }
        />
      </div>
    </div>
  );
}

// ── 历史版本 Drawer 内容 ─────────────────────────────────────────────

function HistoryDrawerContent({
  versions,
  currentVersionId,
  onRestore,
}: {
  versions: VersionSummary[];
  currentVersionId: string | null;
  onRestore: (versionId: string) => void;
}) {
  const [outlineDetail, setOutlineDetail] = useState<VersionSummary | null>(null);
  const [reviewDetail, setReviewDetail] = useState<VersionSummary | null>(null);

  if (versions.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-xs text-muted-foreground">
        暂无历史版本快照
      </div>
    );
  }

  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="relative space-y-3 before:absolute before:bottom-5 before:left-[7px] before:top-5 before:w-px before:bg-slate-200 dark:before:bg-slate-800">
        {versions.map((ver) => {
          const isCurrent = ver.id === currentVersionId;
          const reviewPassed = ver.qualityReview?.passed;
          return (
            <article
              key={ver.id}
              className="relative pl-6"
            >
              <span
                className={`absolute left-0 top-4 z-10 h-[15px] w-[15px] rounded-full border-4 border-[#fbfbf8] dark:border-slate-950 ${
                  isCurrent ? "bg-slate-950 dark:bg-slate-100" : "bg-slate-300 dark:bg-slate-700"
                }`}
              />
              <div className={`overflow-hidden rounded-xl border bg-white shadow-[0_4px_18px_rgba(15,23,42,0.035)] transition-shadow hover:shadow-[0_8px_24px_rgba(15,23,42,0.065)] dark:bg-slate-900 ${
                isCurrent ? "border-slate-900 dark:border-slate-200" : "border-slate-200 dark:border-slate-800"
              }`}>
                {isCurrent ? <div className="h-0.5 bg-slate-950 dark:bg-slate-100" /> : null}
                <div className="flex flex-col gap-2.5 p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                      版本 {ver.versionNumber}
                    </span>
                    {isCurrent && (
                      <Badge className={currentVersionBadgeClass}>
                        当前版本
                      </Badge>
                    )}
                  </div>
                  <time className="font-mono text-[10px] text-slate-400 dark:text-slate-500">
                    {new Date(ver.createdAt).toLocaleString()}
                  </time>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                  <Bot className="h-3.5 w-3.5 shrink-0 text-slate-700 dark:text-slate-300" />
                  <span className="truncate font-mono">{modelLabel(ver.provider, ver.model)}</span>
                </div>

                <div>
                  <p className="line-clamp-3 text-xs leading-[1.65] text-slate-600 dark:text-slate-300">
                    {ver.contentSummary || "该版本暂无内容摘要"}
                  </p>
                </div>

                <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-2.5 dark:border-slate-800">
                  <div className="flex min-w-0 items-center gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 rounded-md px-2 text-[11px] font-medium text-amber-800 hover:bg-amber-50 hover:text-amber-950 disabled:text-slate-400 dark:text-amber-300 dark:hover:bg-amber-950/50"
                      disabled={!ver.outlineOperationId}
                      onClick={() => setOutlineDetail(ver)}
                    >
                      <ListTree className="h-3.5 w-3.5" />
                      {compactOutlineLabel(ver.outlineVersionNumber, ver.outlineSections.length)}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className={`h-7 rounded-md px-2 text-[11px] font-medium disabled:text-slate-400 ${
                        reviewPassed
                          ? "text-emerald-700 hover:bg-emerald-50 hover:text-emerald-900 dark:text-emerald-400 dark:hover:bg-emerald-950/50"
                          : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                      }`}
                      disabled={!ver.qualityReview}
                      onClick={() => setReviewDetail(ver)}
                    >
                      <ClipboardList className="h-3.5 w-3.5" />
                      {compactReviewLabel(ver.qualityReview)}
                    </Button>
                  </div>
                  <Button
                    variant={isCurrent ? "ghost" : "outline"}
                    size="sm"
                    className="h-7 shrink-0 rounded-md px-2.5 text-[11px]"
                    onClick={() => onRestore(ver.id)}
                    disabled={isCurrent}
                  >
                    <Undo2 className="h-3 w-3" />
                    {isCurrent ? "当前版本" : "恢复此版本"}
                  </Button>
                </div>
                </div>
              </div>
            </article>
          );
        })}
        </div>
      </div>

      <Dialog open={!!outlineDetail} onOpenChange={(open) => !open && setOutlineDetail(null)}>
        <DialogContent className="h-[min(78vh,680px)] max-w-xl !flex min-h-0 flex-col overflow-hidden bg-[#fbfbf8] dark:bg-slate-950">
          <DialogHeader className="shrink-0 border-b border-slate-200 pb-4 dark:border-slate-800">
            <DialogTitle className="flex items-center gap-2 text-lg tracking-tight">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                <ListTree className="h-4 w-4" />
              </span>
              版本 {outlineDetail?.versionNumber} 使用的大纲
              {outlineDetail?.outlineVersionNumber ? (
                <Badge variant="secondary">O{outlineDetail.outlineVersionNumber}</Badge>
              ) : null}
            </DialogTitle>
            <DialogDescription>历史大纲快照，仅供查看，不会修改当前大纲。</DialogDescription>
          </DialogHeader>
          <ScrollArea className="min-h-0 flex-1 pr-3">
            <div className="space-y-3 py-1">
              {(outlineDetail?.outlineSections ?? []).map((section, index) => (
                <section key={section.id ?? index} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                  <div className="flex items-start gap-2">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-950 text-[10px] font-semibold text-white dark:bg-slate-100 dark:text-slate-950">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <h4 className="text-xs font-semibold">{section.heading}</h4>
                      <p className="mt-0.5 text-[10px] text-muted-foreground">约 {section.wordCountEstimate} 字</p>
                    </div>
                  </div>
                  {section.keyPoints.length > 0 ? (
                    <ul className="mt-2 list-disc space-y-1 pl-9 text-[11px] leading-5 text-muted-foreground">
                      {section.keyPoints.map((point, pointIndex) => <li key={pointIndex}>{point}</li>)}
                    </ul>
                  ) : null}
                </section>
              ))}
              {outlineDetail && outlineDetail.outlineSections.length === 0 ? (
                <p className="py-12 text-center text-xs text-muted-foreground">该版本没有大纲快照。</p>
              ) : null}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reviewDetail} onOpenChange={(open) => !open && setReviewDetail(null)}>
        <DialogContent className="h-[min(78vh,680px)] max-w-2xl !flex min-h-0 flex-col overflow-hidden bg-[#fbfbf8] dark:bg-slate-950">
          <DialogHeader className="shrink-0 border-b border-slate-200 pb-4 dark:border-slate-800">
            <DialogTitle className="flex items-center gap-2 text-lg tracking-tight">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                <ClipboardList className="h-4 w-4" />
              </span>
              版本 {reviewDetail?.versionNumber} 的自动评审
            </DialogTitle>
            <DialogDescription>历史评审结果，仅供查看。</DialogDescription>
          </DialogHeader>
          <ScrollArea className="min-h-0 flex-1 pr-3">
            {reviewDetail?.qualityReview ? <ReportCard report={reviewDetail.qualityReview} /> : null}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}
