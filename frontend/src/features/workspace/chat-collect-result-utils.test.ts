import { beforeEach, describe, expect, test } from "bun:test";

import type { ChatCollectResult, ChatMessage } from "@/types/workflow";

import {
  buildChatRunStreamUrl,
  clearStoredChatRun,
  readStoredChatRun,
  saveStoredChatRun,
  shouldApplyChatRunEvent,
} from "./chat-conversation-run-client";
import {
  DEFAULT_VISIBLE_COLLECT_RESULTS,
  appendConversationTurn,
  collectItemKey,
  getCollectGroupStats,
  getSelectedCollectItems,
  getVisibleCollectItems,
  toWorkbenchItems,
  toggleCollectSelection,
} from "./chat-collect-result-utils";

function installSessionStorage() {
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    },
  });
}

describe("chat conversation run client", () => {
  beforeEach(() => {
    installSessionStorage();
  });

  test("builds stream url with lastEventId", () => {
    expect(buildChatRunStreamUrl("run-1", 3)).toBe("/api/agent/conversation/runs/run-1/stream?lastEventId=3");
  });

  test("stores and reads recoverable chat run state", () => {
    saveStoredChatRun({
      runId: "run-1",
      sessionId: "session-1",
      lastEventId: 2,
      streamingContent: "hello",
      toolSteps: ["tool"],
      collectResults: [{ platform: "zhihu", topic: "个人网站", items: [{ title: "问题" }] }],
      status: "streaming",
      error: null,
    });

    expect(readStoredChatRun()).toEqual({
      runId: "run-1",
      sessionId: "session-1",
      lastEventId: 2,
      streamingContent: "hello",
      toolSteps: ["tool"],
      collectResults: [{ platform: "zhihu", topic: "个人网站", items: [{ title: "问题" }] }],
      status: "streaming",
      error: null,
    });
  });

  test("invalid stored json is cleared", () => {
    globalThis.sessionStorage.setItem("chat:conversation-run", "{broken");

    expect(readStoredChatRun()).toBeNull();
    expect(globalThis.sessionStorage.getItem("chat:conversation-run")).toBeNull();
  });

  test("clears stored run state", () => {
    saveStoredChatRun({
      runId: "run-1",
      sessionId: "session-1",
      lastEventId: 0,
      streamingContent: "",
      toolSteps: [],
      collectResults: [],
      status: "streaming",
      error: null,
    });

    clearStoredChatRun();

    expect(readStoredChatRun()).toBeNull();
  });

  test("ignores duplicate or older event ids", () => {
    expect(shouldApplyChatRunEvent(2, 2)).toBe(false);
    expect(shouldApplyChatRunEvent(1, 2)).toBe(false);
    expect(shouldApplyChatRunEvent(3, 2)).toBe(true);
  });
});

const zhihuResult: ChatCollectResult = {
  platform: "zhihu",
  topic: "个人网站搭建",
  items: [
    { title: "如何自己搭建一个个人网站？", url: "https://www.zhihu.com/question/1", excerpt: "经典老题", group: "新手入门" },
    { title: "个人网站 SEO 怎么做？", url: "https://www.zhihu.com/question/2", metric: "312 个回答", group: "SEO 引流" },
    { title: "缺少链接的结果", excerpt: "无 URL", group: "新手入门" },
  ],
};

describe("chat collect result helpers", () => {
  test("appendConversationTurn creates one assistant task result when collect results exist", () => {
    const previous: ChatMessage[] = [{ role: "user", content: "采集个人网站问题" }];
    const next = appendConversationTurn(previous, {
      toolSteps: ["✅ zhihu_search 已返回结果"],
      collectResults: [zhihuResult],
      reply: "采集完毕，建议先看新手入门和 SEO 引流。",
    });

    expect(next).toHaveLength(2);
    expect(next[1]).toMatchObject({
      role: "assistant",
      content: "采集完毕，建议先看新手入门和 SEO 引流。",
      collectResults: [zhihuResult],
    });
  });

  test("appendConversationTurn preserves ordinary tool messages when no collect results exist", () => {
    const next = appendConversationTurn([], {
      toolSteps: ["✅ web_fetch 已返回结果"],
      collectResults: [],
      reply: "普通工具结果总结。",
    });

    expect(next).toEqual([
      { role: "tool", content: "", steps: ["✅ web_fetch 已返回结果"] },
      { role: "assistant", content: "普通工具结果总结。" },
    ]);
  });

  test("visibility helper collapses long result lists by default", () => {
    const result: ChatCollectResult = {
      ...zhihuResult,
      items: Array.from({ length: DEFAULT_VISIBLE_COLLECT_RESULTS + 1 }, (_, i) => ({
        title: `结果 ${i + 1}`,
        url: `https://example.com/${i + 1}`,
      })),
    };

    expect(getVisibleCollectItems(result, false)).toHaveLength(DEFAULT_VISIBLE_COLLECT_RESULTS);
    expect(getVisibleCollectItems(result, true)).toHaveLength(DEFAULT_VISIBLE_COLLECT_RESULTS + 1);
  });

  test("selection helper toggles stable item keys", () => {
    const firstKey = collectItemKey(zhihuResult, zhihuResult.items[0], 0);
    const selected = toggleCollectSelection(new Set<string>(), firstKey);
    expect(selected.has(firstKey)).toBe(true);
    expect(toggleCollectSelection(selected, firstKey).has(firstKey)).toBe(false);
  });

  test("group stats are display-only counts and do not filter visible items", () => {
    const stats = getCollectGroupStats(zhihuResult);
    const visible = getVisibleCollectItems(zhihuResult, false);

    expect(stats).toEqual([
      { label: "新手入门", count: 2 },
      { label: "SEO 引流", count: 1 },
    ]);
    expect(visible.map((item) => item.title)).toEqual([
      "如何自己搭建一个个人网站？",
      "个人网站 SEO 怎么做？",
      "缺少链接的结果",
    ]);
  });

  test("selected items map to workbench items and tolerate missing url", () => {
    const selected = new Set<string>([
      collectItemKey(zhihuResult, zhihuResult.items[0], 0),
      collectItemKey(zhihuResult, zhihuResult.items[2], 2),
    ]);

    const targets = getSelectedCollectItems(zhihuResult, selected);
    const items = toWorkbenchItems(zhihuResult, targets, "2026-07-05T00:00:00.000Z");

    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({
      id: "https://www.zhihu.com/question/1",
      title: "如何自己搭建一个个人网站？",
      sourcePlatform: "zhihu",
      sourceTopic: "个人网站搭建",
    });
    expect(items[1]).toMatchObject({
      id: "zhihu-个人网站搭建-缺少链接的结果-1",
      url: "",
    });
  });

  test("empty selection returns no import targets", () => {
    expect(getSelectedCollectItems(zhihuResult, new Set<string>())).toEqual([]);
  });
});
