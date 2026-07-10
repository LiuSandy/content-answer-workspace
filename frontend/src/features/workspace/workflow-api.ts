import { apiDelete, apiGet, apiPost } from "@/lib/api";
import { streamPost, type SseCallbacks } from "@/lib/sse";
import type {
  AgentChatPayload,
  AgentChatResponse,
  AgentTool,
  ChatConversationRunSnapshot,
  CollectPayload,
  CollectResponse,
  ConfigResponse,
  ConversationHistoryResponse,
  ConversationPayload,
  ConversationResponse,
  CreateChatConversationRunResponse,
  CreateGenerationJobResponse,
  GenerateAllPayload,
  GenerateAllResponse,
  GenerationJobSnapshot,
  GenerateOnePayload,
  GenerateOneResponse,
  HotlistResponse,
  ParseQuestionUrlPayload,
  ParseQuestionUrlResponse,
  PolishOnePayload,
  PolishOneResponse,
  SaveSessionPayload,
  SessionResponse,
  SessionSummary,
} from "@/types/workflow";

export function getWorkspaceConfig() {
  return apiGet<ConfigResponse>("/api/config");
}

export function getLatestSession() {
  return apiGet<SessionResponse>("/api/session/latest");
}

export function collectWorkflow(payload: CollectPayload) {
  return apiPost<CollectResponse>("/api/workflow/collect", payload);
}

export function parseQuestionUrl(payload: ParseQuestionUrlPayload) {
  return apiPost<ParseQuestionUrlResponse>("/api/workflow/parse-question-url", payload);
}

export function generateOneAnswer(payload: GenerateOnePayload) {
  return apiPost<GenerateOneResponse>("/api/workflow/generate-one", payload);
}

export function createGenerationJob(payload: GenerateOnePayload) {
  return apiPost<CreateGenerationJobResponse>("/api/workflow/generate-one/jobs", payload);
}

export function getGenerationJob(jobId: string) {
  return apiGet<GenerationJobSnapshot>(`/api/workflow/generate-one/jobs/${jobId}`);
}

export function cancelGenerationJob(jobId: string) {
  return apiDelete<{ jobId: string; status: "canceled" }>(`/api/workflow/generate-one/jobs/${jobId}`);
}

export function polishOneAnswer(payload: PolishOnePayload) {
  return apiPost<PolishOneResponse>("/api/workflow/polish-one", payload);
}

export function generateAllAnswers(payload: GenerateAllPayload) {
  return apiPost<GenerateAllResponse>("/api/workflow/generate", payload);
}

export function saveWorkspaceSession(payload: SaveSessionPayload) {
  return apiPost<{ filePath: string }>("/api/session/save", payload);
}

export function getHotlist(limit = 30) {
  return apiGet<HotlistResponse>(`/api/hotlist?limit=${limit}`);
}

export function agentChat(payload: AgentChatPayload) {
  return apiPost<AgentChatResponse>("/api/agent/chat", payload);
}

export function listAgentTools() {
  return apiGet<AgentTool[]>("/api/agent/tools");
}

export function listSessions() {
  return apiGet<SessionSummary[]>("/api/session/list");
}

export function createSession() {
  return apiPost<SessionSummary>("/api/session/new", {});
}

export function getSession(sessionId: string) {
  return apiGet<SessionResponse>(`/api/session/${sessionId}`);
}

export function sendConversationMessage(payload: ConversationPayload) {
  return apiPost<ConversationResponse>("/api/agent/conversation", payload);
}

export function createChatConversationRun(payload: ConversationPayload) {
  return apiPost<CreateChatConversationRunResponse>("/api/agent/conversation/runs", payload);
}

export function getChatConversationRun(runId: string) {
  return apiGet<ChatConversationRunSnapshot>(`/api/agent/conversation/runs/${runId}`);
}

export function cancelChatConversationRun(runId: string) {
  return apiDelete<{ runId: string; status: "canceled" }>(`/api/agent/conversation/runs/${runId}`);
}

export function getConversationHistory(sessionId: string) {
  return apiGet<ConversationHistoryResponse>(`/api/agent/conversation/${sessionId}/history`);
}

export function deleteSession(sessionId: string) {
  return apiDelete<void>(`/api/session/${sessionId}`);
}

export function streamGenerateOneAnswer(
  payload: GenerateOnePayload,
  callbacks: SseCallbacks<GenerateOneResponse>,
): Promise<void> {
  return streamPost("/api/workflow/generate-one/stream", payload, callbacks);
}

export function streamPolishOneAnswer(
  payload: PolishOnePayload,
  callbacks: SseCallbacks<PolishOneResponse>,
): Promise<void> {
  return streamPost("/api/workflow/polish-one/stream", payload, callbacks);
}

export function streamGenerateAllAnswers(
  payload: GenerateAllPayload,
  callbacks: SseCallbacks<GenerateAllResponse>,
): Promise<void> {
  return streamPost("/api/workflow/generate/stream", payload, callbacks);
}

export function streamConversationMessage(
  payload: ConversationPayload,
  callbacks: SseCallbacks<ConversationResponse>,
): Promise<void> {
  return streamPost("/api/agent/conversation/stream", payload, callbacks);
}

export function streamAgentChat(
  payload: AgentChatPayload,
  callbacks: SseCallbacks<AgentChatResponse>,
): Promise<void> {
  return streamPost("/api/agent/chat/stream", payload, callbacks);
}
