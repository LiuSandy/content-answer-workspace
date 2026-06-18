import { create } from "zustand";

import { DEFAULT_PLATFORM, type CollectSource, type Platform, type QuestionItem, type Topic } from "@/types/workflow";

type SaveState = "idle" | "saving" | "saved" | "error";

type WorkspaceState = {
  selectedPlatform: Platform;
  selectedSource: CollectSource;
  presetTopics: Topic[];
  selectedTopic: Topic | null;
  questions: QuestionItem[];
  selectedQuestionId: string | null;
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  contentConstraint: string;
  maxPushCount: number;
  isCollecting: boolean;
  isGeneratingAll: boolean;
  saveState: SaveState;
  statusMessage: string;
  setSelectedPlatform: (platform: Platform) => void;
  setSelectedSource: (source: CollectSource) => void;
  setPresetTopics: (topics: Topic[]) => void;
  setSelectedTopic: (topic: Topic | null) => void;
  updateTopicPrompts: (topicId: string, prompts: { systemPrompt?: string; answerStyle?: string }) => void;
  setQuestions: (questions: QuestionItem[]) => void;
  setQuestionAnswer: (questionId: string, answer: string) => void;
  setQuestionItem: (questionId: string, item: QuestionItem) => void;
  selectQuestion: (questionId: string | null) => void;
  updateQuestionAnswer: (questionId: string, answer: string) => void;
  setAnswerStyle: (value: string) => void;
  setSystemPrompt: (value: string) => void;
  setGenerationPrompt: (value: string) => void;
  setContentConstraint: (value: string) => void;
  setMaxPushCount: (value: number) => void;
  setIsCollecting: (value: boolean) => void;
  setIsGeneratingAll: (value: boolean) => void;
  setSaveState: (value: SaveState) => void;
  setStatusMessage: (value: string) => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedPlatform: DEFAULT_PLATFORM,
  selectedSource: "auto",
  presetTopics: [],
  selectedTopic: null,
  questions: [],
  selectedQuestionId: null,
  answerStyle: "",
  systemPrompt: "",
  generationPrompt: "",
  contentConstraint: "",
  maxPushCount: 10,
  isCollecting: false,
  isGeneratingAll: false,
  saveState: "idle",
  statusMessage: "正在初始化工作台...",
  setSelectedPlatform: (selectedPlatform) => set({ selectedPlatform }),
  setSelectedSource: (selectedSource) => set({ selectedSource }),
  setPresetTopics: (topics) => set({ presetTopics: topics }),
  setSelectedTopic: (topic) => set({ selectedTopic: topic }),
  updateTopicPrompts: (topicId, prompts) =>
    set((state) => {
      const presetTopics = state.presetTopics.map((topic) =>
        topic.id === topicId
          ? {
              ...topic,
              systemPrompt: prompts.systemPrompt ?? topic.systemPrompt,
              answerStyle: prompts.answerStyle ?? topic.answerStyle,
            }
          : topic,
      );
      const selectedTopic =
        state.selectedTopic?.id === topicId
          ? {
              ...state.selectedTopic,
              systemPrompt: prompts.systemPrompt ?? state.selectedTopic.systemPrompt,
              answerStyle: prompts.answerStyle ?? state.selectedTopic.answerStyle,
            }
          : state.selectedTopic;
      return { presetTopics, selectedTopic };
    }),
  setQuestions: (questions) =>
    set((state) => ({
      questions,
      selectedQuestionId:
        questions.find((item) => item.id === state.selectedQuestionId)?.id ?? questions[0]?.id ?? null,
    })),
  setQuestionAnswer: (questionId, answer) =>
    set((state) => ({
      questions: state.questions.map((question) =>
        question.id === questionId ? { ...question, answer } : question,
      ),
    })),
  setQuestionItem: (questionId, item) =>
    set((state) => ({
      questions: state.questions.map((question) => (question.id === questionId ? item : question)),
    })),
  selectQuestion: (selectedQuestionId) => set({ selectedQuestionId }),
  updateQuestionAnswer: (questionId, answer) =>
    set((state) => ({
      questions: state.questions.map((question) =>
        question.id === questionId ? { ...question, answer } : question,
      ),
    })),
  setAnswerStyle: (answerStyle) => set({ answerStyle }),
  setSystemPrompt: (systemPrompt) => set({ systemPrompt }),
  setGenerationPrompt: (generationPrompt) => set({ generationPrompt }),
  setContentConstraint: (contentConstraint) => set({ contentConstraint }),
  setMaxPushCount: (maxPushCount) => set({ maxPushCount }),
  setIsCollecting: (isCollecting) => set({ isCollecting }),
  setIsGeneratingAll: (isGeneratingAll) => set({ isGeneratingAll }),
  setSaveState: (saveState) => set({ saveState }),
  setStatusMessage: (statusMessage) => set({ statusMessage }),
}));
