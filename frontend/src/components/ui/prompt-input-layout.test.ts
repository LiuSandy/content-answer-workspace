import { expect, test } from "bun:test";

import { promptInputControlOrder } from "./prompt-input-layout";

test("places outline action immediately after word count", () => {
  expect(
    promptInputControlOrder({
      showStyles: true,
      showWordCount: true,
      hasAfterWordCountActions: true,
    }),
  ).toEqual(["styles", "wordCount", "afterWordCountActions"]);
});
