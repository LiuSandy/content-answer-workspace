import { useState } from "react";

import { useWorkspaceStore } from "@/store/workspace-store";
import type { QuestionItem } from "@/types/workflow";

import { agentChat } from "./workflow-api";

type Props = {
  sessionId: string;
  question: QuestionItem;
};

export function RefinementChat({ sessionId, question }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastReply, setLastReply] = useState<string | null>(null);

  const updateQuestionAnswer = useWorkspaceStore((s) => s.updateQuestionAnswer);

  async function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setInput("");

    try {
      const res = await agentChat({
        sessionId,
        questionId: question.id,
        message: trimmed,
        currentAnswer: question.answer,
      });

      setLastReply(res.reply);

      if (res.answerUpdated && res.updatedAnswer) {
        updateQuestionAnswer(question.id, res.updatedAnswer);
      }
    } catch {
      setLastReply("请求失败，请重试");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="border-t">
      <button
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:bg-muted/50"
        onClick={() => setIsOpen((v) => !v)}
      >
        <span>{isOpen ? "▼" : "▶"}</span>
        <span>AI 精修</span>
      </button>

      {isOpen && (
        <div className="px-3 pb-3 space-y-2">
          {lastReply && (
            <p className="text-xs text-muted-foreground bg-muted/30 rounded px-2 py-1">{lastReply}</p>
          )}
          <div className="flex gap-2">
            <input
              className="flex-1 text-sm border rounded px-2 py-1 bg-background"
              placeholder="输入指令，如：第二段改短一些…"
              value={input}
              disabled={isLoading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            />
            <button
              className="text-sm px-3 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
              disabled={!input.trim() || isLoading}
              onClick={handleSend}
            >
              {isLoading ? "…" : "发送"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
