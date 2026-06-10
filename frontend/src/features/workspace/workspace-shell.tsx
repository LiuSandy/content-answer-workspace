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
  Orbit,
  RefreshCcw,
  Save,
  Search,
  Sparkles,
} from "lucide-react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from "@/components/ui/navigation-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/store/workspace-store";

import { maxCollectCount, supportedPlatforms } from "./defaults";
import { useWorkspace } from "./use-workspace";

function PromptConfigPanel() {
  const { answerStyle, systemPrompt, generationPrompt, setAnswerStyle, setSystemPrompt, setGenerationPrompt } =
    useWorkspace();

  return (
    <Card className="workspace-column workspace-column--config">
      <CardHeader className="workspace-column__header">
        <div className="space-y-1">
          <CardTitle>提示词配置</CardTitle>
          <CardDescription>这里的提示词在链接导入和自动采集两种模式下都要保留，并且可以继续编辑。</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="workspace-column__content">
        <div className="grid gap-2">
          <Label htmlFor="topic-system-prompt">主题提示词</Label>
          <Textarea
            id="topic-system-prompt"
            rows={8}
            value={systemPrompt}
            onChange={(event) => setSystemPrompt(event.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="answer-style">主题回答风格提示</Label>
          <Textarea
            id="answer-style"
            rows={5}
            value={answerStyle}
            onChange={(event) => setAnswerStyle(event.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="generation-prompt">全局生成规则提示词</Label>
          <Textarea
            id="generation-prompt"
            rows={12}
            value={generationPrompt}
            onChange={(event) => setGenerationPrompt(event.target.value)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function TopicControlPanel({ entryMode }: { entryMode: "import" | "collect" }) {
  const {
    selectedPlatform,
    presetTopics,
    selectedTopic,
    questions,
    maxPushCount,
    selectPlatform,
    selectTopic,
    setMaxPushCount,
    collectQuestions,
    saveSession,
    isCollecting,
  } = useWorkspace();

  return (
    <section className="workspace-frame workspace-hero">
      <div className="workspace-hero__content">
        <div className="workspace-kicker">
          <Orbit className="h-4 w-4" />
          内容回答工作台
        </div>
        <h1 className="workspace-title">先找准问题，再写出像真人的回答。</h1>
        <p className="workspace-copy">
          现在有两条清晰入口：先支持直接导入指定问题链接，其次支持按主题自动采集，再进入统一回答流程。
        </p>

        <div className="workspace-metrics" aria-label="当前工作概况">
          <MetricCard
            label="当前平台"
            value={supportedPlatforms.find((item) => item.id === selectedPlatform)?.label ?? selectedPlatform}
          />
          <MetricCard label="当前主题" value={selectedTopic?.name ?? "未选择"} />
          <MetricCard label="采集上限" value={`${maxPushCount} 条`} />
        </div>

        <WorkspacePulsePanel questions={questions} selectedTopic={selectedTopic} />
      </div>

      <Card className="workspace-control-panel">
        <CardHeader className="space-y-2">
          <CardTitle className="text-[1.05rem]">
            {entryMode === "import" ? "链接导入" : "自动采集"}
          </CardTitle>
          <CardDescription>
            {entryMode === "import"
              ? "粘贴知乎问题链接，直接把指定题目导入当前问题池。"
              : "主题单选，采集和回答都围绕当前主题展开。"}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2">
            <Label htmlFor="platform-select">平台</Label>
            <Select
              value={selectedPlatform}
              onValueChange={(value) => selectPlatform(value as typeof selectedPlatform)}
            >
              <SelectTrigger id="platform-select">
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

          {entryMode === "import" ? (
            <section className="workspace-entry-panel">
              <div className="grid gap-2">
                <Label htmlFor="question-url">问题链接</Label>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <Input
                    id="question-url"
                    value={questionUrl}
                    onChange={(event) => setQuestionUrl(event.target.value)}
                    placeholder="目前仅支持知乎问题链接，例如 https://www.zhihu.com/question/..."
                  />
                  <Button
                    className="cursor-pointer"
                    disabled={!questionUrl.trim() || isImportingQuestionUrl}
                    onClick={() => importQuestionByUrl(questionUrl.trim())}
                  >
                    {isImportingQuestionUrl ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : (
                      <ArrowUpRight className="h-4 w-4" />
                    )}
                    {isImportingQuestionUrl ? "解析中" : "导入问题"}
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">
                  适合已经明确目标题目的场景，导入后会直接进入当前问题池。
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Button className="cursor-pointer" variant="outline" onClick={saveSession}>
                  <Save className="h-4 w-4" />
                  保存当前结果
                </Button>
              </div>
            </section>
          ) : (
            <>
              <div className="grid gap-2">
                <Label htmlFor="topic-select">主题</Label>
                <Select
                  value={selectedTopic?.id ?? ""}
                  onValueChange={(value) => {
                    const topic = presetTopics.find((item) => item.id === value) ?? null;
                    selectTopic(topic);
                  }}
                >
                  <SelectTrigger id="topic-select">
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

              <div className="grid gap-2">
                <Label htmlFor="push-count">采集数量上限</Label>
                <Input
                  id="push-count"
                  type="number"
                  min={1}
                  max={maxCollectCount}
                  value={maxPushCount}
                  onChange={(event) => {
                    const nextValue = Number(event.target.value) || 1;
                    setMaxPushCount(Math.min(maxCollectCount, Math.max(1, nextValue)));
                  }}
                />
              </div>

              <div className="grid gap-2">
                <Label>系统扩展匹配词</Label>
                <div className="workspace-chip-cloud">
                  {(selectedTopic?.expandedHints ?? []).length ? (
                    (selectedTopic?.expandedHints ?? []).map((hint) => <Badge key={hint}>{hint}</Badge>)
                  ) : (
                    <span className="text-sm text-muted-foreground">当前主题还没有扩展词。</span>
                  )}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Button className="cursor-pointer" onClick={collectQuestions} disabled={isCollecting}>
                  {isCollecting ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  {isCollecting ? "正在采集" : "开始采集问题"}
                </Button>
                <Button className="cursor-pointer" variant="outline" onClick={saveSession}>
                  <Save className="h-4 w-4" />
                  保存当前结果
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function MetricCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "accent";
}) {
  return (
    <div className={cn("workspace-metric-card", tone === "accent" && "workspace-metric-card--accent")}>
      <div className="workspace-metric-card__label">{label}</div>
      <div className="workspace-metric-card__value">{value}</div>
    </div>
  );
}

function WorkspacePulsePanel({
  questions,
  selectedTopic,
}: {
  questions: ReturnType<typeof useWorkspace>["questions"];
  selectedTopic: ReturnType<typeof useWorkspace>["selectedTopic"];
}) {
  const statusMessage = useWorkspaceStore((state) => state.statusMessage);
  const saveState = useWorkspaceStore((state) => state.saveState);
  const answeredCount = questions.filter((question) => question.answer?.trim()).length;
  const retrievalKeywords = selectedTopic?.expandedHints ?? [];

  const saveText =
    saveState === "saved"
      ? "已保存"
      : saveState === "saving"
        ? "保存中"
        : saveState === "error"
          ? "保存失败"
          : "未保存";

  return (
    <section className="workspace-pulse-panel" aria-label="当前批次状态">
      <div className="workspace-pulse-panel__header">
        <div>
          <div className="workspace-pulse-panel__eyebrow">当前批次</div>
          <div className="workspace-pulse-panel__title">采集与回答状态</div>
        </div>
        <Badge variant={saveState === "saved" ? "default" : "secondary"}>{saveText}</Badge>
      </div>

      <div className="workspace-pulse-grid">
        <div className="workspace-status-card workspace-status-card--wide">
          <div className="workspace-status-card__icon">
            <MessageSquareQuote className="h-4 w-4" />
          </div>
          <div className="workspace-status-card__body">
            <div className="workspace-status-card__label">实时状态</div>
            <div className="workspace-status-card__value">{statusMessage}</div>
          </div>
        </div>

        <div className="workspace-status-card">
          <div className="workspace-status-card__icon">
            <FileDown className="h-4 w-4" />
          </div>
          <div className="workspace-status-card__body">
            <div className="workspace-status-card__label">问题池</div>
            <div className="workspace-status-card__value">{questions.length} 条</div>
          </div>
        </div>

        <div className="workspace-status-card">
          <div className="workspace-status-card__icon">
            <Check className="h-4 w-4" />
          </div>
          <div className="workspace-status-card__body">
            <div className="workspace-status-card__label">已生成</div>
            <div className="workspace-status-card__value">{answeredCount} 条</div>
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-2">
        <div className="workspace-pulse-panel__eyebrow">本次检索关键词</div>
        <div className="workspace-chip-cloud">
          {retrievalKeywords.length ? (
            retrievalKeywords.map((keyword) => <Badge key={keyword}>{keyword}</Badge>)
          ) : (
            <span className="text-sm text-muted-foreground">发起采集后，这里会显示本次实际使用的关键词。</span>
          )}
        </div>
      </div>
    </section>
  );
}

function QuestionsColumn() {
  const { questions, selectedQuestionId, selectQuestion, isCollecting } = useWorkspace();
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

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  useEffect(() => {
    setPage(1);
  }, [deferredQuery, questions.length]);

  return (
    <Card className="workspace-column workspace-column--list">
      <CardHeader className="workspace-column__header">
        <div className="space-y-1">
          <CardTitle>问题池</CardTitle>
          <CardDescription>先看题目质量，再决定要不要生成回答。</CardDescription>
        </div>
        <div className="workspace-column__header-meta">
          <Badge>{filteredQuestions.length} 条</Badge>
        </div>
      </CardHeader>
      <CardContent className="workspace-column__content">
        <div className="grid gap-3">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索标题、摘要、主题"
          />

          {isCollecting ? (
            <div className="workspace-loading-panel">
              <LoaderCircle className="h-6 w-6 animate-spin" />
              <div>
                <div className="workspace-loading-panel__title">正在采集站点问题</div>
                <div className="workspace-loading-panel__copy">
                  正在扩展相近主题、批量检索知乎题目，并聚合去重结果，请稍候。
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <ScrollArea className="workspace-scroll-panel">
          <div className="workspace-question-list">
            {filteredQuestions.length === 0 ? (
              <EmptyState
                title="还没有采集到问题"
                description="先在上方选择主题并发起采集。"
              />
            ) : (
              pagedQuestions.map((question) => {
                const isActive = selectedQuestionId === question.id;
                const hasAnswer = Boolean(question.answer?.trim());

                return (
                  <button
                    key={question.id}
                    type="button"
                    onClick={() => selectQuestion(question.id)}
                    className={cn(
                      "workspace-question-card",
                      isActive && "workspace-question-card--active",
                    )}
                  >
                    <div className="workspace-question-card__meta">
                      <Badge className="workspace-question-card__badge">{question.topic}</Badge>
                      <span className="workspace-question-card__status">
                        {hasAnswer ? (
                          <>
                            <Check className="h-3.5 w-3.5" />
                            已生成
                          </>
                        ) : (
                          "未生成"
                        )}
                      </span>
                    </div>
                    <h3 className="workspace-question-card__title">{question.title}</h3>
                    {question.excerpt ? (
                      <p className="workspace-question-card__excerpt">{question.excerpt}</p>
                    ) : null}
                    <div className="workspace-question-card__footer">
                      <span>{question.answerCount} 个回答</span>
                      <span>{question.updatedTime || "未知时间"}</span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </ScrollArea>

        <div className="workspace-pagination" aria-label="问题池分页">
          <div className="workspace-pagination__summary">
            {filteredQuestions.length ? `${visibleStart}-${visibleEnd} / ${filteredQuestions.length}` : "0 / 0"}
          </div>
          <div className="workspace-pagination__controls">
            <Select
              value={String(pageSize)}
              onValueChange={(value) => {
                setPageSize(Number(value));
                setPage(1);
              }}
            >
              <SelectTrigger className="h-9 w-[104px]">
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
              className="cursor-pointer"
              variant="outline"
              size="icon"
              onClick={() => setPage((value) => Math.max(1, value - 1))}
              disabled={currentPage <= 1}
              aria-label="上一页"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Badge variant="secondary">
              {currentPage} / {totalPages}
            </Badge>
            <Button
              className="cursor-pointer"
              variant="outline"
              size="icon"
              onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
              disabled={currentPage >= totalPages}
              aria-label="下一页"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AnswerColumn() {
  const { questions, selectedQuestionId, setQuestionAnswer, generateOneAnswer, isGeneratingOne, saveSession } =
    useWorkspace();
  const question = questions.find((item) => item.id === selectedQuestionId) ?? null;
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
    <Card className="workspace-column workspace-column--editor">
      <CardHeader className="workspace-column__header">
        <div className="space-y-1">
          <CardTitle>回答工作区</CardTitle>
          <CardDescription>选中一个问题后，再决定是自动生成还是继续手工修改。</CardDescription>
        </div>

        {question ? (
          <div className="workspace-column__actions">
            <Button
              className="cursor-pointer"
              variant="secondary"
              onClick={() => generateOneAnswer(question)}
              disabled={isGeneratingOne(question.id)}
            >
              {isGeneratingOne(question.id) ? (
                <LoaderCircle className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              AI 生成
            </Button>
            <Button className="cursor-pointer" variant="outline" onClick={saveSession}>
              <Save className="h-4 w-4" />
              保存
            </Button>
          </div>
        ) : null}
      </CardHeader>

      <CardContent className="workspace-column__content">
        {!question ? (
          <EmptyState
            title="先选中一个问题"
            description="左侧问题池选择题目后，这里才会进入回答编辑状态。"
            icon={<Bot className="h-10 w-10 text-muted-foreground" />}
          />
        ) : (
          <div className="workspace-answer-layout">
            <div className="workspace-answer-brief">
              <div className="workspace-answer-brief__meta">
                <Badge>{question.topic}</Badge>
                <span>{question.answerCount} 个回答</span>
                <span>{question.updatedTime || "未知时间"}</span>
              </div>

              <h2 className="workspace-answer-brief__title">{question.title}</h2>

              <a
                href={question.url}
                target="_blank"
                rel="noreferrer"
                className="workspace-answer-brief__link"
              >
                打开原始问题
                <ArrowUpRight className="h-4 w-4" />
              </a>

              {question.excerpt ? (
                <p className="workspace-answer-brief__excerpt">{question.excerpt}</p>
              ) : null}
            </div>

            <div className="workspace-answer-editor">
              <div className="workspace-answer-editor__toolbar">
                <div>
                  <div className="workspace-answer-editor__title">回答正文</div>
                  <div className="workspace-answer-editor__copy">
                    支持在线查看、编辑、重新生成，并可保存到本地。
                  </div>
                </div>
                <div className="workspace-answer-editor__actions">
                  <Button
                    className="cursor-pointer"
                    variant="outline"
                    onClick={copyAnswer}
                    disabled={!question.answer?.trim()}
                  >
                    {isCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    {isCopied ? "已复制" : "复制"}
                  </Button>
                  <Button
                    className="cursor-pointer"
                    variant="ghost"
                    onClick={() => generateOneAnswer(question)}
                    disabled={isGeneratingOne(question.id)}
                  >
                    <RefreshCcw className={cn("h-4 w-4", isGeneratingOne(question.id) && "animate-spin")} />
                    AI 生成
                  </Button>
                </div>
              </div>

              {question.images?.length ? (
                <div className="workspace-answer-images">
                  {question.images.map((imageUrl, index) => (
                    <figure key={`${question.id}-image-${index}`} className="workspace-answer-image-card">
                      <img
                        className="workspace-answer-image"
                        src={imageUrl}
                        alt={question.imagePrompts?.[index] || `${question.title} 配图 ${index + 1}`}
                      />
                      {question.imagePrompts?.[index] ? (
                        <figcaption className="workspace-answer-image-caption">
                          {question.imagePrompts[index]}
                        </figcaption>
                      ) : null}
                    </figure>
                  ))}
                </div>
              ) : null}

              <MarkdownEditor
                className="workspace-answer-editor__textarea"
                placeholder="点击上方按钮生成回答，或者直接手工编辑这里的内容。"
                value={question.answer || ""}
                onChange={(value) => setQuestionAnswer(question.id, value)}
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ImportControlCard() {
  const {
    selectedPlatform,
    saveSession,
    importQuestionByUrl,
    isImportingQuestionUrl,
    selectPlatform,
  } = useWorkspace();
  const [questionUrl, setQuestionUrl] = useState("");

  return (
    <Card className="workspace-column workspace-column--import">
      <CardHeader className="workspace-column__header">
        <div className="space-y-1">
          <CardTitle>链接导入</CardTitle>
          <CardDescription>粘贴问题链接，导入成功后直接在左侧回答工作区查看和生成内容。</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="workspace-column__content">
        <div className="grid gap-2">
          <Label htmlFor="import-platform-select">平台</Label>
          <Select
            value={selectedPlatform}
            onValueChange={(value) => selectPlatform(value as typeof selectedPlatform)}
          >
            <SelectTrigger id="import-platform-select">
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

        <section className="workspace-entry-panel">
          <div className="grid gap-2">
            <Label htmlFor="question-url">问题链接</Label>
            <div className="grid gap-3">
              <Input
                id="question-url"
                value={questionUrl}
                onChange={(event) => setQuestionUrl(event.target.value)}
                placeholder="目前仅支持知乎问题链接，例如 https://www.zhihu.com/question/..."
              />
              <Button
                className="cursor-pointer"
                disabled={!questionUrl.trim() || isImportingQuestionUrl}
                onClick={() => importQuestionByUrl(questionUrl.trim())}
              >
                {isImportingQuestionUrl ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <ArrowUpRight className="h-4 w-4" />
                )}
                {isImportingQuestionUrl ? "解析中" : "导入问题"}
              </Button>
            </div>
          </div>

          <Button className="cursor-pointer" variant="outline" onClick={saveSession}>
            <Save className="h-4 w-4" />
            保存当前结果
          </Button>
        </section>
      </CardContent>
    </Card>
  );
}

function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="workspace-empty-state">
      {icon ?? <MessageSquareQuote className="h-10 w-10 text-muted-foreground" />}
      <div className="workspace-empty-state__title">{title}</div>
      <div className="workspace-empty-state__copy">{description}</div>
    </div>
  );
}

export function WorkspaceShell() {
  const [entryMode, setEntryMode] = useState<"import" | "collect">("import");

  return (
    <div className="workspace-page">
      <div className="workspace-backdrop" />
      <main className="workspace-main">
        <section className="workspace-topbar" aria-label="页面导航">
          <div className="workspace-topbar__brand">
            <div className="workspace-topbar__title">内容回答工作台</div>
            <div className="workspace-topbar__copy">先选择问题来源，再进入对应流程。</div>
          </div>
          <NavigationMenu className="workspace-mode-menu" viewport={false}>
            <NavigationMenuList className="workspace-mode-menu__list">
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <button
                    type="button"
                    className={cn(
                      "workspace-mode-menu__trigger",
                      entryMode === "import" && "workspace-mode-menu__trigger--active",
                    )}
                    onClick={() => setEntryMode("import")}
                    aria-current={entryMode === "import" ? "page" : undefined}
                  >
                    链接导入
                  </button>
                </NavigationMenuLink>
              </NavigationMenuItem>
              <NavigationMenuItem>
                <NavigationMenuLink asChild>
                  <button
                    type="button"
                    className={cn(
                      "workspace-mode-menu__trigger",
                      entryMode === "collect" && "workspace-mode-menu__trigger--active",
                    )}
                    onClick={() => setEntryMode("collect")}
                    aria-current={entryMode === "collect" ? "page" : undefined}
                  >
                    自动采集
                  </button>
                </NavigationMenuLink>
              </NavigationMenuItem>
            </NavigationMenuList>
          </NavigationMenu>
        </section>

        {entryMode === "import" ? (
          <section className="workspace-import-layout">
            <AnswerColumn />
            <div className="workspace-import-side">
              <ImportControlCard />
              <PromptConfigPanel />
            </div>
          </section>
        ) : (
          <>
            <TopicControlPanel entryMode={entryMode} />
            <section className="workspace-columns workspace-columns--collect">
              <QuestionsColumn />
              <AnswerColumn />
              <PromptConfigPanel />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
