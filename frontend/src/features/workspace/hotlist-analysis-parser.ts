import type { HotlistAnalysisResult } from "@/types/workflow";

export function parseAnalysisResult(raw: string): HotlistAnalysisResult | null {
  try {
    // 兼容 LLM 偶发包裹 markdown code block 的情况
    let cleaned = raw.trim();
    if (cleaned.startsWith("```")) {
      cleaned = cleaned.replace(/^```[a-z]*\n?/, "").replace(/```$/, "").trim();
    }
    const parsed = JSON.parse(cleaned);
    if (
      !Array.isArray(parsed.topicDistribution) ||
      !Array.isArray(parsed.contentOpportunities) ||
      !Array.isArray(parsed.recommendations) ||
      typeof parsed.audienceMood !== "string"
    ) {
      return null;
    }
    return parsed as HotlistAnalysisResult;
  } catch {
    return null;
  }
}
