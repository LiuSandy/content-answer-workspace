import { describe, expect, test } from "bun:test";

import { outlineDialogLayout } from "../outline-dialog-layout";

describe("outline dialog scrolling", () => {
  test("gives the dialog and its scroll viewport a shrinkable height chain", () => {
    expect(outlineDialogLayout.content).toContain("h-[min(84vh,760px)]");
    expect(outlineDialogLayout.content).toContain("!flex min-h-0");
    expect(outlineDialogLayout.content).toContain("overflow-hidden");
    expect(outlineDialogLayout.scrollArea).toContain("min-h-0 flex-1");
  });
});
