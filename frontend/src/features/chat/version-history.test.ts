import { describe, expect, test } from "bun:test";

import {
  compactOutlineLabel,
  compactReviewLabel,
  currentVersionBadgeClass,
  modelLabel,
  reviewLabel,
} from "./version-history";

describe("version history presentation", () => {
  test("uses a high contrast current-version badge", () => {
    expect(currentVersionBadgeClass).toContain("bg-slate-950");
    expect(currentVersionBadgeClass).toContain("text-white");
    expect(currentVersionBadgeClass).toContain("dark:bg-slate-100");
    expect(currentVersionBadgeClass).toContain("dark:text-slate-950");
  });

  test("formats model and review labels without version type", () => {
    expect(modelLabel("deepseek", "deepseek-v4-pro")).toBe("deepseek/deepseek-v4-pro");
    expect(modelLabel(null, "deepseek-v4-pro")).toBe("deepseek-v4-pro");
    expect(reviewLabel({
      reportId: "review-1",
      overallScore: 86,
      passed: true,
      iterations: 1,
      selectedIteration: 1,
      reviewStatus: "completed",
    })).toBe("评审 86 分 · 已达标");
    expect(reviewLabel(null)).toBe("暂无评审");
  });

  test("formats compact outline and review actions for dense history cards", () => {
    expect(compactOutlineLabel(2, 6)).toBe("O2 · 6章");
    expect(compactOutlineLabel(null, 0)).toBe("无大纲");
    expect(compactReviewLabel({
      reportId: "review-1",
      overallScore: 92,
      passed: true,
      iterations: 2,
      selectedIteration: 2,
      reviewStatus: "completed",
    })).toBe("92分 · 达标");
    expect(compactReviewLabel(null)).toBe("无评审");
  });
});
