import { apiGet, apiPost } from "@/lib/api";
import type {
  CollectPayload,
  CollectResponse,
  ConfigResponse,
  GenerateAllPayload,
  GenerateAllResponse,
  GenerateOnePayload,
  GenerateOneResponse,
  HotlistResponse,
  ParseQuestionUrlPayload,
  ParseQuestionUrlResponse,
  PolishOnePayload,
  PolishOneResponse,
  SaveSessionPayload,
  SessionResponse,
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
