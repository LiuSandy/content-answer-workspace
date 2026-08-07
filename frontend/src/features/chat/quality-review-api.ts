// 质检（Quality Review）功能专属 API 层（roadmap R3）。
// 组件不得直接散落业务 fetch，统一通过本模块调用。

export interface QualitySuggestionDTO {
  id: string;
  dimension: string;
  title: string;
  reason?: string;
  anchor?: string;
  replacement?: string;
  adopted?: boolean;
}

export interface QualityReportDTO {
  overallScore: number;
  dimensionScores: Record<string, number>;
  issues?: Array<{ severity?: string; description?: string }>;
  suggestions?: QualitySuggestionDTO[];
  summary?: string;
}

export interface QualityReviewDTO {
  reportId: string;
  sourceVersionId?: string | null;
  report: QualityReportDTO;
}

export interface QualityReviewRecordDTO {
  reportId: string;
  overallScore?: number | null;
  dimensionScores?: Record<string, number>;
  issues?: Array<{ severity?: string; description?: string }>;
  suggestions?: QualitySuggestionDTO[];
  summary?: string;
  sourceVersionId?: string | null;
  createdAt?: string | null;
}

export interface QualityReviewDocumentStateDTO {
  documentId: string;
  sourceItemId: string;
  currentContent: string | null;
  currentVersionId: string | null;
  lockVersion: number;
}

// 后端统一错误包装；409 时 code 为 document_conflict，用于冲突刷新
export class ApiError extends Error {
  code?: string;
  status?: number;
}

async function unwrap<T>(response: Response): Promise<T> {
  let payload: any = {};
  try {
    payload = await response.json();
  } catch {
    // 非 JSON 响应
  }
  if (!response.ok) {
    const err = new ApiError(payload?.error?.message || "请求失败，请稍后重试");
    err.code = payload?.error?.code;
    err.status = response.status;
    throw err;
  }
  return payload?.data as T;
}

export async function runQualityReview(documentId: string): Promise<QualityReviewDTO> {
  const res = await fetch(`/api/documents/${documentId}/quality/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return unwrap<QualityReviewDTO>(res);
}

export async function listQualityReviews(documentId: string): Promise<QualityReviewRecordDTO[]> {
  const res = await fetch(`/api/documents/${documentId}/quality/reviews`);
  return unwrap<QualityReviewRecordDTO[]>(res);
}

export async function adoptQualitySuggestion(
  documentId: string,
  params: { reportId: string; suggestionId: string; expectedLockVersion: number },
): Promise<QualityReviewDocumentStateDTO> {
  const res = await fetch(`/api/documents/${documentId}/quality/adopt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      reportId: params.reportId,
      suggestionId: params.suggestionId,
      expectedLockVersion: params.expectedLockVersion,
    }),
  });
  return unwrap<QualityReviewDocumentStateDTO>(res);
}
