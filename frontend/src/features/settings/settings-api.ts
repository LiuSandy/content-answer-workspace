/**
 * 所有设置相关 API 调用；单独定义是为了让 use-settings.ts 的 hooks 和组件都从同一入口访问后端。
 */

export interface LlmConfig {
  baseUrl: string;
  model: string;
  apiKey: string;
}

export interface CollectConfig {
  defaultPlatform: string;
  maxPushCount: number;
  sortModes: string[];
  userAgent: string;
  skipAnswerGeneration: boolean;
}

export interface PublishConfig {
  testMode: boolean;
  officialAccountName: string;
  ctaText: string;
}

export interface AgentReachConfig {
  enabledPlatforms: string[];
  groqApiKey: string;
}

export interface AllSettings {
  llm: LlmConfig;
  collect: CollectConfig;
  publish: PublishConfig;
  agentReach: AgentReachConfig;
}

export interface TopicItem {
  id: string;
  name: string;
  keywords: string[];
  expandedHints: string[];
}

export interface AgentReachStatus {
  ok: boolean;
  data?: Record<string, unknown>;
  error?: string;
  platforms?: Record<string, unknown>;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function getSettings(): Promise<AllSettings> {
  const res = await fetchJson<{ ok: boolean; data: AllSettings }>("/api/settings");
  return res.data;
}

export async function updateLlmSettings(payload: {
  baseUrl: string;
  model: string;
  apiKey?: string;
}): Promise<void> {
  await fetchJson("/api/settings/llm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateCollectSettings(payload: Partial<CollectConfig>): Promise<void> {
  await fetchJson("/api/settings/collect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updatePublishSettings(payload: Partial<PublishConfig>): Promise<void> {
  await fetchJson("/api/settings/publish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getAgentReachStatus(): Promise<AgentReachStatus> {
  return fetchJson<AgentReachStatus>("/api/settings/agent-reach/status");
}

export async function updateAgentReachPlatforms(enabledPlatforms: string[]): Promise<void> {
  await fetchJson("/api/settings/agent-reach/platforms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabledPlatforms }),
  });
}

export async function configureGroqKey(key: string): Promise<void> {
  await fetchJson("/api/settings/agent-reach/groq-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
}

export async function getTopics(): Promise<TopicItem[]> {
  const res = await fetchJson<{ ok: boolean; data: TopicItem[] }>("/api/settings/topics");
  return res.data;
}

export async function createTopic(topic: TopicItem): Promise<TopicItem[]> {
  const res = await fetchJson<{ ok: boolean; data: TopicItem[] }>("/api/settings/topics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(topic),
  });
  return res.data;
}

export async function updateTopic(topicId: string, topic: TopicItem): Promise<TopicItem[]> {
  const res = await fetchJson<{ ok: boolean; data: TopicItem[] }>(
    `/api/settings/topics/${topicId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(topic),
    },
  );
  return res.data;
}

export async function deleteTopic(topicId: string): Promise<TopicItem[]> {
  const res = await fetchJson<{ ok: boolean; data: TopicItem[] }>(
    `/api/settings/topics/${topicId}`,
    { method: "DELETE" },
  );
  return res.data;
}

export interface TwitterAuth {
  authToken: string;
  ct0: string;
  configured: boolean;
}

export async function getTwitterAuth(): Promise<TwitterAuth> {
  const res = await fetchJson<{ ok: boolean; data: TwitterAuth }>(
    "/api/settings/agent-reach/twitter-auth",
  );
  return res.data;
}

export async function saveTwitterAuth(authToken: string, ct0: string): Promise<void> {
  await fetchJson("/api/settings/agent-reach/twitter-auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ authToken, ct0 }),
  });
}

export async function restartServer(): Promise<void> {
  await fetch("/api/settings/restart", { method: "POST" }).catch(() => {
    // 重启时连接断开属正常现象，忽略 fetch 错误
  });
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch("/api/health");
    return res.ok;
  } catch {
    return false;
  }
}
