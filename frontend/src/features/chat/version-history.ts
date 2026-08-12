import type { QualityReviewRecordDTO } from "./quality-review-api";

export const currentVersionBadgeClass =
  "h-5 rounded-full bg-slate-950 px-2 text-[10px] font-semibold text-white hover:bg-slate-950 dark:bg-slate-100 dark:text-slate-950 dark:hover:bg-slate-100";

export function modelLabel(provider: string | null, model: string | null): string {
  if (provider && model) return `${provider}/${model}`;
  return model || provider || "未记录模型";
}

export function reviewLabel(review: QualityReviewRecordDTO | null): string {
  if (!review || typeof review.overallScore !== "number") return "暂无评审";
  return `评审 ${review.overallScore} 分 · ${review.passed ? "已达标" : "未达标"}`;
}

export function compactOutlineLabel(versionNumber: number | null, sectionCount: number): string {
  if (!versionNumber) return "无大纲";
  return `O${versionNumber} · ${sectionCount}章`;
}

export function compactReviewLabel(review: QualityReviewRecordDTO | null): string {
  if (!review || typeof review.overallScore !== "number") return "无评审";
  return `${review.overallScore}分 · ${review.passed ? "达标" : "待优化"}`;
}
