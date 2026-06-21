import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SessionSummary } from "@/types/workflow";

type Props = {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onDelete: (sessionId: string) => void;
};

export function ChatSessionList({ sessions, activeSessionId, onSelect, onCreate, onDelete }: Props) {
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-lg border bg-white">
      <div className="p-3">
        <Button className="w-full" onClick={onCreate}>
          + 新建对话
        </Button>
      </div>
      <div className="flex-1 min-h-0 space-y-1 overflow-y-auto px-2 pb-2">
        {sessions.map((session) => (
          <div
            key={session.sessionId}
            className={cn(
              "group flex items-center gap-1 rounded-md px-2 py-2 transition-colors hover:bg-muted",
              session.sessionId === activeSessionId && "bg-muted font-medium",
            )}
          >
            <button
              type="button"
              className="min-w-0 flex-1 truncate text-left text-sm"
              onClick={() => onSelect(session.sessionId)}
            >
              {session.title}
            </button>
            <button
              type="button"
              className="invisible shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:visible group-hover:opacity-100"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(session.sessionId);
              }}
              aria-label="删除对话"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {sessions.length === 0 && (
          <p className="px-2 py-2 text-xs text-muted-foreground">还没有会话，点上面的按钮新建一个。</p>
        )}
      </div>
    </div>
  );
}
