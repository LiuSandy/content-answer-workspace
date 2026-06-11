import { useWorkspaceStore } from "@/store/workspace-store";
import {
  ArrowUpRight,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  FileDown,
  Layers,
  LoaderCircle,
  Maximize2,
  RefreshCcw,
  Save,
  Search,
  Sparkles,
} from "lucide-react";
import { useDeferredValue, useMemo, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuList,
} from "@/components/ui/navigation-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { maxCollectCount, supportedPlatforms } from "./defaults";
import { useWorkspace } from "./use-workspace";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";

type EntryMode = "import" | "collect";
type WorkspaceState = ReturnType<typeof useWorkspace>;

function useWorkspaceOutlet() {
  return useOutletContext<WorkspaceState>();
}

const topNavItems: Array<{ id: EntryMode; label: string }> = [
  { id: "import", label: "URL 导入回答" },
  { id: "collect", label: "主题采集" },
];

// ──────────────────────────────────────────────────────────
// Topbar
// ──────────────────────────────────────────────────────────

function WorkspaceTopbar() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-[52px] w-full max-w-[1800px] items-center gap-6 px-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] bg-slate-900 text-[10px] font-bold tracking-tight text-white">
            CW
          </div>
          <div className="leading-none">
            <div className="text-[13px] font-semibold text-slate-900">内容工作台</div>
            <div className="mt-[1px] text-[10px] font-medium text-slate-400">Content Workspace</div>
          </div>
        </div>

        <Separator orientation="vertical" className="h-4" />

        <NavigationMenu>
          <NavigationMenuList className="gap-0">
            {topNavItems.map((item) => (
              <NavigationMenuItem key={item.id}>
                <NavLink
                  to={`/${item.id}`}
                  end
                  className={({ isActive }) =>
                    cn(
                      "inline-flex h-[52px] items-center border-b-2 border-transparent px-3 text-[13px] font-medium text-slate-500 transition-all hover:text-slate-800",
                      isActive && "border-slate-900 font-semibold text-slate-900",
                    )
                  }
                >
                  {item.label}
                </NavLink>
              </NavigationMenuItem>
            ))}
          </NavigationMenuList>
        </NavigationMenu>
      </div>
    </header>
  );
}

// ──────────────────────────────────────────────────────────
// Shared: Section panel header (no card, just a labeled area)
// ──────────────────────────────────────────────────────────

