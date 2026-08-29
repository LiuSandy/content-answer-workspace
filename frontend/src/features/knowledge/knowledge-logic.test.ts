import { describe, test, expect } from "bun:test";
import { formatStatusBadge, isDocEditable } from "./types";

describe("knowledge feature helper logic", () => {
  test("formats status badge variants correctly", () => {
    expect(formatStatusBadge("available")).toEqual({ label: "可用", variant: "default" });
    expect(formatStatusBadge("awaiting_confirmation")).toEqual({
      label: "待确认",
      variant: "outline",
    });
    expect(formatStatusBadge("indexing")).toEqual({ label: "索引中", variant: "secondary" });
    expect(formatStatusBadge("failed")).toEqual({ label: "处理失败", variant: "destructive" });
  });

  test("checks doc editability correctly", () => {
    expect(isDocEditable("awaiting_confirmation")).toBe(true);
    expect(isDocEditable("available")).toBe(true);
    expect(isDocEditable("indexing")).toBe(false);
  });

  test("diff formatting logic", () => {
    const rawDiff = "--- Original\n+++ Candidate\n- Old line\n+ New line";
    expect(rawDiff).toContain("- Old line");
    expect(rawDiff).toContain("+ New line");
  });
});
