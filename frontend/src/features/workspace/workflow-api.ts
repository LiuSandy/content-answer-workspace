import { apiGet, apiPost } from "@/lib/api";
import type {
  CollectPayload,
  CollectResponse,
  ConfigResponse,
  GenerateAllPayload,
  GenerateAllResponse,
  GenerateOnePayload,
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

export function generateOneAnswer(payload: GenerateOnePayload) {
  return apiPost<{ answer: string }>("/api/workflow/generate-one", payload);
}

export function generateAllAnswers(payload: GenerateAllPayload) {
  return apiPost<GenerateAllResponse>("/api/workflow/generate", payload);
}

export function saveWorkspaceSession(payload: SaveSessionPayload) {
  return apiPost<{ filePath: string }>("/api/session/save", payload);
}