function PanelSection({
  label,
  action,
  children,
  className,
}: {
  label: string;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</span>
        {action}
      </div>
      {children}
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Shared: Status dot indicator (inline status bar)
// ──────────────────────────────────────────────────────────

type StatusLevel = "idle" | "running" | "done" | "warn" | "error";

function StatusDot({
  label,
  status,
  value,
}: {
  label: string;
  status: StatusLevel;
  value: string;
}) {
  const dotClass: Record<StatusLevel, string> = {
    idle: "bg-slate-300",
    running: "bg-blue-500 animate-pulse",
    done: "bg-emerald-500",
    warn: "bg-amber-400",
    error: "bg-red-500",
  };
  const valueClass: Record<StatusLevel, string> = {
    idle: "text-slate-400",
    running: "text-blue-600",
    done: "text-emerald-600",
    warn: "text-amber-600",
    error: "text-red-600",
  };

  return (
    <div className="flex items-center gap-1.5">
      <span className={cn("h-[6px] w-[6px] rounded-full shrink-0", dotClass[status])} />
      <span className="text-[11px] font-medium text-slate-500">{label}</span>
      <span className={cn("text-[11px] font-semibold", valueClass[status])}>{value}</span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Full-screen prompt editor dialog
// ──────────────────────────────────────────────────────────

function PromptExpandDialog({
  open,
  onOpenChange,
  label,
  value,
  onChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[80vh] max-w-3xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-slate-200 px-5 py-4">
          <DialogTitle className="text-[14px] font-semibold text-slate-800">
            编辑 · {label}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-hidden p-4">
          <Textarea
            autoFocus
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="h-full min-h-0 resize-none rounded-md border-slate-200 bg-white text-[13px] leading-relaxed shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
          />
        </div>
        <DialogFooter className="border-t border-slate-200 px-5 py-3">
          <span className="mr-auto text-[11px] text-slate-400">
            {value.length} 字符
          </span>
          <Button
            size="sm"
            className="h-8 rounded-md bg-slate-900 px-4 text-[12px] font-medium hover:bg-slate-800"
            onClick={() => onOpenChange(false)}
          >
            完成
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ──────────────────────────────────────────────────────────
// Prompt field with expand button
// ──────────────────────────────────────────────────────────

function PromptField({
  id,
  label,
  value,
  onChange,
  rows = 4,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
}) {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label htmlFor={id} className="text-[11px] font-medium text-slate-600">
            {label}
          </Label>
          <button
            type="button"
            title="全屏编辑"
            onClick={() => setDialogOpen(true)}
            className="flex items-center gap-1 rounded px-1 py-0.5 text-[10px] font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <Maximize2 className="h-3 w-3" />
            全屏
          </button>
        </div>
        <Textarea
          id={id}
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="resize-none rounded-md border-slate-200 bg-white text-[12px] leading-relaxed shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
        />
      </div>

      <PromptExpandDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        label={label}
        value={value}
        onChange={onChange}
      />
    </>
  );
}

// ──────────────────────────────────────────────────────────
// Prompt config (left panel reusable)
// ──────────────────────────────────────────────────────────

function PromptConfigPanel({
  answerStyle,
  systemPrompt,
  generationPrompt,
  onAnswerStyleChange,
  onSystemPromptChange,
  onGenerationPromptChange,
}: {
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  onAnswerStyleChange: (value: string) => void;
  onSystemPromptChange: (value: string) => void;
  onGenerationPromptChange: (value: string) => void;
}) {
  return (
    <PanelSection label="提示词配置">
      <div className="space-y-3">
        <PromptField
          id="topic-system-prompt"
          label="主题提示词"
          value={systemPrompt}
          onChange={onSystemPromptChange}
          rows={5}
        />
        <PromptField
          id="answer-style"
          label="回答风格"
          value={answerStyle}
          onChange={onAnswerStyleChange}
          rows={3}
        />
        <PromptField
          id="generation-prompt"
          label="全局生成规则"
          value={generationPrompt}
          onChange={onGenerationPromptChange}
          rows={6}
        />
      </div>
    </PanelSection>
  );
}

// ──────────────────────────────────────────────────────────
// Question row (collect page)
// ──────────────────────────────────────────────────────────

function QuestionRow({
  question,
  active,
  onSelect,
  isGenerating,
}: {
  question: WorkspaceState["questions"][number];
  active: boolean;
  onSelect: (questionId: string) => void;
  isGenerating: boolean;
}) {
  const generated = Boolean(question.answer?.trim());

  return (
    <button
      type="button"
      onClick={() => onSelect(question.id)}
      className={cn(
        "w-full rounded-md border bg-white px-3 py-2.5 text-left transition-all hover:border-slate-300 hover:bg-slate-50/70",
        active
          ? "border-blue-500 bg-blue-50/40 ring-1 ring-blue-500/20 hover:bg-blue-50/40"
          : "border-slate-200",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center rounded-[4px] px-1.5 py-[1px] text-[10px] font-semibold",
                generated
                  ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  : "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
              )}
            >
              {generated ? "已生成" : "待生成"}
            </span>
            <span className="text-[11px] text-slate-400">
              {question.platform ?? "zhihu"} · {question.answerCount} 个回答
            </span>
            {question.updatedTime ? (
              <span className="text-[11px] text-slate-400">{question.updatedTime}</span>
            ) : null}
          </div>

          <div className="line-clamp-2 text-[13px] font-semibold leading-[1.5] text-slate-800">
            {question.title}
          </div>

          {question.excerpt ? (
            <div className="line-clamp-1 text-[12px] text-slate-500">{question.excerpt}</div>
          ) : null}

          <div className="flex items-center gap-1.5">
            <span className="rounded-[4px] bg-slate-100 px-1.5 py-[1px] text-[10px] font-medium text-slate-500">
              {question.topic || "未分类"}
            </span>
            {isGenerating && (
              <span className="flex items-center gap-1 text-[11px] font-medium text-blue-600">
                <LoaderCircle className="h-3 w-3 animate-spin" />
                生成中
              </span>
            )}
          </div>
        </div>

        <span
          className={cn(
            "mt-1 h-[7px] w-[7px] shrink-0 rounded-full",
            generated ? "bg-emerald-400" : "bg-amber-300",
          )}
        />
      </div>
    </button>
  );
}

// ──────────────────────────────────────────────────────────
// Questions panel (collect page middle column)
// ──────────────────────────────────────────────────────────

function QuestionsPanel({
  questions,
  selectedQuestionId,
  selectQuestion,
  isCollecting,
  isGeneratingOne,
}: {
  questions: WorkspaceState["questions"];
  selectedQuestionId: string | null;
  selectQuestion: (questionId: string | null) => void;
  isCollecting: boolean;
  isGeneratingOne: (questionId: string) => boolean;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const deferredQuery = useDeferredValue(query);

  const filteredQuestions = useMemo(() => {
    const keyword = deferredQuery.trim().toLowerCase();
    if (!keyword) return questions;
    return questions.filter((q) => {
      const haystack = `${q.title} ${q.excerpt} ${q.topic}`.toLowerCase();
      return haystack.includes(keyword);
    });
  }, [questions, deferredQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredQuestions.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * pageSize;
  const pageEnd = pageStart + pageSize;
  const pagedQuestions = filteredQuestions.slice(pageStart, pageEnd);
  const visibleStart = filteredQuestions.length ? pageStart + 1 : 0;
  const visibleEnd = Math.min(pageEnd, filteredQuestions.length);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <PanelSection
        label={`问题列表 ${questions.length ? `(${questions.length})` : ""}`}
        action={
          <Button variant="ghost" size="sm" className="h-6 gap-1 px-2 text-[11px] text-slate-500 hover:text-slate-700">
            <FileDown className="h-3 w-3" />
            导出
          </Button>
        }
      >
        <div className="space-y-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(1); }}
              placeholder="搜索标题、摘要、关键词"
              className="h-8 rounded-md border-slate-200 bg-white pl-8 text-[12px] shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
            />
          </div>
          <div className="flex gap-1">
            {["全部", "未生成", "已生成"].map((label) => (
              <button
                key={label}
                type="button"
                className="rounded-[4px] bg-slate-100 px-2 py-[3px] text-[11px] font-medium text-slate-600 transition-colors hover:bg-slate-200 first:bg-slate-800 first:text-white"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </PanelSection>

      <ScrollArea className="flex-1 pr-1" style={{ height: "calc(100vh - 400px)", minHeight: "360px" }}>
        <div className="space-y-2">
          {isCollecting && !questions.length ? (
            <EmptySlot message="正在采集问题，完成后结果将显示在这里。" />
          ) : pagedQuestions.length ? (
            pagedQuestions.map((q) => (
              <QuestionRow
                key={q.id}
                question={q}
                active={q.id === selectedQuestionId}
                onSelect={selectQuestion}
                isGenerating={isGeneratingOne(q.id)}
              />
            ))
          ) : (
            <EmptySlot message="没有匹配的问题结果。" />
          )}
        </div>
      </ScrollArea>

      <div className="flex items-center justify-between gap-2 border-t border-slate-200 pt-2">
        <span className="text-[11px] text-slate-400">
          {filteredQuestions.length ? `${visibleStart}–${visibleEnd} / ${filteredQuestions.length}` : "0 / 0"}
        </span>
        <div className="flex items-center gap-1.5">
          <Select
            value={String(pageSize)}
            onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}
          >
            <SelectTrigger className="h-7 w-[90px] rounded-md border-slate-200 bg-white text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {[10, 20, 50].map((s) => (
                <SelectItem key={s} value={String(s)} className="text-[12px]">
                  每页 {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="h-7 w-7 rounded-md border-slate-200 bg-white"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <span className="min-w-[36px] text-center text-[11px] font-medium text-slate-500">
            {currentPage}/{totalPages}
          </span>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
            className="h-7 w-7 rounded-md border-slate-200 bg-white"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Answer panel (shared between pages)
// ──────────────────────────────────────────────────────────

function QuestionBrief({
  question,
  onOpenSource,
}: {
  question: WorkspaceState["questions"][number];
  onOpenSource: () => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3.5 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-[4px] bg-blue-50 px-1.5 py-[1px] text-[10px] font-semibold text-blue-700 ring-1 ring-blue-200">
          {question.topic || "知乎题目"}
        </span>
        <span className="text-[11px] text-slate-400">{question.answerCount} 个回答</span>
        {question.updatedTime ? (
          <span className="text-[11px] text-slate-400">{question.updatedTime}</span>
        ) : null}
        <button
          type="button"
          onClick={onOpenSource}
          className="ml-auto flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-700"
        >
          打开原链接
          <ExternalLink className="h-3 w-3" />
        </button>
      </div>
      <div className="text-[14px] font-semibold leading-snug text-slate-900">{question.title}</div>
      {question.excerpt ? (
        <p className="mt-1.5 text-[12px] leading-relaxed text-slate-500">{question.excerpt}</p>
      ) : null}
    </div>
  );
}

function AnswerPanel({
  question,
  onGenerateOne,
  onSave,
  setQuestionAnswer,
}: {
  question: WorkspaceState["questions"][number] | null;
  onGenerateOne: (item: WorkspaceState["questions"][number]) => void;
  onSave: () => void;
  setQuestionAnswer: (questionId: string, answer: string) => void;
}) {
  const [isCopied, setIsCopied] = useState(false);

  async function copyAnswer() {
    if (!question?.answer?.trim()) return;
    await navigator.clipboard.writeText(question.answer);
    setIsCopied(true);
    window.setTimeout(() => setIsCopied(false), 1500);
  }

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <PanelSection label="回答工作区" className="flex-1" />
        {question && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 rounded-md border-slate-200 px-2.5 text-[12px] font-medium"
              onClick={copyAnswer}
              disabled={!question.answer?.trim()}
            >
              {isCopied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
              {isCopied ? "已复制" : "复制"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1.5 rounded-md border-slate-200 px-2.5 text-[12px] font-medium"
              onClick={() => onGenerateOne(question)}
            >
              <RefreshCcw className="h-3 w-3" />
              重新生成
            </Button>
            <Button
              size="sm"
              className="h-7 gap-1.5 rounded-md bg-slate-900 px-3 text-[12px] font-medium hover:bg-slate-800"
              onClick={() => onGenerateOne(question)}
            >
              <Sparkles className="h-3 w-3" />
              AI 生成
            </Button>
          </div>
        )}
      </div>

      {!question ? (
        <div className="flex min-h-[400px] flex-col items-center justify-center gap-3 rounded-md border border-dashed border-slate-200 bg-slate-50/50">
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
          <QuestionBrief question={question} onOpenSource={() => window.open(question.url, "_blank", "noreferrer")} />

          {question.images?.length ? (
            <div className="grid gap-2 md:grid-cols-2">
              {question.images.map((imgUrl, i) => (
                <figure
                  key={`${question.id}-img-${i}`}
                  className="overflow-hidden rounded-md border border-slate-200 bg-slate-50"
                >
                  <img
                    className="h-40 w-full object-cover"
                    src={imgUrl}
                    alt={question.imagePrompts?.[i] || `${question.title} 配图 ${i + 1}`}
                  />
                  {question.imagePrompts?.[i] ? (
                    <figcaption className="border-t border-slate-200 px-2.5 py-1.5 text-[11px] text-slate-500">
                      {question.imagePrompts[i]}
                    </figcaption>
                  ) : null}
                </figure>
              ))}
            </div>
          ) : null}

          <MarkdownEditor
            className="min-h-[320px] rounded-md border border-slate-200 bg-white"
            placeholder="点击 AI 生成 按钮自动撰写，或直接手工编辑内容。"
            value={question.answer || ""}
            onChange={(v) => setQuestionAnswer(question.id, v)}
          />
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Empty slot
// ──────────────────────────────────────────────────────────

function EmptySlot({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-dashed border-slate-200 bg-slate-50/60 px-3 py-3.5 text-[12px] text-slate-400">
      {message}
    </div>
  );
}

// ──────────────────────────────────────────────────────────
// Collect Page
// ──────────────────────────────────────────────────────────

function CollectPage() {
  const workspace = useWorkspaceOutlet();
  const { saveState, statusMessage } = useWorkspaceStore();
  const {
    selectedPlatform,
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    generationPrompt,
    maxPushCount,
    selectPlatform,
    selectTopic,
    setMaxPushCount,
    collectQuestions,
    generateOneAnswer,
    saveSession,
    setQuestionAnswer,
    isCollecting,
    isGeneratingOne,
  } = workspace;

  const currentQuestion = questions.find((q) => q.id === selectedQuestionId) ?? null;
  const collectKeywords = selectedTopic?.expandedHints ?? [];
  const answeredCount = questions.filter((q) => q.answer?.trim()).length;

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50/60 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100">
            <Layers className="h-3.5 w-3.5 text-slate-600" />
          </div>
          <div>
            <span className="text-[14px] font-semibold text-slate-800">主题采集工作台</span>
            <span className="ml-2 text-[12px] text-slate-400">按主题采集问题，筛选并批量生成回答</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {questions.length > 0 && (
            <span className="text-[12px] font-medium text-slate-500">
              {answeredCount}/{questions.length} 已生成
            </span>
          )}
          <Badge variant="secondary" className="rounded-[6px] px-2 py-0.5 text-[11px] font-semibold">
            {questions.length} 个问题
          </Badge>
        </div>
      </div>

      {/* Action bar */}
      <div className="border-b border-slate-200 bg-white px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5">
            <Label className="shrink-0 text-[11px] font-medium text-slate-500">主题</Label>
            <Select
              value={selectedTopic?.id ?? ""}
              onValueChange={(v) => {
                const t = presetTopics.find((item) => item.id === v) ?? null;
                selectTopic(t);
              }}
            >
              <SelectTrigger className="h-8 w-[180px] rounded-md border-slate-200 bg-white text-[12px]">
                <SelectValue placeholder="选择主题" />
              </SelectTrigger>
              <SelectContent>
                {presetTopics.map((t) => (
                  <SelectItem key={t.id} value={t.id} className="text-[12px]">
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-1.5">
            <Label className="shrink-0 text-[11px] font-medium text-slate-500">平台</Label>
            <Select value={selectedPlatform} onValueChange={(v) => selectPlatform(v as typeof selectedPlatform)}>
              <SelectTrigger className="h-8 w-[120px] rounded-md border-slate-200 bg-white text-[12px]">
                <SelectValue placeholder="选择平台" />
              </SelectTrigger>
              <SelectContent>
                {supportedPlatforms.map((p) => (
                  <SelectItem key={p.id} value={p.id} className="text-[12px]">
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-1.5">
            <Label className="shrink-0 text-[11px] font-medium text-slate-500">上限</Label>
            <Input
              type="number"
              min={1}
              max={maxCollectCount}
              value={maxPushCount}
              onChange={(e) => {
                const v = Number(e.target.value) || 1;
                setMaxPushCount(Math.min(maxCollectCount, Math.max(1, v)));
              }}
              className="h-8 w-[72px] rounded-md border-slate-200 bg-white text-[12px] shadow-none"
            />
          </div>

          <div className="flex-1" />

          <Button
            size="sm"
            className="h-8 gap-1.5 rounded-md bg-slate-900 px-3.5 text-[12px] font-medium hover:bg-slate-800"
            onClick={collectQuestions}
            disabled={isCollecting}
          >
            {isCollecting ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Search className="h-3.5 w-3.5" />
            )}
            {isCollecting ? "采集中…" : "开始采集"}
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 rounded-md border-slate-200 px-3 text-[12px] font-medium"
            onClick={saveSession}
          >
            <Save className="h-3.5 w-3.5" />
            保存结果
          </Button>
        </div>

        {/* Inline status row */}
        {(questions.length > 0 || isCollecting) && (
          <div className="mt-2 flex flex-wrap items-center gap-4">
            <StatusDot
              label="采集"
              status={isCollecting ? "running" : questions.length > 0 ? "done" : "idle"}
              value={isCollecting ? "进行中" : questions.length > 0 ? `${questions.length} 条` : "待执行"}
            />
            <StatusDot
              label="已生成"
              status={answeredCount === questions.length && questions.length > 0 ? "done" : answeredCount > 0 ? "warn" : "idle"}
              value={questions.length > 0 ? `${answeredCount}/${questions.length}` : "—"}
            />
            <StatusDot
              label="保存"
              status={saveState === "saved" ? "done" : saveState === "saving" ? "running" : saveState === "error" ? "error" : "idle"}
              value={saveState === "saved" ? "已保存" : saveState === "saving" ? "保存中" : "未保存"}
            />
            {statusMessage && (
              <span className="ml-auto text-[11px] text-slate-400">{statusMessage}</span>
            )}
          </div>
        )}
      </div>

      {/* Three-column body */}
      <div className="grid xl:grid-cols-[280px_minmax(0,1.3fr)_minmax(0,1fr)]">
        {/* Left: config */}
        <div className="border-r border-slate-200 p-4">
          <div className="space-y-5">
            {collectKeywords.length > 0 && (
              <PanelSection label="扩展检索词">
                <div className="flex flex-wrap gap-1">
                  {collectKeywords.map((kw) => (
                    <span
                      key={kw}
                      className="rounded-[4px] bg-slate-100 px-1.5 py-[2px] text-[11px] font-medium text-slate-600"
                    >
                      {kw}
                    </span>
                  ))}
                </div>
              </PanelSection>
            )}

            {selectedTopic?.name && (
              <PanelSection label="当前主题">
                <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
                  <span className="text-[13px] font-semibold text-slate-800">{selectedTopic.name}</span>
                </div>
              </PanelSection>
            )}

            <PromptConfigPanel
              answerStyle={answerStyle}
              systemPrompt={systemPrompt}
              generationPrompt={generationPrompt}
              onAnswerStyleChange={workspace.setAnswerStyle}
              onSystemPromptChange={workspace.setSystemPrompt}
              onGenerationPromptChange={workspace.setGenerationPrompt}
            />
          </div>
        </div>

        {/* Middle: question list */}
        <div className="border-r border-slate-200 p-4">
          <QuestionsPanel
            questions={questions}
            selectedQuestionId={selectedQuestionId}
            selectQuestion={workspace.selectQuestion}
            isCollecting={isCollecting}
            isGeneratingOne={isGeneratingOne}
          />
        </div>

        {/* Right: answer workspace */}
        <div className="p-4">
          <AnswerPanel
            question={currentQuestion}
            onGenerateOne={generateOneAnswer}
            onSave={saveSession}
            setQuestionAnswer={setQuestionAnswer}
          />
        </div>
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────
// Import Page
// ──────────────────────────────────────────────────────────

function ImportPage() {
  const workspace = useWorkspaceOutlet();
  const { saveState, statusMessage } = useWorkspaceStore();
  const {
    selectedPlatform,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    generationPrompt,
    selectPlatform,
    importQuestionByUrl,
    isImportingQuestionUrl,
    saveSession,
    generateOneAnswer,
    setQuestionAnswer,
    setAnswerStyle,
    setSystemPrompt,
    setGenerationPrompt,
  } = workspace;
  const [questionUrl, setQuestionUrl] = useState("");
  const currentQuestion = questions.find((q) => q.id === selectedQuestionId) ?? null;

  const urlStatus: StatusLevel = isImportingQuestionUrl ? "running" : currentQuestion ? "done" : "idle";
  const answerStatus: StatusLevel = currentQuestion?.answer?.trim() ? "done" : isImportingQuestionUrl ? "idle" : currentQuestion ? "warn" : "idle";
  const saveStatus: StatusLevel = saveState === "saved" ? "done" : saveState === "saving" ? "running" : saveState === "error" ? "error" : "idle";

  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 border-b border-slate-200 bg-slate-50/60 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100">
            <ArrowUpRight className="h-3.5 w-3.5 text-slate-600" />
          </div>
          <div>
            <span className="text-[14px] font-semibold text-slate-800">URL 导入回答</span>
            <span className="ml-2 text-[12px] text-slate-400">粘贴问题链接，解析单题信息，生成并编辑回答</span>
          </div>
        </div>
        <Badge variant="secondary" className="rounded-[6px] px-2 py-0.5 text-[11px] font-semibold">
          最近导入 {questions.length} 条
        </Badge>
      </div>

      {/* Action bar */}
      <div className="border-b border-slate-200 bg-white px-5 py-3">
        <div className="flex items-center gap-2">
          <Input
            value={questionUrl}
            onChange={(e) => setQuestionUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && questionUrl.trim() && !isImportingQuestionUrl) {
                importQuestionByUrl(questionUrl.trim());
              }
            }}
            placeholder="粘贴知乎问题链接，例如 https://www.zhihu.com/question/..."
            className="h-8 flex-1 rounded-md border-slate-200 bg-white text-[12px] shadow-none focus-visible:ring-1 focus-visible:ring-blue-500"
          />
          <Select value={selectedPlatform} onValueChange={(v) => selectPlatform(v as typeof selectedPlatform)}>
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
            disabled={!questionUrl.trim() || isImportingQuestionUrl}
            onClick={() => importQuestionByUrl(questionUrl.trim())}
          >
            {isImportingQuestionUrl ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <ArrowUpRight className="h-3.5 w-3.5" />
            )}
            {isImportingQuestionUrl ? "解析中…" : "导入问题"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 rounded-md border-slate-200 px-3 text-[12px] font-medium"
            onClick={saveSession}
          >
            <Save className="h-3.5 w-3.5" />
            保存
          </Button>
        </div>

        {/* Inline status — moved from left panel */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <StatusDot label="URL 解析" status={urlStatus} value={isImportingQuestionUrl ? "解析中" : currentQuestion ? "已完成" : "待检查"} />
          <StatusDot label="回答生成" status={answerStatus} value={currentQuestion?.answer?.trim() ? "已完成" : "待执行"} />
          <StatusDot label="本地保存" status={saveStatus} value={saveState === "saved" ? "已保存" : saveState === "saving" ? "保存中" : "未保存"} />
          {statusMessage && (
            <span className="ml-auto text-[11px] text-slate-400">{statusMessage}</span>
          )}
        </div>
      </div>

      {/* Two-column body: left = config, right = answer */}
      <div className="grid xl:grid-cols-[320px_minmax(0,1fr)]">
        {/* Left: config params only */}
        <div className="border-r border-slate-200 p-4">
          <div className="space-y-5">
            {/* Recent imports */}
            <PanelSection label="最近导入">
              {questions.length > 0 ? (
                <div className="space-y-1.5">
                  {questions.slice(0, 5).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => workspace.selectQuestion(item.id)}
                      className={cn(
                        "group w-full rounded-md border px-3 py-2 text-left transition-colors hover:bg-slate-50",
                        item.id === selectedQuestionId
                          ? "border-blue-400 bg-blue-50/40"
                          : "border-slate-200 bg-white",
                      )}
                    >
                      <div className="line-clamp-1 text-[12px] font-medium text-slate-800">
                        {item.title}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1.5">
                        <span
                          className={cn(
                            "inline-block h-[5px] w-[5px] rounded-full",
                            item.answer?.trim() ? "bg-emerald-400" : "bg-amber-300",
                          )}
                        />
                        <span className="text-[10px] text-slate-400">
                          {item.platform ?? "zhihu"} · {item.answer?.trim() ? "已生成回答" : "未生成"}
                        </span>
                      </div>
                    </button>
                  ))}
                  {questions.length > 5 && (
                    <div className="text-[11px] text-slate-400">
                      另有 {questions.length - 5} 条导入记录
                    </div>
                  )}
                </div>
              ) : (
                <EmptySlot message="暂无导入记录。粘贴问题链接后开始。" />
              )}
            </PanelSection>

            <Separator className="bg-slate-100" />

            {/* Prompt config */}
            <PromptConfigPanel
              answerStyle={answerStyle}
              systemPrompt={systemPrompt}
              generationPrompt={generationPrompt}
              onAnswerStyleChange={setAnswerStyle}
              onSystemPromptChange={setSystemPrompt}
              onGenerationPromptChange={setGenerationPrompt}
            />
          </div>
        </div>

        {/* Right: answer workspace */}
        <div className="p-4">
          <AnswerPanel
            question={currentQuestion}
            onGenerateOne={generateOneAnswer}
            onSave={saveSession}
            setQuestionAnswer={setQuestionAnswer}
          />
        </div>
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────
// Layout root
// ──────────────────────────────────────────────────────────

export function WorkspaceLayout() {
  const workspace = useWorkspace();

  return (
    <div className="min-h-screen bg-[#EFF2F7] text-slate-900">
      <WorkspaceTopbar />
      <main className="mx-auto w-full max-w-[1800px] px-4 pb-6 pt-4 sm:px-5">
        <Outlet context={workspace} />
      </main>
    </div>
  );
}

export { CollectPage, ImportPage };
