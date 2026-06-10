export const DEFAULT_PLATFORM = "zhihu" as const;

export type Platform = typeof DEFAULT_PLATFORM;

export type Topic = {
  id: string;
  name: string;
  keywords: string[];
  expandedHints?: string[];
  answerStyle?: string;
  systemPrompt?: string;
};

export type WorkflowConfig = {
  platform: Platform;
  maxPushCount: number;
  sortModes: string[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  testMode: boolean;
  skipAnswerGeneration: boolean;
  userAgent: string;
  ctaText: string;
  outputDir: string;
};

export type QuestionItem = {
  id: string;
  platform?: Platform;
  title: string;
  url: string;
  answerCount: number;
  updatedTime?: string | null;
  excerpt: string;
  detail: string;
  topic: string;
  answer: string;
  images?: string[];
  imagePrompts?: string[];
};

export type ConfigResponse = {
  topics: Topic[];
  workflow: WorkflowConfig;
};

export type SessionResponse = {
  session: {
    platform?: Platform;
    topics?: Topic[];
    answerStyle?: string;
    systemPrompt?: string;
    generationPrompt?: string;
    maxPushCount?: number;
    items?: QuestionItem[];
  } | null;
};

export type CollectResponse = {
  platform: Platform;
  config: WorkflowConfig;
  topics: Topic[];
  items: QuestionItem[];
};

export type ParseQuestionUrlPayload = {
  platform: Platform;
  url: string;
  topic?: Topic;
};

export type ParseQuestionUrlResponse = {
  item: QuestionItem;
};

export type GenerateOneResponse = {
  item: QuestionItem;
};

export type GenerateAllResponse = {
  items: QuestionItem[];
};

export type CollectPayload = {
  platform: Platform;
  topics: Topic[];
  maxPushCount: number;
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  skipAnswerGeneration: boolean;
};

export type GenerateOnePayload = {
  platform: Platform;
  item: QuestionItem;
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
};

export type GenerateAllPayload = {
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  maxPushCount: number;
};

export type SaveSessionPayload = {
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  maxPushCount: number;
  savedAt: string;
};
