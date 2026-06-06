import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { apiGet, apiPost } from "@/lib/api";
import { useWorkspaceStore } from "@/store/workspace-store";
import type {
  CollectResponse,
  ConfigResponse,
  GenerateAllResponse,
  QuestionItem,
  SessionResponse,
} from "@/types/workflow";

import { fallbackTopics, fallbackWorkflow } from "./defaults";

export function useWorkspace() {
  const {
    presetTopics,
    selectedTopic,
    questions,
    selectedQuestionId,
    answerStyle,
    systemPrompt,
    maxPushCount,
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
    queryFn: () => apiGet<ConfigResponse>("/api/config"),
  });

  const sessionQuery = useQuery({
    queryKey: ["workspace-session"],
    queryFn: () => apiGet<SessionResponse>("/api/session/latest"),
  });

  useEffect(() => {
    if (configQuery.data) {
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
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  useEffect(() => {
    if (configQuery.isError) {
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
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  useEffect(() => {
    const session = sessionQuery.data?.session;
    if (!session) {
      return;
    }
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
      setQuestions(session.items);
      setStatusMessage("已恢复最近一次保存的会话。");
    }
  }, [
    sessionQuery.data,
    setAnswerStyle,
    setMaxPushCount,
    setQuestions,
    setSelectedTopic,
    setStatusMessage,
    setSystemPrompt,
  ]);

  const collectMutation = useMutation({
    mutationFn: () =>
      apiPost<CollectResponse>("/api/workflow/collect", {
        topics: selectedTopic ? [selectedTopic] : [],
        maxPushCount,
        answerStyle,
        systemPrompt,
        skipAnswerGeneration: true,
      }),
    onMutate: () => {
      setIsCollecting(true);
      setStatusMessage("正在连接知乎并采集候选问题...");
    },
    onSuccess: (data) => {
      setQuestions(data.items);
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
    mutationFn: () =>
      apiPost<GenerateAllResponse>("/api/workflow/generate", {
        topics: selectedTopic ? [selectedTopic] : [],
        items: questions,
        answerStyle,
        systemPrompt,
        maxPushCount,
      }),
    onMutate: () => {
      setIsGeneratingAll(true);
      setStatusMessage("正在批量生成回答...");
    },
    onSuccess: (data) => {
      setQuestions(data.items);
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
    mutationFn: (item: QuestionItem) =>
      apiPost<{ answer: string }>("/api/workflow/generate-one", {
        item,
        answerStyle,
        systemPrompt,
      }),
    onSuccess: (data, item) => {
      setQuestionAnswer(item.id, data.answer);
      setStatusMessage(`已生成：${item.title}`);
    },
    onError: (error: Error) => {
      setStatusMessage(error.message);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      apiPost<{ filePath: string }>("/api/session/save", {
        topics: selectedTopic ? [selectedTopic] : [],
        items: questions,
        answerStyle,
        systemPrompt,
        maxPushCount,
        savedAt: new Date().toISOString(),
      }),
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
