import { useState } from "react";
import { ChevronRight, Loader2, Wrench } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ChatCollectResult } from "@/types/workflow";

import { ChatCollectResultPanel } from "./chat-collect-result-panel";
import { MarkdownMessage } from "./markdown-message";

type Props = {
  content: string;
  steps?: string[];
  collectResults?: ChatCollectResult[];
  live?: boolean;
  statusLabel?: string;
};

export function ChatTaskResultMessage({
  content,
  steps = [],
  collectResults = [],
  live = false,
  statusLabel,
}: Props) {
  const [stepsOpen, setStepsOpen] = useState(false);
  const hasContent = content.trim().length > 0;
  const hasSteps = steps.length > 0;
  const hasResults = collectResults.length > 0;

  return (
    <div className="w-full max-w-[880px] rounded-lg bg-muted px-4 py-3 text-sm leading-relaxed text-foreground">
      {hasSteps && (
        <div className="mb-3 rounded-md border bg-white/70">
          <button
            type="button"
            onClick={() => setStepsOpen((open) => !open)}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-[12px] text-muted-foreground"
          >
            <Wrench className="h-3.5 w-3.5" />
            <span className="flex-1 text-left">工具调用过程{live ? "（进行中）" : ""}</span>
            <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", stepsOpen && "rotate-90")} />
          </button>
          {stepsOpen && (
            <div className="space-y-1 border-t px-3 py-2 text-[12px] text-muted-foreground">
              {steps.map((step, index) => (
                <p key={`${step}-${index}`}>{step}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {hasContent && <MarkdownMessage content={content} />}

      {!hasContent && live && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{statusLabel || "正在生成回答..."}</span>
        </div>
      )}

      {hasResults && (
        <div className={cn("space-y-3", (hasContent || live) && "mt-3")}>
          {collectResults.map((result, index) => (
            <ChatCollectResultPanel key={`${result.platform}-${result.topic}-${index}`} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}
