import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { useWorkspaceStore } from "@/store/workspace-store";
import type {
  CollectPayload,
  GenerateAllPayload,
  GenerateOnePayload,
  Platform,
  QuestionItem,
  SaveSessionPayload,
} from "@/types/workflow";

import { defaultPlatform, fallbackTopics, fallbackWorkflow } from "./defaults";
import {
  collectWorkflow,
  generateAllAnswers,
  generateOneAnswer,
  getLatestSession,
  getWorkspaceConfig,
  saveWorkspaceSession,
} from "./workflow-api";

function withPlatform<T extends { platform?: Platform }>(item: T, platform: Platform): T {
  return {
    ...item,
    platform: item.platform ?? platform,
  };
}

export function useWorkspace() {
  const {
    selectedPlatform,
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    maxPushCount,
    setSelectedPlatform,
    setPresetTopics,
    setSelectedTopic,
    setQuestions,
    setQuestionAnswer,
    selectQuestion,
    setAnswerStyle,
    setSystemPrompt,
    setMaxPushCount,
    setIsCollecting,
    setIsGeneratingAll,
    setSaveState,
    setStatusMessage,
  } = useWorkspaceStore();

  const configQuery = useQuery({
    queryKey: ["workspace-config"],
    queryFn: getWorkspaceConfig,
  });

  const sessionQuery = useQuery({
    queryKey: ["workspace-session"],
    queryFn: getLatestSession,
  });

  useEffect(() => {
    if (configQuery.data) {
      setSelectedPlatform(configQuery.data.workflow.platform ?? defaultPlatform);
      setPresetTopics(configQuery.data.topics);
      setAnswerStyle(configQuery.data.workflow.answerStyle);
      setSystemPrompt(configQuery.data.workflow.systemPrompt);
      setMaxPushCount(configQuery.data.workflow.maxPushCount);
      if (!selectedTopic) {
        setSelectedTopic(configQuery.data.topics[0] ?? null);
      }
      setStatusMessage("配置加载完成，可以开始采集问题。");
    }
  }, [
    configQuery.data,
    selectedTopic,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  useEffect(() => {
    if (configQuery.isError) {
      setSelectedPlatform(fallbackWorkflow.platform);
      setPresetTopics(fallbackTopics);
      setAnswerStyle(fallbackWorkflow.answerStyle);
      setSystemPrompt(fallbackWorkflow.systemPrompt);
      setMaxPushCount(fallbackWorkflow.maxPushCount);
      if (!selectedTopic) {
        setSelectedTopic(fallbackTopics[0] ?? null);
      }
      setStatusMessage("配置接口加载失败，已回退到本地默认主题。");
    }
  }, [
    configQuery.isError,
    selectedTopic,
    setAnswerStyle,
    setMaxPushCount,
    setPresetTopics,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  useEffect(() => {
    const session = sessionQuery.data?.session;
    if (!session) {
      return;
    }
    const sessionPlatform = session.platform ?? selectedPlatform;
    setSelectedPlatform(sessionPlatform);
    if (session.answerStyle) {
      setAnswerStyle(session.answerStyle);
    }
    if (session.systemPrompt) {
      setSystemPrompt(session.systemPrompt);
    }
    if (session.maxPushCount) {
      setMaxPushCount(session.maxPushCount);
    }
    if (session.topics?.length) {
      setSelectedTopic(session.topics[0]);
    }
    if (session.items?.length) {
      setQuestions(session.items.map((item) => withPlatform(item, sessionPlatform)));
      setStatusMessage("已恢复最近一次保存的会话。");
    }
  }, [
    sessionQuery.data,
    selectedPlatform,
    setAnswerStyle,
    setMaxPushCount,
    setQuestions,
    setSelectedPlatform,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  const collectMutation = useMutation({
    mutationFn: () => {
      const payload: CollectPayload = {
        platform: selectedPlatform,
        topics: selectedTopic ? [selectedTopic] : [],
        maxPushCount,
        answerStyle,
        systemPrompt,
        skipAnswerGeneration: true,
      };
      return collectWorkflow(payload);
    },
    onMutate: () => {
      setIsCollecting(true);
      setStatusMessage("正在连接知乎并采集候选问题...");
    },
    onSuccess: (data) => {
      const responsePlatform = data.platform ?? data.config.platform ?? selectedPlatform;
      setSelectedPlatform(responsePlatform);
      setQuestions(data.items.map((item) => withPlatform(item, responsePlatform)));
      setStatusMessage(`采集完成，本次获取 ${data.items.length} 条问题。`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
    onSettled: () => {
      setIsCollecting(false);
    },
  });

  const generateAllMutation = useMutation({
    mutationFn: () => {
      const payload: GenerateAllPayload = {
        platform: selectedPlatform,
        topics: selectedTopic ? [selectedTopic] : [],
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle,
        systemPrompt,
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
      const payload: GenerateOnePayload = {
        platform: selectedPlatform,
        item: withPlatform(item, selectedPlatform),
        answerStyle,
        systemPrompt,
      };
      return generateOneAnswer(payload);
    },
    onSuccess: (data, item) => {
      setQuestionAnswer(item.id, data.answer);
      setStatusMessage(`已生成：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload: SaveSessionPayload = {
        platform: selectedPlatform,
        topics: selectedTopic ? [selectedTopic] : [],
        items: questions.map((item) => withPlatform(item, selectedPlatform)),
        answerStyle,
        systemPrompt,
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

  return {
    selectedPlatform,
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    maxPushCount,
    isBootstrapping: configQuery.isLoading || sessionQuery.isLoading,
    isCollecting: collectMutation.isPending,
    isGeneratingAll: generateAllMutation.isPending,
    collectingError: collectMutation.error,
    selectPlatform: setSelectedPlatform,
    selectTopic: setSelectedTopic,
    setQuestions,
    selectQuestion,
    setQuestionAnswer,
    setAnswerStyle,
    setSystemPrompt,
    setMaxPushCount,
    collectQuestions: () => collectMutation.mutate(),
    generateAllAnswers: () => generateAllMutation.mutate(),
    generateOneAnswer: (item: QuestionItem) => generateOneMutation.mutate(item),
    saveSession: () => saveMutation.mutate(),
    isGeneratingOne: (questionId: string) => generateOneMutation.isPending && generateOneMutation.variables?.id === questionId,
  };
}
