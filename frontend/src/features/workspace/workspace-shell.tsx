import {
  ArrowUpRight,
  Bot,
  Check,
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
import { useDeferredValue, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/store/workspace-store";

import { supportedPlatforms } from "./defaults";
import { useWorkspace } from "./use-workspace";

function TopicControlPanel() {
  const {
    selectedPlatform,
    presetTopics,
    selectedTopic,
    questions,
    maxPushCount,
    answerStyle,
    systemPrompt,
    selectPlatform,
    selectTopic,
    setMaxPushCount,
    setAnswerStyle,
    setSystemPrompt,
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
          页面只保留一条主链路：选择主题、采集问题、逐条生成与编辑回答、保存本地结果。
        </p>

        <div className="workspace-metrics" aria-label="当前工作概况">
          <MetricCard
            label="当前平台"
            value={supportedPlatforms.find((item) => item.id === selectedPlatform)?.label ?? selectedPlatform}
          />
          <MetricCard label="当前主题" value={selectedTopic?.name ?? "未选择"} />
          <MetricCard label="采集上限" value={`${maxPushCount} 条`} />
        </div>

        <WorkspacePulsePanel questions={questions} />
      </div>

      <Card className="workspace-control-panel">
        <CardHeader className="space-y-2">
          <CardTitle className="text-[1.05rem]">开始一次采集</CardTitle>
          <CardDescription>主题单选，采集和回答都围绕当前主题展开。</CardDescription>
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
              max={10}
              value={maxPushCount}
              onChange={(event) => setMaxPushCount(Number(event.target.value) || 1)}
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

          <div className="grid gap-2">
            <Label htmlFor="system-prompt">系统提示词</Label>
            <Textarea
              id="system-prompt"
              rows={8}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="answer-style">回答风格提示</Label>
            <Textarea
              id="answer-style"
              rows={5}
              value={answerStyle}
              onChange={(event) => setAnswerStyle(event.target.value)}
            />
          </div>
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

function WorkspacePulsePanel({ questions }: { questions: ReturnType<typeof useWorkspace>["questions"] }) {
  const statusMessage = useWorkspaceStore((state) => state.statusMessage);
  const saveState = useWorkspaceStore((state) => state.saveState);
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
    </section>
  );
}

function QuestionsColumn() {
  const { questions, selectedQuestionId, selectQuestion, isCollecting } = useWorkspace();
  const [query, setQuery] = useState("");
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
                  正在根据当前主题检索题目、整理链接并过滤结果，请稍候。
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
              filteredQuestions.map((question) => {
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
  return (
    <div className="workspace-page">
      <div className="workspace-backdrop" />
      <main className="workspace-main">
        <TopicControlPanel />

        <section className="workspace-columns">
          <QuestionsColumn />
          <AnswerColumn />
        </section>
      </main>
    </div>
  );
}
