import { describe, expect, test } from "bun:test";

import {
  addKeyPoint,
  addSection,
  removeKeyPoint,
  removeSection,
  updateSection,
  type EditableOutlineSection,
} from "../outline-editor";

const sections: EditableOutlineSection[] = [
  {
    heading: "开场",
    keyPoints: ["背景", "问题"],
    wordCountEstimate: 200,
  },
  {
    heading: "分析",
    keyPoints: ["原因"],
    wordCountEstimate: 500,
  },
];

describe("outline editor", () => {
  test("adds and removes sections while keeping at least one section", () => {
    const added = addSection(sections);
    expect(added).toHaveLength(3);
    expect(added[2]).toEqual({
      heading: "新章节",
      keyPoints: ["新要点"],
      wordCountEstimate: 200,
    });

    expect(removeSection(added, 1).map((section) => section.heading)).toEqual(["开场", "新章节"]);
    expect(removeSection([sections[0]], 0)).toEqual([sections[0]]);
  });

  test("edits section fields and manages key points immutably", () => {
    const renamed = updateSection(sections, 0, {
      heading: "新的开场",
      wordCountEstimate: 260,
    });
    const withPoint = addKeyPoint(renamed, 0);
    const withoutPoint = removeKeyPoint(withPoint, 0, 0);

    expect(renamed[0].heading).toBe("新的开场");
    expect(renamed[0].wordCountEstimate).toBe(260);
    expect(withPoint[0].keyPoints[withPoint[0].keyPoints.length - 1]).toBe("新要点");
    expect(withoutPoint[0].keyPoints).toEqual(["问题", "新要点"]);
    expect(sections[0].heading).toBe("开场");
  });
});
