import type { ChatCollectItem, ChatCollectResult, ChatMessage, Platform, WorkbenchItem } from "@/types/workflow";

export const DEFAULT_VISIBLE_COLLECT_RESULTS = 5;
export const FINAL_OUTPUT_STEP = "✍️ 正在整理最终回答…";

type AppendConversationTurnParams = {
  toolSteps: string[];
  collectResults: ChatCollectResult[];
  reply: string;
};

export type CollectGroupStat = {
  label: string;
  count: number;
};

export function appendConversationTurn(
  previous: ChatMessage[],
  { toolSteps, collectResults, reply }: AppendConversationTurnParams,
): ChatMessage[] {
  const committedSteps = toolSteps.filter((step) => step !== FINAL_OUTPUT_STEP);

  if (collectResults.length > 0) {
    return [
      ...previous,
      {
        role: "assistant",
        content: reply,
        ...(committedSteps.length > 0 ? { steps: committedSteps } : {}),
        collectResults,
      },
    ];
  }

  return [
    ...previous,
    ...(committedSteps.length > 0
      ? [{ role: "tool" as const, content: "", steps: committedSteps }]
      : []),
    { role: "assistant" as const, content: reply },
  ];
}

export function collectItemKey(result: ChatCollectResult, item: ChatCollectItem, index: number) {
  return item.url || `${result.platform}-${result.topic}-${item.title}-${index}`;
}

export function getVisibleCollectItems(result: ChatCollectResult, expanded: boolean) {
  if (expanded) return result.items;
  return result.items.slice(0, DEFAULT_VISIBLE_COLLECT_RESULTS);
}

export function toggleCollectSelection(selected: Set<string>, key: string) {
  const next = new Set(selected);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  return next;
}

export function getSelectedCollectItems(result: ChatCollectResult, selected: Set<string>) {
  return result.items.filter((item, index) => selected.has(collectItemKey(result, item, index)));
}

export function getCollectGroupStats(result: ChatCollectResult): CollectGroupStat[] {
  const counts = new Map<string, number>();
  result.items.forEach((item) => {
    const label = item.group || item.category;
    if (!label) return;
    counts.set(label, (counts.get(label) ?? 0) + 1);
  });
  return Array.from(counts.entries()).map(([label, count]) => ({ label, count }));
}

export function toWorkbenchItems(
  result: ChatCollectResult,
  selectedItems: ChatCollectItem[],
  now = new Date().toISOString(),
): WorkbenchItem[] {
  return selectedItems.map((item, index) => ({
    id: item.url || `${result.platform}-${result.topic}-${item.title}-${index}`,
    title: item.title,
    url: item.url || "",
    platform: result.platform as Platform,
    topic: result.topic,
    answerCount: 0,
    updatedTime: null,
    excerpt: item.excerpt ?? item.metric ?? "",
    detail: "",
    answer: "",
    addedAt: now,
    sourcePlatform: result.platform as Platform,
    sourceTopic: result.topic,
    promptConfig: { answerStyle: "", systemPrompt: "", generationPrompt: "" },
    generationStatus: "idle",
  }));
}
