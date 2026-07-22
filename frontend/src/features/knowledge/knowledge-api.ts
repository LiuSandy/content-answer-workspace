import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from "@/lib/api";
import type { KnowledgeDocument } from "./types";

export interface ListDocumentsResponse {
  documents: KnowledgeDocument[];
  total: number;
  limit: number;
  offset: number;
}

export async function fetchKnowledgeDocuments(
  workspaceId: string = "default",
  status?: string
): Promise<ListDocumentsResponse> {
  const query = new URLSearchParams({ workspaceId });
  if (status) query.append("status", status);
  return apiGet<ListDocumentsResponse>(`/api/knowledge/documents?${query.toString()}`);
}

export async function uploadKnowledgeDocument(
  file: File,
  workspaceId: string = "default"
): Promise<KnowledgeDocument> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("workspaceId", workspaceId);
  return apiUpload<KnowledgeDocument>("/api/knowledge/documents", formData);
}

export async function importKnowledgeUrl(
  url: string,
  workspaceId: string = "default"
): Promise<KnowledgeDocument> {
  return apiPost<KnowledgeDocument>("/api/knowledge/documents/import-url", {
    url,
    workspaceId,
  });
}

export async function fetchDocumentMarkdown(
  documentId: string,
  isCandidate: boolean = false
): Promise<{ documentId: string; markdown: string; isCandidate: boolean }> {
  return apiGet<{ documentId: string; markdown: string; isCandidate: boolean }>(
    `/api/knowledge/documents/${documentId}/markdown?isCandidate=${isCandidate}`
  );
}

export async function updateDocumentMarkdown(
  documentId: string,
  markdown: string,
  workspaceId: string = "default"
): Promise<void> {
  await apiPut(`/api/knowledge/documents/${documentId}/markdown`, {
    markdown,
    workspaceId,
  });
}

export async function confirmKnowledgeDocument(documentId: string): Promise<void> {
  await apiPost(`/api/knowledge/documents/${documentId}/confirm`, {});
}

export async function reconvertKnowledgeDocument(
  documentId: string
): Promise<{ status: string; diff?: string }> {
  return apiPost<{ status: string; diff?: string }>(
    `/api/knowledge/documents/${documentId}/reconvert`,
    {}
  );
}

export async function deleteKnowledgeDocument(documentId: string): Promise<void> {
  await apiDelete(`/api/knowledge/documents/${documentId}`);
}
