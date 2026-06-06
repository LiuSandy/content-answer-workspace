export type Topic = {
  id: string;
  name: string;
  keywords: string[];
  expandedHints?: string[];
};

export type WorkflowConfig = {
  maxPushCount: number;
  sortModes: string[];
  answerStyle: string;
  systemPrompt: string;
  testMode: boolean;
  skipAnswerGeneration: boolean;
  userAgent: string;
  ctaText: string;
  outputDir: string;
};

export type QuestionItem = {
  id: string;
  title: string;
  url: string;
  answerCount: number;
  updatedTime?: string | null;
  excerpt: string;
  detail: string;
  topic: string;
  answer: string;
};

export type ConfigResponse = {
  topics: Topic[];
  workflow: WorkflowConfig;
};

export type SessionResponse = {
  session: {
    topics?: Topic[];
    answerStyle?: string;
    systemPrompt?: string;
    maxPushCount?: number;
    items?: QuestionItem[];
  } | null;
};

export type CollectResponse = {
  config: WorkflowConfig;
  topics: Topic[];
  items: QuestionItem[];
};

export type GenerateAllResponse = {
  items: QuestionItem[];
};
