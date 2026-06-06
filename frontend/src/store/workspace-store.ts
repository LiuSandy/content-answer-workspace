import { create } from "zustand";

import { DEFAULT_PLATFORM, type Platform, type QuestionItem, type Topic } from "@/types/workflow";

type SaveState = "idle" | "saving" | "saved" | "error";

type WorkspaceState = {
  selectedPlatform: Platform;
  presetTopics: Topic[];
  selectedTopic: Topic | null;
  questions: QuestionItem[];
  selectedQuestionId: string | null;
  answerStyle: string;
  systemPrompt: string;
  maxPushCount: number;
  isCollecting: boolean;
  isGeneratingAll: boolean;
  saveState: SaveState;
  statusMessage: string;
  setSelectedPlatform: (platform: Platform) => void;
  setPresetTopics: (topics: Topic[]) => void;
  setSelectedTopic: (topic: Topic | null) => void;
  setQuestions: (questions: QuestionItem[]) => void;
  setQuestionAnswer: (questionId: string, answer: string) => void;
  selectQuestion: (questionId: string | null) => void;
  updateQuestionAnswer: (questionId: string, answer: string) => void;
  setAnswerStyle: (value: string) => void;
  setSystemPrompt: (value: string) => void;
  setMaxPushCount: (value: number) => void;
  setIsCollecting: (value: boolean) => void;
  setIsGeneratingAll: (value: boolean) => void;
  setSaveState: (value: SaveState) => void;
  setStatusMessage: (value: string) => void;
};

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  selectedPlatform: DEFAULT_PLATFORM,
  presetTopics: [],
  selectedTopic: null,
  questions: [],
  selectedQuestionId: null,
  answerStyle: "",
  systemPrompt: "",
  maxPushCount: 10,
  isCollecting: false,
  isGeneratingAll: false,
  saveState: "idle",
  statusMessage: "正在初始化工作台...",
  setSelectedPlatform: (selectedPlatform) => set({ selectedPlatform }),
  setPresetTopics: (topics) => set({ presetTopics: topics }),
  setSelectedTopic: (topic) => set({ selectedTopic: topic }),
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
  selectQuestion: (selectedQuestionId) => set({ selectedQuestionId }),
  updateQuestionAnswer: (questionId, answer) =>
    set((state) => ({
      questions: state.questions.map((question) =>
        question.id === questionId ? { ...question, answer } : question,
      ),
    })),
  setAnswerStyle: (answerStyle) => set({ answerStyle }),
  setSystemPrompt: (systemPrompt) => set({ systemPrompt }),
  setMaxPushCount: (maxPushCount) => set({ maxPushCount }),
  setIsCollecting: (isCollecting) => set({ isCollecting }),
  setIsGeneratingAll: (isGeneratingAll) => set({ isGeneratingAll }),
  setSaveState: (saveState) => set({ saveState }),
  setStatusMessage: (statusMessage) => set({ statusMessage }),
}));
