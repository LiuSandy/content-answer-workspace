export const DEFAULT_PLATFORM = "zhihu" as const;

export type Platform = typeof DEFAULT_PLATFORM | "xiaohongshu";

export type CollectSource = "official" | "web" | "auto";

export type ContentMode = "answer" | "imitate";

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
  contentMode?: ContentMode;
};

export type ConfigResponse = {
  topics: Topic[];
  workflow: WorkflowConfig;
};

export type SessionResponse = {
  session: {
    sessionId?: string;
    title?: string;
    createdAt?: string;
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
  source?: CollectSource;
  contentMode?: ContentMode;
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
  contentConstraint?: string;
};

export type PolishOnePayload = {
  platform: Platform;
  item: QuestionItem;
  currentAnswer: string;
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  contentConstraint?: string;
};

export type PolishOneResponse = {
  item: QuestionItem;
};

export type GenerateAllPayload = {
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  contentConstraint?: string;
  maxPushCount: number;
};

export type SaveSessionPayload = {
  sessionId?: string;
  platform: Platform;
  topics: Topic[];
  items: QuestionItem[];
  answerStyle: string;
  systemPrompt: string;
  generationPrompt: string;
  maxPushCount: number;
  savedAt: string;
};

export type AgentChatPayload = {
  sessionId: string;
  questionId?: string;
  message: string;
  currentAnswer?: string;
};

export type AgentChatResponse = {
  reply: string;
  answerUpdated: boolean;
  updatedAnswer?: string;
  operationSummary: string;
};

export type HotlistAnalysisResult = {
  topicDistribution: {
    field: string;
    count: number;
    examples: string[];
  }[];
  contentOpportunities: {
    direction: string;
    reason: string;
  }[];
  audienceMood: string;
  recommendations: {
    topic: string;
    reason: string;
    keywords: string[];
  }[];
};

export type AnalysisStatus =
  | { type: "idle" }
  | { type: "loading" }
  | { type: "success"; data: HotlistAnalysisResult }
  | { type: "error"; raw: string };

export type HotlistItem = {
  rank: number;
  title: string;
  url: string;
  thumbnailUrl: string;
  summary: string;
  heat: string;
};

export type HotlistResponse = {
  items: HotlistItem[];
  fetchedAt: string;
};

export type SessionSummary = {
  sessionId: string;
  title: string;
  createdAt: string;
};

/** Chat 采集结果卡片的单条内容项 */
export type ChatCollectItem = {
  title: string;
  url: string;
  excerpt?: string;
  /** 格式化后的核心指标，如 "1.2万 赞" 或 "312 个回答" */
  metric?: string;
  author?: string;
};

/** Chat 消息中嵌入的采集结果数据（role === "collect" 时存在） */
export type ChatCollectResult = {
  platform: Platform | string;
  topic: string;
  items: ChatCollectItem[];
};

export type ChatMessage = {
  role: "user" | "assistant" | "tool" | "collect";
  content: string;
  /** tool 角色专用：工具调用过程的逐步文案 */
  steps?: string[];
  /** collect 角色专用：结构化采集结果 */
  collectResult?: ChatCollectResult;
};

export type ConversationPayload = {
  sessionId: string;
  message: string;
};

export type ConversationResponse = {
  reply: string;
};

export type ConversationHistoryResponse = {
  messages: ChatMessage[];
};

export type AgentTool = {
  name: string;
  description: string;
};

export type GenerationStatus = "idle" | "generating" | "done" | "error" | "interrupted";

/** 工作台问题条目，在 QuestionItem 基础上附加来源元数据与提示词快照。 */
export type WorkbenchItem = QuestionItem & {
  /** 加入工作台的时间，用于排序 */
  addedAt: string;
  /** 来源平台 */
  sourcePlatform: Platform;
  /** 来源主题名称 */
  sourceTopic: string;
  /** 采集时的提示词快照，生成回答时使用 */
  promptConfig: {
    answerStyle: string;
    systemPrompt: string;
    generationPrompt: string;
  };
  /** AI 回答生成状态；不能只用 answer 是否为空判断是否完整生成。 */
  generationStatus?: GenerationStatus;
  /** 生成失败或中断时的可展示错误。 */
  generationError?: string;
};
