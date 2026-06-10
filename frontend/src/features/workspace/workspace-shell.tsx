import {
  ArrowUpRight,
  Bot,
  Check,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileDown,
  LoaderCircle,
  MessageSquareQuote,
  RefreshCcw,
  Save,
  Search,
  Sparkles,
} from "lucide-react";
import { useDeferredValue, useMemo, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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

function WorkspaceTopbar() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-[56px] w-full max-w-[1800px] items-center gap-8 px-4 sm:px-6 lg:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-[11px] font-extrabold tracking-tight text-white shadow-[0_8px_16px_rgba(37,99,235,0.16)]">
            CW
          </div>
          <div className="leading-none">
            <div className="text-[15px] font-extrabold tracking-tight text-slate-900">内容工作台</div>
            <div className="mt-0.5 text-[10px] font-semibold text-slate-500">Research and Answers</div>
          </div>
        </div>

        <NavigationMenu className="flex-1">
          <NavigationMenuList className="gap-8">
            {topNavItems.map((item) => (
              <NavigationMenuItem key={item.id}>
                <NavLink
                  to={`/${item.id}`}
                  end
                  className={({ isActive }) =>
                    cn(
                      "inline-flex h-8 shrink-0 items-center whitespace-nowrap border-b-2 border-transparent px-0 text-[14px] font-semibold text-slate-500 transition-colors hover:text-blue-700",
                      isActive && "border-blue-600 font-extrabold text-blue-700",
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

function SectionCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden rounded-xl border-slate-200/80 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.05)]", className)}>
      <CardHeader className="flex-row items-start justify-between gap-3 border-b border-slate-200/70 px-5 py-4">
        <div className="space-y-1">
          <CardTitle className="text-[0.9rem] font-extrabold tracking-tight text-slate-900">{title}</CardTitle>
          {description ? <CardDescription className="text-[0.76rem] leading-5 text-slate-500">{description}</CardDescription> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </CardHeader>
      <CardContent className="px-5 py-4">{children}</CardContent>
    </Card>
  );
}

function MetricTile({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3.5">
      <div className="flex items-start justify-between gap-2.5">
        <div className="space-y-0.5">
          <div className="text-[0.72rem] font-semibold text-slate-500">{label}</div>
          <div className="text-[0.94rem] font-extrabold tracking-tight text-slate-900">{value}</div>
        </div>
        {icon ? <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-slate-500 shadow-sm">{icon}</div> : null}
      </div>
    </div>
  );
}

function StatusRow({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-50 px-3 py-2 text-sm">
      <span className="text-slate-600">{label}</span>
      <span className={cn("font-semibold text-slate-900", valueClassName)}>{value}</span>
    </div>
  );
}

function PromptConfigSection({
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
    <SectionCard
      title="提示词配置"
      description="主题提示词、回答风格和全局生成规则。"
      className="h-full"
    >
      <div className="space-y-3">
        <div className="space-y-2">
          <Label htmlFor="topic-system-prompt" className="text-[0.82rem] font-semibold text-slate-700">
            主题提示词
          </Label>
          <Textarea
            id="topic-system-prompt"
            rows={6}
            value={systemPrompt}
            onChange={(event) => onSystemPromptChange(event.target.value)}
            className="min-h-[128px] rounded-xl border-slate-200 bg-white text-sm shadow-none"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="answer-style" className="text-[0.82rem] font-semibold text-slate-700">
            回答风格
          </Label>
          <Textarea
            id="answer-style"
            rows={4}
            value={answerStyle}
            onChange={(event) => onAnswerStyleChange(event.target.value)}
            className="min-h-[96px] rounded-xl border-slate-200 bg-white text-sm shadow-none"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="generation-prompt" className="text-[0.82rem] font-semibold text-slate-700">
            全局生成规则
          </Label>
          <Textarea
            id="generation-prompt"
            rows={8}
            value={generationPrompt}
            onChange={(event) => onGenerationPromptChange(event.target.value)}
            className="min-h-[156px] rounded-xl border-slate-200 bg-white text-sm shadow-none"
          />
        </div>
      </div>
    </SectionCard>
  );
}

function WorkspacePulsePanel({
  questions,
  selectedTopicName,
  keywords,
  saveState,
  statusMessage,
}: {
  questions: WorkspaceState["questions"];
  selectedTopicName: string;
  keywords: string[];
  saveState: "idle" | "saving" | "saved" | "error";
  statusMessage: string;
}) {
  const answeredCount = questions.filter((question) => question.answer?.trim()).length;
  const saveText =
    saveState === "saved"
      ? "已保存"
      : saveState === "saving"
        ? "保存中"
        : saveState === "error"
          ? "保存失败"
          : "未保存";

  return (
    <SectionCard title="当前批次" description="采集与回答状态。">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <MetricTile label="实时状态" value={saveText} icon={<MessageSquareQuote className="h-4 w-4" />} />
          <MetricTile label="问题池" value={`${questions.length} 条`} icon={<FileDown className="h-4 w-4" />} />
          <MetricTile label="已生成" value={`${answeredCount} 条`} icon={<Check className="h-4 w-4" />} />
        </div>

        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-500">实时状态</div>
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-sm leading-6 text-slate-700">
            {statusMessage}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-500">本次检索关键词</div>
          <div className="flex flex-wrap gap-1.5">
            {keywords.length ? (
              keywords.map((keyword) => (
                <Badge key={keyword} variant="outline" className="rounded-full border-slate-200 bg-white px-2.5 py-0.5 text-slate-700">
                  {keyword}
                </Badge>
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-500">
                发起采集后，这里会显示本次实际使用的关键词。
              </div>
            )}
          </div>
        </div>

        {selectedTopicName ? (
          <StatusRow label="当前主题" value={selectedTopicName} />
        ) : null}
      </div>
    </SectionCard>
  );
}

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
    <Button
      variant="ghost"
      onClick={() => onSelect(question.id)}
      className={cn(
        "h-auto w-full justify-start rounded-xl border border-slate-200 bg-white p-3.5 text-left shadow-none transition-all hover:border-slate-300 hover:bg-slate-50",
        active && "border-blue-500 bg-blue-50/60 shadow-sm hover:bg-blue-50/60",
      )}
    >
      <div className="flex w-full items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={generated ? "default" : "secondary"} className="rounded-full px-2.5 py-1">
              {generated ? "已生成" : "未生成"}
            </Badge>
            <span className="text-xs font-semibold text-slate-500">
              {question.platform ?? "zhihu"} / {question.answerCount} 个回答
            </span>
            {question.updatedTime ? <span className="text-xs font-semibold text-slate-400">{question.updatedTime}</span> : null}
          </div>

          <div className="space-y-1.5">
            <div className="line-clamp-2 text-[0.94rem] font-extrabold leading-6 text-slate-900">{question.title}</div>
            {question.excerpt ? <div className="line-clamp-2 text-sm leading-6 text-slate-500">{question.excerpt}</div> : null}
          </div>

          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="rounded-full border-slate-200 bg-slate-50 text-slate-600">
              {question.topic || "未分类"}
            </Badge>
            {question.url ? (
              <Badge variant="outline" className="rounded-full border-slate-200 bg-slate-50 text-slate-600">
                原始链接
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
          {isGenerating ? (
            <Badge variant="secondary" className="rounded-full">
              生成中
            </Badge>
          ) : null}
          <span className={cn("inline-flex h-2.5 w-2.5 rounded-full", generated ? "bg-emerald-500" : "bg-amber-400")} />
        </div>
      </div>
    </Button>
  );
}

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
    if (!keyword) {
      return questions;
    }
    return questions.filter((question) => {
      const haystack = `${question.title} ${question.excerpt} ${question.topic}`.toLowerCase();
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
    <SectionCard
      title="问题研究结果"
      description="搜索、筛选并选择当前要处理的问题。"
      action={<Button variant="outline" className="rounded-full border-slate-200 bg-white px-4 text-sm font-semibold">导出结果</Button>}
      className="min-h-0"
    >
      <div className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder="搜索标题、摘要、关键词"
              className="h-9 rounded-xl border-slate-200 bg-white pl-9 shadow-none"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" className="rounded-full border-slate-200 bg-white px-3.5 font-semibold">
              全部
            </Button>
            <Button variant="outline" className="rounded-full border-slate-200 bg-white px-3.5 font-semibold">
              未生成
            </Button>
            <Button variant="outline" className="rounded-full border-slate-200 bg-white px-3.5 font-semibold">
              已生成
            </Button>
          </div>
        </div>

        <ScrollArea className="h-[calc(100vh-460px)] min-h-[460px] pr-3">
          <div className="space-y-3">
            {isCollecting && !questions.length ? (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-500">
                正在采集问题，完成后结果会显示在这里。
              </div>
            ) : pagedQuestions.length ? (
              pagedQuestions.map((question) => (
                <QuestionRow
                  key={question.id}
                  question={question}
                  active={question.id === selectedQuestionId}
                  onSelect={(questionId) => selectQuestion(questionId)}
                  isGenerating={isGeneratingOne(question.id)}
                />
              ))
            ) : (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-500">
                没有匹配的问题结果。
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm font-semibold text-slate-500">
            {filteredQuestions.length ? `${visibleStart}-${visibleEnd} / ${filteredQuestions.length}` : "0 / 0"}
          </div>
          <div className="flex items-center gap-2">
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                setPageSize(Number(value));
                setPage(1);
              }}
            >
              <SelectTrigger className="h-10 w-[112px] rounded-xl border-slate-200 bg-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 20, 50].map((size) => (
                  <SelectItem key={size} value={String(size)}>
                    每页 {size}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={currentPage <= 1}
              aria-label="上一页"
              className="rounded-xl border-slate-200 bg-white"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Badge variant="secondary" className="rounded-full px-2.5 py-1">
              {currentPage} / {totalPages}
            </Badge>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              disabled={currentPage >= totalPages}
              aria-label="下一页"
              className="rounded-xl border-slate-200 bg-white"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function QuestionBrief({
  question,
  onOpenSource,
}: {
  question: WorkspaceState["questions"][number];
  onOpenSource: () => void;
}) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/80 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="rounded-full px-2.5 py-0.5">{question.topic || "知乎题目"}</Badge>
        <Badge variant="outline" className="rounded-full border-slate-200 bg-white px-2.5 py-0.5 text-slate-600">
          {question.answerCount} 个回答
        </Badge>
        <Badge variant="outline" className="rounded-full border-slate-200 bg-white px-2.5 py-0.5 text-slate-600">
          {question.updatedTime || "未知时间"}
        </Badge>
      </div>

      <div className="space-y-3">
        <div className="text-[0.94rem] font-extrabold leading-snug tracking-tight text-slate-900">{question.title}</div>
        {question.excerpt ? <div className="text-[0.84rem] leading-6 text-slate-600">{question.excerpt}</div> : null}
      </div>

      <Button variant="outline" className="rounded-full border-slate-200 bg-white font-semibold text-slate-700" onClick={onOpenSource}>
        打开原链接
        <ArrowUpRight className="h-4 w-4" />
      </Button>
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
    if (!question?.answer?.trim()) {
      return;
    }
    await navigator.clipboard.writeText(question.answer);
    setIsCopied(true);
    window.setTimeout(() => setIsCopied(false), 1200);
  }

  return (
    <SectionCard
      title="回答工作区"
      description="选中一个问题后，再决定是自动生成还是继续手工修改。"
      action={
        question ? (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              className="rounded-full px-4 font-semibold"
              onClick={() => onGenerateOne(question)}
            >
              <Sparkles className="h-4 w-4" />
              AI 生成
            </Button>
            <Button variant="outline" className="rounded-full border-slate-200 bg-white px-4 font-semibold" onClick={onSave}>
              <Save className="h-4 w-4" />
              保存
            </Button>
          </div>
        ) : null
      }
      className="min-h-0"
    >
      {!question ? (
        <div className="flex min-h-[360px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-200 bg-slate-50/70 px-5 text-center">
          <Bot className="h-10 w-10 text-slate-400" />
          <div className="space-y-1.5">
            <div className="text-[1rem] font-extrabold text-slate-900">先选中一个问题</div>
            <div className="max-w-md text-sm leading-7 text-slate-500">
              左侧问题池选择题目后，这里才会进入回答编辑状态。
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <QuestionBrief question={question} onOpenSource={() => window.open(question.url, "_blank", "noreferrer")} />

          <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2.5">
              <div>
                <div className="text-sm font-semibold text-slate-500">回答正文</div>
                <div className="mt-1 text-[0.84rem] leading-6 text-slate-500">支持在线查看、编辑、重新生成，并可保存到本地。</div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Button variant="outline" className="rounded-full border-slate-200 bg-white px-3.5 font-semibold" onClick={copyAnswer} disabled={!question.answer?.trim()}>
                  {isCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {isCopied ? "已复制" : "复制"}
                </Button>
                <Button variant="ghost" className="rounded-full px-3.5 font-semibold text-slate-700" onClick={() => onGenerateOne(question)}>
                  <RefreshCcw className="h-4 w-4" />
                  AI 生成
                </Button>
              </div>
            </div>

            {question.images?.length ? (
              <div className="grid gap-2.5 md:grid-cols-2">
                {question.images.map((imageUrl, index) => (
                  <figure key={`${question.id}-image-${index}`} className="overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
                    <img
                      className="h-44 w-full object-cover"
                      src={imageUrl}
                      alt={question.imagePrompts?.[index] || `${question.title} 配图 ${index + 1}`}
                    />
                    {question.imagePrompts?.[index] ? (
                      <figcaption className="border-t border-slate-200 px-3 py-2 text-[0.72rem] leading-5 text-slate-500">
                        {question.imagePrompts[index]}
                      </figcaption>
                    ) : null}
                  </figure>
                ))}
              </div>
            ) : null}

            <MarkdownEditor
              className="min-h-[320px] rounded-xl border border-slate-200 bg-white"
              placeholder="点击上方按钮生成回答，或者直接手工编辑这里的内容。"
              value={question.answer || ""}
              onChange={(value) => setQuestionAnswer(question.id, value)}
            />
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function CollectPage() {
  const workspace = useWorkspaceOutlet();
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

  const currentQuestion = questions.find((item) => item.id === selectedQuestionId) ?? null;
  const collectKeywords = selectedTopic?.expandedHints ?? [];

  return (
    <section className="space-y-4">
      <Card className="overflow-hidden rounded-xl border-slate-200/80 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.05)]">
        <CardHeader className="border-b border-slate-200/70 px-6 py-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-2">
              <CardTitle className="text-[1.25rem] font-extrabold tracking-tight text-slate-900">主题采集工作台</CardTitle>
              <CardDescription className="max-w-3xl text-[0.8rem] leading-6 text-slate-500">
                按主题采集问题，筛选候选题目，并批量生成或编辑回答。
              </CardDescription>
            </div>
            <Badge className="rounded-full px-2.5 py-1 text-[0.72rem] font-semibold">{questions.length} 个问题</Badge>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="border-b border-slate-200/70 bg-slate-50/80 px-6 py-4">
            <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1.6fr)_220px_180px_auto_auto]">
              <div className="space-y-2">
                <Label className="text-[0.82rem] font-semibold text-slate-700">主题</Label>
                <Select
                  value={selectedTopic?.id ?? ""}
                  onValueChange={(value) => {
                    const topic = presetTopics.find((item) => item.id === value) ?? null;
                    selectTopic(topic);
                  }}
                >
                  <SelectTrigger className="h-9 rounded-xl border-slate-200 bg-white px-3.5">
                    <SelectValue placeholder="选择主题" />
                  </SelectTrigger>
                  <SelectContent>
                    {presetTopics.map((topic) => (
                      <SelectItem key={topic.id} value={topic.id}>
                        {topic.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-[0.82rem] font-semibold text-slate-700">平台</Label>
                <Select value={selectedPlatform} onValueChange={(value) => selectPlatform(value as typeof selectedPlatform)}>
                  <SelectTrigger className="h-9 rounded-xl border-slate-200 bg-white px-3.5">
                    <SelectValue placeholder="选择平台" />
                  </SelectTrigger>
                  <SelectContent>
                    {supportedPlatforms.map((platform) => (
                      <SelectItem key={platform.id} value={platform.id}>
                        {platform.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-[0.82rem] font-semibold text-slate-700">采集上限</Label>
                <Input
                  type="number"
                  min={1}
                  max={maxCollectCount}
                  value={maxPushCount}
                  onChange={(event) => {
                    const nextValue = Number(event.target.value) || 1;
                    setMaxPushCount(Math.min(maxCollectCount, Math.max(1, nextValue)));
                  }}
                  className="h-9 rounded-xl border-slate-200 bg-white px-3.5"
                />
              </div>

              <div className="flex items-end">
                <Button
                  className="h-9 w-full rounded-xl px-4 text-sm font-semibold xl:w-auto"
                  onClick={collectQuestions}
                  disabled={isCollecting}
                >
                  {isCollecting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  {isCollecting ? "正在采集" : "开始采集"}
                </Button>
              </div>

              <div className="flex items-end">
                <Button variant="outline" className="h-9 w-full rounded-xl border-slate-200 bg-white px-4 text-sm font-semibold xl:w-auto" onClick={saveSession}>
                  <Save className="h-4 w-4" />
                  保存当前结果
                </Button>
              </div>
            </div>
          </div>

          <div className="grid gap-4 p-6 xl:grid-cols-[320px_minmax(0,1.25fr)_minmax(0,1fr)]">
            <div className="space-y-4">
              <WorkspacePulsePanel
                questions={questions}
                selectedTopicName={selectedTopic?.name ?? ""}
                keywords={collectKeywords}
                saveState={workspace.saveState}
                statusMessage={workspace.statusMessage}
              />

              <SectionCard title="筛选条件" description="仅保留当前工作流需要的核心筛选项。">
                <div className="space-y-1.5">
                  <StatusRow label="仅看未生成" value="18 条" />
                  <StatusRow label="回答数高于 20" value="11 条" />
                  <StatusRow label="最近 30 天更新" value="9 条" />
                </div>
              </SectionCard>

              <SectionCard title="扩展检索词" description="当前主题自动扩展出的检索词。">
                <div className="flex flex-wrap gap-1.5">
                  {collectKeywords.length ? (
                    collectKeywords.map((keyword) => (
                      <Badge key={keyword} variant="outline" className="rounded-full border-slate-200 bg-white px-2.5 py-0.5 text-slate-700">
                        {keyword}
                      </Badge>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-500">
                      当前主题还没有扩展词。
                    </div>
                  )}
                </div>
              </SectionCard>

              <PromptConfigSection
                answerStyle={answerStyle}
                systemPrompt={systemPrompt}
                generationPrompt={generationPrompt}
                onAnswerStyleChange={workspace.setAnswerStyle}
                onSystemPromptChange={workspace.setSystemPrompt}
                onGenerationPromptChange={workspace.setGenerationPrompt}
              />
            </div>

            <QuestionsPanel
              questions={questions}
              selectedQuestionId={selectedQuestionId}
              selectQuestion={workspace.selectQuestion}
              isCollecting={isCollecting}
              isGeneratingOne={isGeneratingOne}
            />

            <AnswerPanel
              question={currentQuestion}
              onGenerateOne={generateOneAnswer}
              onSave={saveSession}
              setQuestionAnswer={setQuestionAnswer}
            />
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function ImportPage() {
  const workspace = useWorkspaceOutlet();
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
    statusMessage,
    saveState,
  } = workspace;
  const [questionUrl, setQuestionUrl] = useState("");
  const currentQuestion = questions.find((item) => item.id === selectedQuestionId) ?? null;

  return (
    <section className="space-y-4">
      <Card className="overflow-hidden rounded-xl border-slate-200/80 bg-white shadow-[0_12px_28px_rgba(15,23,42,0.05)]">
        <CardHeader className="border-b border-slate-200/70 px-6 py-5">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
            <div className="space-y-2">
              <CardTitle className="text-[1.25rem] font-extrabold tracking-tight text-slate-900">URL 导入回答工作台</CardTitle>
              <CardDescription className="max-w-3xl text-[0.8rem] leading-6 text-slate-500">
                粘贴问题链接，解析单题信息，并直接生成和编辑回答。
              </CardDescription>
            </div>
            <Badge className="rounded-full px-2.5 py-1 text-[0.72rem] font-semibold">最近导入 {questions.length} 条</Badge>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <div className="border-b border-slate-200/70 bg-slate-50/80 px-6 py-4">
            <div className="grid gap-2.5 xl:grid-cols-[minmax(0,1.8fr)_220px_auto_auto]">
              <div className="space-y-2">
                <Label className="text-[0.82rem] font-semibold text-slate-700">问题链接</Label>
                <Input
                  value={questionUrl}
                  onChange={(event) => setQuestionUrl(event.target.value)}
                  placeholder="目前仅支持知乎问题链接，例如 https://www.zhihu.com/question/..."
                  className="h-9 rounded-xl border-slate-200 bg-white px-3.5"
                />
              </div>

              <div className="space-y-2">
                <Label className="text-[0.82rem] font-semibold text-slate-700">平台</Label>
                <Select value={selectedPlatform} onValueChange={(value) => selectPlatform(value as typeof selectedPlatform)}>
                  <SelectTrigger className="h-9 rounded-xl border-slate-200 bg-white px-3.5">
                    <SelectValue placeholder="选择平台" />
                  </SelectTrigger>
                  <SelectContent>
                    {supportedPlatforms.map((platform) => (
                      <SelectItem key={platform.id} value={platform.id}>
                        {platform.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-end">
                <Button
                  className="h-9 w-full rounded-xl px-4 text-sm font-semibold xl:w-auto"
                  disabled={!questionUrl.trim() || isImportingQuestionUrl}
                  onClick={() => importQuestionByUrl(questionUrl.trim())}
                >
                  {isImportingQuestionUrl ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ArrowUpRight className="h-4 w-4" />}
                  {isImportingQuestionUrl ? "解析中" : "导入问题"}
                </Button>
              </div>

              <div className="flex items-end">
                <Button variant="outline" className="h-9 w-full rounded-xl border-slate-200 bg-white px-4 text-sm font-semibold xl:w-auto" onClick={saveSession}>
                  <Save className="h-4 w-4" />
                  保存当前结果
                </Button>
              </div>
            </div>
          </div>

          <div className="grid gap-4 p-6 xl:grid-cols-[360px_minmax(0,1fr)]">
            <div className="space-y-4">
              <SectionCard title="当前状态" description="链接解析、回答生成和本地保存。">
                <div className="space-y-2">
                  <StatusRow label="URL 解析" value={isImportingQuestionUrl ? "进行中" : "待检查"} valueClassName={isImportingQuestionUrl ? "text-blue-700" : "text-amber-600"} />
                  <StatusRow label="回答生成" value={currentQuestion?.answer?.trim() ? "已完成" : "待执行"} valueClassName={currentQuestion?.answer?.trim() ? "text-emerald-600" : "text-amber-600"} />
                  <StatusRow label="本地保存" value={saveState === "saved" ? "已保存" : "未保存"} valueClassName={saveState === "saved" ? "text-emerald-600" : "text-rose-600"} />
                  <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-[0.84rem] leading-6 text-slate-600">
                    {statusMessage}
                  </div>
                </div>
              </SectionCard>

              <SectionCard title="最近导入历史" description="最近进入问题池的链接。">
                <div className="space-y-3">
                  {questions.slice(0, 3).length ? (
                    questions.slice(0, 3).map((item) => (
                      <div key={item.id} className="rounded-xl border border-slate-200 bg-white p-3.5">
                        <div className="line-clamp-2 text-[0.9rem] font-bold leading-6 text-slate-900">{item.title}</div>
                        <div className="mt-1.5 text-[0.72rem] leading-5 text-slate-500">
                          {item.platform ?? "zhihu"} · {item.updatedTime || "未知时间"} · {item.answer?.trim() ? "已生成回答" : "未生成"}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/80 px-3 py-2 text-sm text-slate-500">
                      还没有导入记录。
                    </div>
                  )}
                </div>
              </SectionCard>

              <PromptConfigSection
                answerStyle={answerStyle}
                systemPrompt={systemPrompt}
                generationPrompt={generationPrompt}
                onAnswerStyleChange={setAnswerStyle}
                onSystemPromptChange={setSystemPrompt}
                onGenerationPromptChange={setGenerationPrompt}
              />
            </div>

            <AnswerPanel
              question={currentQuestion}
              onGenerateOne={generateOneAnswer}
              onSave={saveSession}
              setQuestionAnswer={setQuestionAnswer}
            />
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

export function WorkspaceLayout() {
  const workspace = useWorkspace();

  return (
    <div className="min-h-screen bg-[linear-gradient(180deg,#fbfdff_0%,#f4f7fb_100%)] text-slate-900">
      <WorkspaceTopbar />
      <main className="mx-auto w-full max-w-[1800px] px-4 pb-4 pt-4 sm:px-6 lg:px-6">
        <Outlet context={workspace} />
      </main>
    </div>
  );
}

export { CollectPage, ImportPage };
