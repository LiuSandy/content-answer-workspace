import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { useWorkspaceStore } from "@/store/workspace-store";
import type {
  CollectPayload,
  GenerateAllPayload,
  GenerateOnePayload,
  ParseQuestionUrlPayload,
  Platform,
  PolishOnePayload,
  QuestionItem,
  SaveSessionPayload,
  Topic,
} from "@/types/workflow";

import { defaultPlatform } from "./defaults";
import {
  collectWorkflow,
  generateAllAnswers,
  generateOneAnswer,
  getLatestSession,
  getSession,
  getWorkspaceConfig,
  parseQuestionUrl,
  polishOneAnswer,
  saveWorkspaceSession,
} from "./workflow-api";

function withPlatform<T extends { platform?: Platform }>(item: T, platform: Platform): T {
  return {
    ...item,
    platform: item.platform ?? platform,
  };
}

function uniqueQuestionsById(items: QuestionItem[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.platform ?? "zhihu"}:${item.id}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function mergeTopics(currentTopics: Topic[], updatedTopics: Topic[]) {
  const updatedMap = new Map(updatedTopics.map((topic) => [topic.id, topic]));
  return [
    ...currentTopics.map((topic) => updatedMap.get(topic.id) ?? topic),
    ...updatedTopics.filter((topic) => !currentTopics.some((currentTopic) => currentTopic.id === topic.id)),
  ];
}

function getTopicSystemPrompt(topic: Topic | null, fallback: string) {
  return topic?.systemPrompt?.trim() ? topic.systemPrompt : fallback;
}

function getTopicAnswerStyle(topic: Topic | null, fallback: string) {
  return topic?.answerStyle?.trim() ? topic.answerStyle : fallback;
}

export function useWorkspace() {
  const hasHydratedConfig = useRef(false);
  const hydratedSessionKey = useRef<string | null>(null);
  const {
    selectedPlatform,
    selectedSource,
    selectedContentMode,
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    generationPrompt,
    contentConstraint,
    maxPushCount,
    setSelectedPlatform,
    setSelectedContentMode,
    setPresetTopics,
    setSelectedTopic,
    updateTopicPrompts,
    setQuestions,
    setQuestionAnswer,
    setQuestionItem,
    selectQuestion,
    setAnswerStyle,
    setSystemPrompt,
    setGenerationPrompt,
    setContentConstraint,
    setMaxPushCount,
    setIsCollecting,
    setIsGeneratingAll,
    setSaveState,
    setStatusMessage,
    activeSessionId,
    setActiveSessionId,
  } = useWorkspaceStore();

  const configQuery = useQuery({
    queryKey: ["workspace-config"],
    queryFn: getWorkspaceConfig,
  });

  const sessionQuery = useQuery({
    queryKey: ["workspace-session", activeSessionId],
    queryFn: () => (activeSessionId ? getSession(activeSessionId) : getLatestSession()),
  });

  useEffect(() => {
    if (configQuery.data && !hasHydratedConfig.current) {
      hasHydratedConfig.current = true;
      const initialTopic = configQuery.data.topics[0] ?? null;
      setSelectedPlatform(configQuery.data.workflow.platform ?? defaultPlatform);
      setPresetTopics(configQuery.data.topics);
      setAnswerStyle(getTopicAnswerStyle(initialTopic, configQuery.data.workflow.answerStyle));
      setSystemPrompt(getTopicSystemPrompt(initialTopic, configQuery.data.workflow.systemPrompt));
      setGenerationPrompt(configQuery.data.workflow.generationPrompt);
      setMaxPushCount(configQuery.data.workflow.maxPushCount);
      setSelectedTopic(initialTopic);
      setStatusMessage("配置加载完成，可以开始采集问题。");
    }
  }, [
    configQuery.data,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
    setGenerationPrompt,
  ]);

  useEffect(() => {
    if (!selectedTopic) {
      return;
    }
    setSystemPrompt(getTopicSystemPrompt(selectedTopic, systemPrompt));
    setAnswerStyle(getTopicAnswerStyle(selectedTopic, answerStyle));
  }, [selectedTopic?.id, setAnswerStyle, setSystemPrompt]);

  useEffect(() => {
    if (configQuery.isError && !hasHydratedConfig.current) {
      hasHydratedConfig.current = true;
      setStatusMessage("配置接口加载失败，请检查后端服务是否正常运行。");
    }
  }, [configQuery.isError, setStatusMessage]);

  useEffect(() => {
    const session = sessionQuery.data?.session;
    const sessionKey = activeSessionId ?? "__latest__";
    if (!session || hydratedSessionKey.current === sessionKey) {
      return;
    }
    hydratedSessionKey.current = sessionKey;
    if (!activeSessionId && session.sessionId) {
      setActiveSessionId(session.sessionId);
    }
    const sessionPlatform = session.platform ?? selectedPlatform;
    const sessionTopics = session.topics ?? [];
    const sessionSelectedTopic = sessionTopics[0] ?? null;
    setSelectedPlatform(sessionPlatform);
    if (session.maxPushCount) {
      setMaxPushCount(session.maxPushCount);
    }
    if (session.generationPrompt) {
      setGenerationPrompt(session.generationPrompt);
    }
    if (sessionTopics.length) {
      setPresetTopics(sessionTopics);
      setSelectedTopic(sessionSelectedTopic);
      setAnswerStyle(getTopicAnswerStyle(sessionSelectedTopic, session.answerStyle ?? answerStyle));
      setSystemPrompt(getTopicSystemPrompt(sessionSelectedTopic, session.systemPrompt ?? systemPrompt));
    } else {
      if (session.answerStyle) {
        setAnswerStyle(session.answerStyle);
      }
      if (session.systemPrompt) {
        setSystemPrompt(session.systemPrompt);
      }
    }
    setQuestions(session.items?.length ? session.items.map((item) => withPlatform(item, sessionPlatform)) : []);
    setStatusMessage(session.items?.length ? "已恢复所选会话。" : "已切换到新的空会话。");
  }, [
    sessionQuery.data,
    activeSessionId,
    selectedPlatform,
    setActiveSessionId,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setQuestions,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
    setGenerationPrompt,
  ]);

  const collectMutation = useMutation({
    mutationFn: () => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: CollectPayload = {
        platform: selectedPlatform,
        source: selectedSource,
        contentMode: selectedContentMode,
        topics: selectedTopic
          ? [
              {
                ...selectedTopic,
                systemPrompt: currentSystemPrompt,
                answerStyle: currentAnswerStyle,
              },
            ]
          : [],
        maxPushCount,
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        skipAnswerGeneration: true,
      };
      return collectWorkflow(payload);
    },
    onMutate: () => {
      setIsCollecting(true);
      setStatusMessage("正在让 AI 扩展检索词，并连接知乎采集候选问题...");
    },
    onSuccess: (data) => {
      const responsePlatform = data.platform ?? data.config.platform ?? selectedPlatform;
      setSelectedPlatform(responsePlatform);
      if (data.topics.length) {
        setPresetTopics(mergeTopics(presetTopics, data.topics));
        setSelectedTopic(data.topics[0] ?? null);
      }
      setQuestions(data.items.map((item) => withPlatform(item, responsePlatform)));
      const retrievalCount = data.topics[0]?.expandedHints?.length ?? 0;
      setStatusMessage(
        retrievalCount
          ? `采集完成，AI 生成 ${retrievalCount} 个检索词，聚合出 ${data.items.length} 条问题。`
          : `采集完成，本次获取 ${data.items.length} 条问题。`,
      );
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
    onSettled: () => {
      setIsCollecting(false);
    },
  });

  const importQuestionByUrlMutation = useMutation({
    mutationFn: (url: string) => {
      const payload: ParseQuestionUrlPayload = {
        platform: selectedPlatform,
        url,
        topic: selectedTopic ?? undefined,
      };
      return parseQuestionUrl(payload);
    },
    onMutate: () => {
      setStatusMessage("正在解析问题链接...");
    },
    onSuccess: (data) => {
      const importedItem = withPlatform(data.item, selectedPlatform);
      setQuestions(
        uniqueQuestionsById([importedItem, ...questions.map((item) => withPlatform(item, selectedPlatform))]),
      );
      selectQuestion(importedItem.id);
      setStatusMessage(`已导入问题：${importedItem.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });

  const generateAllMutation = useMutation({
    mutationFn: () => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateAllPayload = {
        platform: selectedPlatform,
        topics: selectedTopic
          ? [
              {
                ...selectedTopic,
                systemPrompt: currentSystemPrompt,
                answerStyle: currentAnswerStyle,
              },
            ]
          : [],
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
        maxPushCount,
      };
      return generateAllAnswers(payload);
    },
    onMutate: () => {
      setIsGeneratingAll(true);
      setStatusMessage("正在批量生成回答...");
    },
    onSuccess: (data) => {
      setQuestions(data.items.map((item) => withPlatform(item, selectedPlatform)));
      setStatusMessage(`已完成 ${data.items.length} 条回答生成。`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
    onSettled: () => {
      setIsGeneratingAll(false);
    },
  });

  const generateOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: GenerateOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return generateOneAnswer(payload);
    },
    onSuccess: (data, item) => {
      setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
      setStatusMessage(`已生成：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });

  const polishOneMutation = useMutation({
    mutationFn: (item: QuestionItem) => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: PolishOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        currentAnswer: item.answer,
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        contentConstraint: contentConstraint || undefined,
      };
      return polishOneAnswer(payload);
    },
    onSuccess: (data, item) => {
      setQuestionItem(item.id, withPlatform(data.item, selectedPlatform));
      setStatusMessage(`已润色：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const currentSystemPrompt = getTopicSystemPrompt(selectedTopic, systemPrompt);
      const currentAnswerStyle = getTopicAnswerStyle(selectedTopic, answerStyle);
      const payload: SaveSessionPayload = {
        sessionId: activeSessionId ?? undefined,
        platform: selectedPlatform,
        topics: presetTopics.map((topic) => ({
          ...topic,
          systemPrompt:
            topic.id === selectedTopic?.id ? currentSystemPrompt : getTopicSystemPrompt(topic, currentSystemPrompt),
          answerStyle:
            topic.id === selectedTopic?.id ? currentAnswerStyle : getTopicAnswerStyle(topic, currentAnswerStyle),
        })),
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle: currentAnswerStyle,
        systemPrompt: currentSystemPrompt,
        generationPrompt,
        maxPushCount,
        savedAt: new Date().toISOString(),
      };
      return saveWorkspaceSession(payload);
    },
    onMutate: () => {
      setSaveState("saving");
      setStatusMessage("正在保存当前结果...");
    },
    onSuccess: (data) => {
      setSaveState("saved");
      setStatusMessage(`已保存到 ${data.filePath}`);
    },
    onError: (error: Error) => {
      setSaveState("error");
      setStatusMessage(error.message);
    },
  });

  const { setSelectedSource } = useWorkspaceStore();

  return {
    selectedPlatform,
    selectedSource,
    selectedContentMode,
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    generationPrompt,
    contentConstraint,
    maxPushCount,
    isBootstrapping: configQuery.isLoading || sessionQuery.isLoading,
    isCollecting: collectMutation.isPending,
    isGeneratingAll: generateAllMutation.isPending,
    collectingError: collectMutation.error,
    selectPlatform: setSelectedPlatform,
    selectSource: setSelectedSource,
    selectContentMode: setSelectedContentMode,
    selectTopic: setSelectedTopic,
    setQuestions,
    selectQuestion,
    setQuestionAnswer,
    setAnswerStyle: (value: string) => {
      setAnswerStyle(value);
      if (selectedTopic) {
        updateTopicPrompts(selectedTopic.id, { answerStyle: value });
      }
    },
    setSystemPrompt: (value: string) => {
      setSystemPrompt(value);
      if (selectedTopic) {
        updateTopicPrompts(selectedTopic.id, { systemPrompt: value });
      }
    },
    setMaxPushCount,
    setGenerationPrompt,
    setContentConstraint,
    collectQuestions: () => collectMutation.mutate(),
    importQuestionByUrl: (url: string) => importQuestionByUrlMutation.mutate(url),
    generateAllAnswers: () => generateAllMutation.mutate(),
    generateOneAnswer: (item: QuestionItem) => generateOneMutation.mutate(item),
    polishOneAnswer: (item: QuestionItem) => polishOneMutation.mutate(item),
    saveSession: () => saveMutation.mutate(),
    isGeneratingOne: (questionId: string) => generateOneMutation.isPending && generateOneMutation.variables?.id === questionId,
    isPolishingOne: (questionId: string) => polishOneMutation.isPending && polishOneMutation.variables?.id === questionId,
    isImportingQuestionUrl: importQuestionByUrlMutation.isPending,
  };
}
