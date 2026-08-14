export type PromptInputControl = "styles" | "wordCount" | "afterWordCountActions";

export function promptInputControlOrder(_options: {
  showStyles: boolean;
  showWordCount: boolean;
  hasAfterWordCountActions: boolean;
}): PromptInputControl[] {
  const controls: PromptInputControl[] = [];
  if (_options.showStyles) controls.push("styles");
  if (_options.showWordCount) controls.push("wordCount");
  if (_options.hasAfterWordCountActions) controls.push("afterWordCountActions");
  return controls;
}
