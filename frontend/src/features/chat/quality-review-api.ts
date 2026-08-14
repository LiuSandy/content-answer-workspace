// 质检（Quality Review）功能专属 API 层（roadmap R3）。
// 组件不得直接散落业务 fetch，统一通过本模块调用。

export interface QualityReviewRecordDTO {
  reportId: string;
  sourceVersionId?: string | null;
  overallScore?: number | null;
  dimensionScores?: Record<string, number>;
  issues?: Array<{ severity?: "major" | "minor"; description: string }>;
  suggestions?: string[];
  rewriteInstruction?: string | null;
  summary?: string;
  iterations: number;
  passed: boolean;
  selectedIteration: number;
  reviewStatus: "completed" | "failed";
  rounds?: Array<{ iteration: number; overallScore: number; passed: boolean }>;
  createdAt?: string | null;
}

async function unwrap<T>(response: Response): Promise<T> {
  let payload: any = {};
  try {
    payload = await response.json();
  } catch {
    // 非 JSON 响应
  }
  if (!response.ok) {
    throw new Error(payload?.error?.message || "请求失败，请稍后重试");
  }
  return payload?.data as T;
}

export async function listQualityReviews(documentId: string): Promise<QualityReviewRecordDTO[]> {
  const res = await fetch(`/api/documents/${documentId}/quality/reviews`);
  return unwrap<QualityReviewRecordDTO[]>(res);
}
