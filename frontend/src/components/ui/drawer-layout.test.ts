import { describe, expect, test } from "bun:test";

import { drawerPopupFocusClass } from "./drawer-layout";

describe("drawer focus presentation", () => {
  test("suppresses the browser popup outline while preserving child focus rings", () => {
    expect(drawerPopupFocusClass).toContain("outline-none");
    expect(drawerPopupFocusClass).toContain("focus-visible:outline-none");
  });
});
