import { describe, expect, test } from "bun:test";

import { initialCreationProgress, reduceCreationProgress } from "../creation-review-lifecycle";

describe("creation review lifecycle", () => {
  test("shows writer graph phases", () => {
    const state = reduceCreationProgress(
      initialCreationProgress,
      "writer.progress",
      { phase: "generate_outline", status: "started", label: "正在生成文章大纲" },
    );
    expect(state.running).toBe(true);
    expect(state.label).toBe("正在生成文章大纲");
  });
  test("maps review and rewrite events to user-facing progress", () => {
    let state = initialCreationProgress;
    state = reduceCreationProgress(state, "review.started", {
      iteration: 1,
      maxIterations: 3,
    });
    expect(state.label).toBe("正在进行第 1/3 轮评审");

    state = reduceCreationProgress(state, "review.completed", {
      iteration: 1,
      overallScore: 68,
      passed: false,
    });
    expect(state.score).toBe(68);

    state = reduceCreationProgress(state, "rewrite.started", {
      iteration: 2,
      maxIterations: 3,
    });
    expect(state.label).toBe("未达到质量阈值，正在根据建议优化");

    state = reduceCreationProgress(state, "run.completed", {});
    expect(state.label).toBe("创作完成");
    expect(state.running).toBe(false);
  });

  test("keeps running after document.completed until run.completed", () => {
    let state = reduceCreationProgress(initialCreationProgress, "run.started", {});
    state = reduceCreationProgress(state, "document.completed", {});

    expect(state.running).toBe(true);
    expect(state.label).toBe("正在保存最终内容");

    state = reduceCreationProgress(state, "run.completed", {});
    expect(state.running).toBe(false);
  });

  test("ends a failed run without showing completion", () => {
    const state = reduceCreationProgress(
      reduceCreationProgress(initialCreationProgress, "run.started", {}),
      "run.failed",
      {},
    );

    expect(state.running).toBe(false);
    expect(state.label).toBe("创作失败");
  });

  test("does not invent a zero score when review payload has no score", () => {
    const state = reduceCreationProgress(initialCreationProgress, "review.completed", {
      iteration: 1,
      passed: false,
    });

    expect(state.score).toBeNull();
  });

  test("returns the same state for unknown events", () => {
    const state = reduceCreationProgress(initialCreationProgress, "unknown", {});
    expect(state).toBe(initialCreationProgress);
  });
});
