import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { Markdown } from "@tiptap/markdown";
import {
  FileText,
  Loader2,
  Sparkles,
  Save,
  Wand2,
  Undo2,
  RefreshCw,
  History,
  AlertCircle,
  Globe,
  Copy,
  Check,
  X,
} from "lucide-react";

import { apiGet, apiPut, apiPost } from "@/lib/api";
import { streamPost } from "@/lib/sse";
import { useChatStore } from "@/store/chat-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PromptInput } from "@/components/ui/prompt-input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

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

type VersionSummary = {
  id: string;
  versionNumber: number;
  versionType: string;
  instruction: string | null;
  provider: string | null;
  model: string | null;
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

  const [refineInstruction, setRefineInstruction] = useState("");
  const [rewriteInstruction, setRewriteInstruction] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const isGeneratingRef = useRef(isGenerating);
  useEffect(() => {
    isGeneratingRef.current = isGenerating;
  }, [isGenerating]);
  const [activeTab, setActiveTab] = useState<string>("editor");
  const [copied, setCopied] = useState(false);
  const [selectedStyles, setSelectedStyles] = useState<string[]>([]);
  const [wordCount, setWordCount] = useState<number>(1000);

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
      alert("复制失败");
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

  // 3. 手动保存版本
  const saveCheckpointMutation = useMutation({
    mutationFn: () =>
      apiPost<DocumentState>(`/api/documents/${docStateRef.current?.documentId}/versions`, {
        expectedLockVersion: docStateRef.current?.lockVersion,
      }),
    onSuccess: (updatedState) => {
      queryClient.setQueryData(["document", selectedSourceItemId], updatedState);
      queryClient.invalidateQueries({ queryKey: ["versions", docStateRef.current?.documentId] });
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
      setActiveTab("editor");
    },
  });

  // 4. AI 生成回答 (Stream)
  const handleGenerateAnswer = async () => {
    const currentDocState = docStateRef.current;
    if (!currentDocState || isGenerating || !editor) return;
    cancelDebouncedSave();
    setIsGenerating(true);
    editor.commands.setContent("");

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
            if (event === "document.delta") {
              editor.commands.insertContent(data.delta);
            } else if (event === "document.completed") {
              queryClient.setQueryData(["document", selectedSourceItemId], data);
              queryClient.invalidateQueries({ queryKey: ["versions", data.documentId] });
              (editor.commands as any).setContent(data.currentContent || "", {
                contentType: "markdown",
                emitUpdate: false,
              });
            }
          },
          onError: (err) => {
            alert(`生成失败: ${err.message}`);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      setIsGenerating(false);
    }
  };

  // 5. 局部精修 (Stream)
  const handleInlineRefinement = async () => {
    const currentDocState = docStateRef.current;
    if (!currentDocState || isGenerating || !editor || !refineInstruction.trim()) return;

    const { from, to } = editor.state.selection;
    if (from === to) {
      alert("请先在编辑器中划选一段要优化的文字");
      return;
    }
    const selectedText = editor.state.doc.textBetween(from, to, " ");
    
    // 立即保存挂起的修改，确保后端内容最新，并获取最新 lockVersion
    const updatedState = await flushPendingSave();
    const activeLockVersion = updatedState ? updatedState.lockVersion : currentDocState.lockVersion;
    
    setIsGenerating(true);
    editor.commands.deleteSelection();

    try {
      await streamPost(
        `/api/documents/${currentDocState.documentId}/refine`,
        {
          expectedLockVersion: activeLockVersion,
          instruction: refineInstruction,
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
            }
          },
          onError: (err) => {
            alert(`精修失败: ${err.message}`);
            editor.commands.insertContent(selectedText);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      setIsGenerating(false);
      setRefineInstruction("");
    }
  };

  // 6. 全文重写 (Stream)
  const handleFullRewrite = async () => {
    const currentDocState = docStateRef.current;
    if (!currentDocState || isGenerating || !editor) return;

    const hasContent = !!editor.getText()?.trim();
    if (!hasContent || !rewriteInstruction.trim()) {
      await handleGenerateAnswer();
      return;
    }
    
    // 立即保存挂起的修改，确保获取最新 lockVersion
    const updatedState = await flushPendingSave();
    const activeLockVersion = updatedState ? updatedState.lockVersion : currentDocState.lockVersion;
    
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
            }
          },
          onError: (err) => {
            alert(`重写失败: ${err.message}`);
            queryClient.invalidateQueries({ queryKey: ["document", selectedSourceItemId] });
          },
        },
      );
    } finally {
      setIsGenerating(false);
      setRewriteInstruction("");
    }
  };

  const hasSelection = editor ? editor.state.selection.from !== editor.state.selection.to : false;

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
      {/* ── 1. 帖子原文元数据信息栏 (置于最顶端，在 Tab 选项卡上面) ── */}
      {docState?.sourceItem && (
        <div className="border-b bg-zinc-50/50 dark:bg-zinc-950/20 p-4 shrink-0">
          <div className="space-y-2.5 rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950/40 p-3.5 shadow-sm">
            {/* 标题行：Tag + 标题 (单行截断) + 查看原文按钮 */}
            <div className="flex items-center justify-between gap-4 min-w-0">
              <div className="flex items-center gap-2 min-w-0 flex-1">
                {docState.sourceItem.platform && (
                  <Badge variant="outline" className="text-[10px] uppercase font-bold text-indigo-600 border-indigo-600/30 dark:text-indigo-400 dark:border-indigo-400/30 shrink-0">
                    {docState.sourceItem.platform}
                  </Badge>
                )}
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                  {docState.sourceItem.title}
                </h3>
              </div>
              
              {docState.sourceItem.url && (
                <Button asChild variant="outline" size="sm" className="h-7 text-xs gap-1.5 shrink-0 border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 hover:bg-zinc-50 dark:hover:bg-zinc-900">
                  <a href={docState.sourceItem.url} target="_blank" rel="noopener noreferrer">
                    <Globe className="h-3.5 w-3.5 text-zinc-500" />
                    查看原文
                  </a>
                </Button>
              )}
            </div>

            {/* 作者信息 */}
            {docState.sourceItem.author && (
              <div className="text-[11px] text-muted-foreground">
                作者: {docState.sourceItem.author}
              </div>
            )}

            {/* 原文内容 (直铺，最大 3 行，无滚动条) */}
            {docState.sourceItem.content && (
              <p className="text-xs text-zinc-600 dark:text-zinc-400 leading-relaxed line-clamp-3 whitespace-pre-wrap">
                {docState.sourceItem.content}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── 2. 顶部 Tab 切换 ── */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="editor" className="gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              编辑器
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-1.5">
              <History className="h-3.5 w-3.5" />
              版本 ({versions.length})
            </TabsTrigger>
          </TabsList>
        </Tabs>

        {/* 操作区与状态指示 */}
        <div className="flex items-center gap-2.5">


          {/* 复制按钮 */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            disabled={!hasContent}
            className="h-7 px-2 text-xs gap-1 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-400"
          >
            {copied ? (
              <>
                <Check className="h-3.5 w-3.5 text-green-500" />
                <span>已复制</span>
              </>
            ) : (
              <>
                <Copy className="h-3.5 w-3.5" />
                <span>复制</span>
              </>
            )}
          </Button>

          <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-800" />

          {/* 保存状态指示 */}
          <span className="flex items-center gap-1 text-[10px] text-muted-foreground select-none shrink-0">
            {autoSaveMutation.isPending ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="h-3 w-3" />
                已保存
              </>
            )}
          </span>

          <span className="h-3.5 w-px bg-zinc-200 dark:bg-zinc-800" />

          {/* 关闭/收起编辑器面板 */}
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

      {activeTab === "editor" ? (
        <EditorTabContent
          editor={editor}
          isGenerating={isGenerating}
          rewriteInstruction={rewriteInstruction}
          setRewriteInstruction={setRewriteInstruction}
          onRewrite={handleFullRewrite}
          selectedStyles={selectedStyles}
          setSelectedStyles={setSelectedStyles}
          wordCount={wordCount}
          onWordCountChange={setWordCount}
        />
      ) : (
        <HistoryTabContent
          versions={versions}
          onRestore={(versionId) => {
            if (confirm("确认恢复此版本？当前编辑中的内容将被覆盖。")) {
              restoreVersionMutation.mutate(versionId);
            }
          }}
        />
      )}
    </aside>
  );
}

function EditorTabContent({
  editor,
  isGenerating,
  rewriteInstruction,
  setRewriteInstruction,
  onRewrite,
  selectedStyles,
  setSelectedStyles,
  wordCount,
  onWordCountChange,
}: {
  editor: ReturnType<typeof useEditor>;
  isGenerating: boolean;
  rewriteInstruction: string;
  setRewriteInstruction: (v: string) => void;
  onRewrite: () => void;
  selectedStyles: string[];
  setSelectedStyles: (styles: string[]) => void;
  wordCount: number;
  onWordCountChange: (v: number) => void;
}) {
  const hasContent = !!editor?.getText()?.trim();

  return (
    <div className="relative flex flex-1 flex-col min-h-0 overflow-hidden">
      {/* Tiptap 编辑区 */}
      <ScrollArea className="flex-1 min-h-0 p-4">


        <EditorContent editor={editor} className="prose dark:prose-invert max-w-none outline-none min-h-[300px]" />
      </ScrollArea>

      {/* 居中加载浮层 */}
      {isGenerating && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-white/40 dark:bg-zinc-950/40 backdrop-blur-[1px] select-none pointer-events-auto">
          <div className="flex items-center gap-2.5 rounded-xl border border-indigo-100 dark:border-indigo-900 bg-white/95 dark:bg-zinc-900/95 px-5 py-3.5 shadow-xl">
            <Loader2 className="h-4.5 w-4.5 animate-spin text-indigo-600 dark:text-indigo-400" />
            <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 animate-pulse">
              AI 正在为您撰写/优化中，请稍候...
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
        />
      </div>
    </div>
  );
}

// ── 版本历史 Tab 内容 ─────────────────────────────────────────────

function HistoryTabContent({
  versions,
  onRestore,
}: {
  versions: VersionSummary[];
  onRestore: (versionId: string) => void;
}) {
  if (versions.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-xs text-muted-foreground">
        无任何历史版本快照
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1 min-h-0 p-4">
      <div className="space-y-3">
        {versions.map((ver) => (
          <Card key={ver.id}>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between">
                <span className="text-sm font-bold">版本 {ver.versionNumber}</span>
                <span className="text-[10px] text-muted-foreground">
                  {new Date(ver.createdAt).toLocaleString()}
                </span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">类型:</span>
                  <Badge variant="secondary" className="text-[10px] uppercase">
                    {ver.versionType}
                  </Badge>
                </div>
                {ver.instruction && (
                  <p className="text-xs text-muted-foreground">
                    指令: <span className="italic">"{ver.instruction}"</span>
                  </p>
                )}
                {(ver.provider || ver.model) && (
                  <p className="text-[10px] text-muted-foreground">
                    模型: {ver.provider}/{ver.model}
                  </p>
                )}
              </div>
              <div className="flex justify-end">
                <Button variant="outline" size="sm" onClick={() => onRestore(ver.id)}>
                  <Undo2 className="h-3 w-3" />
                  恢复此版本
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </ScrollArea>
  );
}
