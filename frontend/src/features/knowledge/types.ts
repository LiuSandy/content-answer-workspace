export type KnowledgeDocumentStatus =
  "pending" | "awaiting_confirmation" | "indexing" | "available" | "failed" | "deleted";

export type SourceType = "pdf" | "markdown" | "text" | "image" | "url" | "history";

export type KnowledgeMode = "off" | "normal" | "strict";

export interface KnowledgeDocument {
  id: string;
  workspaceId: string;
  ownerId: string;
  sourceType: SourceType;
  title: string;
  sourceUri?: string;
  sourceUrl?: string;
  sourcePath?: string;
  markdownPath?: string;
  candidateMarkdownPath?: string;
  status: KnowledgeDocumentStatus;
  conversionConfidence?: number;
  conversionError?: string;
  hasManualEdits: boolean;
  createdAt: string;
  updatedAt: string;
  sourceFile?: KnowledgeSourceFile;
  sourceOnly?: boolean;
}

export interface KnowledgeIngestionJob {
  id: string;
  sourceFileId: string;
  attempt: number;
  status: "queued" | "running" | "succeeded" | "completed_with_errors" | "failed";
  stage: string;
  progressCurrent: number;
  progressTotal: number;
  progressPercent: number;
  retryCount: number;
  totalPages: number;
  completedPages: number;
  succeededPages: number;
  failedPages: number;
  currentPage?: number;
  errorCode?: string;
  errorMessage?: string;
  startedAt?: string;
  completedAt?: string;
  updatedAt: string;
}

export interface KnowledgeSourceFile {
  id: string;
  workspaceId: string;
  ownerId: string;
  ingestSource: "frontend_upload" | "directory_scan";
  originalFilename: string;
  originalRelativePath: string;
  currentRelativePath: string;
  extension: string;
  sizeBytes: number;
  contentHash?: string;
  status: "pending" | "processing" | "recognized" | "archived" | "failed";
  knowledgeDocumentId?: string;
  failureCode?: string;
  failureReason?: string;
  createdAt: string;
  updatedAt: string;
  job?: KnowledgeIngestionJob;
}

export function formatStatusBadge(status: KnowledgeDocumentStatus): {
  label: string;
  variant: "default" | "secondary" | "destructive" | "outline";
} {
  switch (status) {
    case "available":
      return { label: "可用", variant: "default" };
    case "awaiting_confirmation":
      return { label: "待确认", variant: "outline" };
    case "indexing":
      return { label: "索引中", variant: "secondary" };
    case "failed":
      return { label: "处理失败", variant: "destructive" };
    case "pending":
      return { label: "挂起中", variant: "outline" };
    case "deleted":
      return { label: "已删除", variant: "destructive" };
    default:
      return { label: status, variant: "outline" };
  }
}

export function isDocEditable(status: KnowledgeDocumentStatus): boolean {
  return status === "awaiting_confirmation" || status === "available" || status === "failed";
}
