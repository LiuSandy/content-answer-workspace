import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from "@/lib/api";
import type { KnowledgeDocument, KnowledgeSourceFile } from "./types";

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
): Promise<{ sourceFileId: string; status: string; outcome: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("workspaceId", workspaceId);
  return apiUpload<{ sourceFileId: string; status: string; outcome: string }>(
    "/api/knowledge/documents",
    formData
  );
}

export interface SourceFileScanResult {
  discovered: number;
  queued: number;
  duplicates: number;
  failed: number;
}

export async function scanKnowledgeSourceFiles(
  workspaceId: string = "default"
): Promise<SourceFileScanResult> {
  return apiPost<SourceFileScanResult>(
    `/api/knowledge/source-files/scan?workspaceId=${encodeURIComponent(workspaceId)}`,
    {}
  );
}

export async function fetchKnowledgeSourceFiles(
  workspaceId: string = "default"
): Promise<{ sourceFiles: KnowledgeSourceFile[] }> {
  return apiGet<{ sourceFiles: KnowledgeSourceFile[] }>(
    `/api/knowledge/source-files?workspaceId=${encodeURIComponent(workspaceId)}`
  );
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

export interface TestRetrievalResponse {
  query: string;
  rewrittenQuery?: string;
  hasEvidence: boolean;
  fallbackReason?: string;
  contextText?: string;
  sources?: Array<{
    documentId: string;
    title: string;
    sourceUrl?: string;
    headingPath?: string;
    text?: string;
    score?: number;
    label?: string;
  }>;
  traceHits?: Array<{
    chunk_id: string;
    document_id: string;
    retrieval_source: string;
    heading_path?: string;
    rank: number;
    bm25_score: number;
    vector_score: number;
    rrf_score: number;
    rerank_score: number | null;
    included_in_context: boolean;
    citation_label?: string;
    context_snapshot?: string;
  }>;
  indexVersion?: string;
  pipelineSteps?: Array<{
    step: string;
    title: string;
    status: "ok" | "skipped" | "error" | "blocked";
    durationMs: number;
    detail: string;
  }>;
}

export async function testKnowledgeRetrieval(
  query: string,
  mode: string = "normal",
  workspaceId: string = "default"
): Promise<TestRetrievalResponse> {
  return apiPost<TestRetrievalResponse>("/api/knowledge/test-search", {
    query,
    mode,
    workspaceId,
  });
}
